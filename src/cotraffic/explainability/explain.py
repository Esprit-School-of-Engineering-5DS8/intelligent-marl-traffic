"""Why did an agent choose a phase? Decision logs and feature-group importance.

* Decision log: for every decision of a demo episode, the blocks of the observation that
  the decision depends on (the chosen phase changes when the block is replaced by zeros)
  and a sentence built from the measured traffic state, e.g.
  "keeps north-south green: 12 halting on north-south, 4 on east-west; ambulance 180 m
  from the south".
* Permutation importance by block: on the observations of evaluation episodes, each block
  is shuffled between decisions and we count how often the chosen phase changes; then an
  episode is replayed with that block shuffled online, which gives the effect on travel
  time. A block the policy ignores changes nothing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cotraffic import config
from cotraffic.controllers.rl_policy import LearnedPolicy
from cotraffic.envs.observations import ObservationConfig, Padding, block_slices
from cotraffic.networks.topology import SIDES
from cotraffic.paths import LOGS_DIR, RESULTS_DIR, SUMMARY_DIR

GROUP_NAMES = {
    "lanes": "local lanes",
    "phase": "phase and timers",
    "neighbours": "neighbour messages",
    "emergency": "emergency vehicles",
    "pedestrians": "pedestrians",
    "buses": "buses",
    "forecast": "forecast",
}


class RecordingPolicy(LearnedPolicy):
    """Learned policy that keeps every observation it acts on."""

    def __init__(self, method: str, checkpoint: Path) -> None:
        super().__init__(method, checkpoint)
        self.records: list[np.ndarray] = []

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        self.records.extend(obs.values())
        return super().act(env, obs)


class PermutedPolicy(LearnedPolicy):
    """Learned policy whose input block ``group`` is replaced by values drawn from a pool
    of recorded observations (breaks the link between the block and the situation)."""

    def __init__(
        self, method: str, checkpoint: Path, group: slice, pool: np.ndarray, seed: int = 0
    ) -> None:
        super().__init__(method, checkpoint)
        self.group, self.pool = group, pool
        self.rng = np.random.default_rng(seed)

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        shuffled = {}
        for agent, o in obs.items():
            o = o.copy()
            o[self.group] = self.pool[self.rng.integers(len(self.pool)), self.group]
            shuffled[agent] = o
        return super().act(env, shuffled)


def _greedy(model, batch: np.ndarray) -> np.ndarray:
    actions, _ = model.predict(batch, deterministic=True)
    return np.asarray(actions)


def phase_description(inter, phase: int) -> str:
    """Name a phase by the sides whose lanes it serves (e.g. 'north-south')."""
    sides = [s for s in SIDES if any(ln in inter.phase_lanes[phase] for ln in inter.side_lanes[s])]
    return "-".join(sides) if sides else f"phase {phase}"


def describe_state(env, tid: str) -> dict[str, Any]:
    """Measured situation of one intersection at decision time."""
    inter = env.intersections[tid]
    state: dict[str, Any] = {
        "phase": inter.phase,
        "queues": {
            p: sum(env.meas.halting[ln] for ln in inter.phase_lanes[p])
            for p in range(inter.n_phases)
        },
        "names": {p: phase_description(inter, p) for p in range(inter.n_phases)},
    }
    ev = env.ev_info.get(tid)
    if ev:
        side, prox = max(ev["side"].items(), key=lambda kv: kv[1])
        state["ev"] = (
            side,
            (1 - prox) * float(env.protocol["observation"]["ev_detection_range_m"]),
        )
    state["peds"] = sum(env.ped_waiting.get(c, 0.0) for c in inter.crossings)
    return state


def sentence(state: dict[str, Any], executed: int, reason: str) -> str:
    names = state["names"]
    verb = "keeps" if executed == state["phase"] else "switches to"
    parts = [
        f"{verb} {names[executed]} green",
        ", ".join(f"{q:.0f} halting on {names[p]}" for p, q in state["queues"].items()),
    ]
    if "ev" in state:
        side, dist = state["ev"]
        parts.append(f"emergency vehicle {dist:.0f} m from the {side}")
    if state["peds"]:
        parts.append(f"{state['peds']:.0f} pedestrians waiting")
    if reason:
        parts.append(f"shield: {reason.replace('_', ' ')}")
    return "; ".join(parts)


def explain_episode(
    method: str,
    checkpoint: Path,
    network: str,
    demand: str,
    scenarios: list[str],
    seed: int,
    max_rows: int = 5000,
) -> Path:
    """Decision log with the blocks each decision depends on and a readable sentence."""
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
    from cotraffic.envs.episodes import evaluation_episode, split_scenarios
    from cotraffic.envs.traffic_env import CoTrafficEnv

    policy = LearnedPolicy(method, checkpoint)
    episode = evaluation_episode(network, demand, scenarios, seed, ssm=False)
    _, runtime = split_scenarios(scenarios)
    env = CoTrafficEnv(
        network,
        lambda rng: episode,
        policy.agent_cfg,
        runtime_scenarios=runtime,
        record_decisions=True,
    )
    slices = block_slices(env.obs_cfg, env.pad)
    rows: list[dict[str, Any]] = []
    try:
        obs, _ = env.reset(seed=seed)
        policy.reset(env)
        while env.agents:
            agents = list(obs)
            batch = np.stack([obs[a] for a in agents])
            chosen = _greedy(policy.model, batch)
            depends = {a: [] for a in agents}
            for name, sl in slices.items():
                masked = batch.copy()
                masked[:, sl] = 0.0
                for a, before, after in zip(
                    agents, chosen, _greedy(policy.model, masked), strict=True
                ):
                    if before != after:
                        depends[a].append(GROUP_NAMES[name])
            states = {a: describe_state(env, a) for a in agents}
            now = env.now
            start = len(env.decisions)
            obs, *_ = env.step({a: int(x) for a, x in zip(agents, chosen, strict=True)})
            for rec in env.decisions[start:]:
                if len(rows) >= max_rows:
                    break
                a = rec["agent"]
                rows.append(
                    {
                        "time": now,
                        "agent": a,
                        "requested": rec["requested"],
                        "executed": rec["executed"],
                        "shield": rec["reason"],
                        "depends_on": "; ".join(depends[a]) or "none",
                        "explanation": sentence(states[a], rec["executed"], rec["reason"]),
                    }
                )
    finally:
        env.close()
    scen = "+".join(scenarios) or "normal"
    name = f"explained__{method}__{network}__{scen}__{demand}__s{seed}.csv"
    out = LOGS_DIR / "decisions" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def permutation_importance(
    method: str,
    checkpoint: Path,
    network: str,
    demand: str,
    scenarios: list[str],
    seeds: list[int],
    online: bool = True,
) -> Path:
    """Action-change rate and travel-time effect of shuffling each observation block."""
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
    from cotraffic.evaluation.runner import run_episode

    work = RESULTS_DIR / "tmp" / "importance"
    recorder = RecordingPolicy(method, checkpoint)
    base_rows = [
        run_episode(
            method,
            network,
            demand,
            scenarios,
            s,
            controller=recorder,
            ssm=False,
            tag="imp-base",
            raw_dir=work,
            logs_dir=work,
        )
        for s in seeds
    ]
    pool = np.stack(recorder.records)
    base_travel = float(np.mean([r["mean_travel_time"] for r in base_rows]))
    rng = np.random.default_rng(0)
    probe = pool[rng.choice(len(pool), size=min(20000, len(pool)), replace=False)]
    base_actions = _greedy(recorder.model, probe)
    net_cfg = config.load("networks", network)
    slices = block_slices(
        ObservationConfig.from_dict(recorder.agent_cfg.get("observation")),
        Padding.from_dict(net_cfg["padding"]),
    )
    rows = []
    for name, sl in slices.items():
        shuffled = probe.copy()
        shuffled[:, sl] = probe[rng.permutation(len(probe)), sl]
        change = float(np.mean(_greedy(recorder.model, shuffled) != base_actions))
        travel = float("nan")
        if online:
            ctrl = PermutedPolicy(method, checkpoint, sl, pool)
            runs = [
                run_episode(
                    method,
                    network,
                    demand,
                    scenarios,
                    s,
                    controller=ctrl,
                    ssm=False,
                    tag=f"imp-{name}",
                    raw_dir=work,
                    logs_dir=work,
                )
                for s in seeds
            ]
            travel = float(np.mean([r["mean_travel_time"] for r in runs]))
        rows.append(
            {
                "method": method,
                "network": network,
                "demand": demand,
                "scenario": "+".join(scenarios) or "normal",
                "group": GROUP_NAMES[name],
                "action_change_rate": change,
                "travel_time": travel,
                "travel_time_base": base_travel,
                "travel_time_increase_pct": 100.0 * (travel - base_travel) / base_travel,
                "decisions_probed": len(probe),
                "seeds": " ".join(map(str, seeds)),
            }
        )
    out = SUMMARY_DIR / f"importance_{method}_{network}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out
