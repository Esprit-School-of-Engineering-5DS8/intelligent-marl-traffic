"""Phase B: the strategy oracle (ceiling of a strategy layer) and its placebo, validation only.

    python scripts/strategy_oracle.py --mix h2:2 [--runs 1] [--networks ...] [--scenarios ...]
        [--demands ...] [--window 300] [--lookahead 300] [--placebo 3] [--seed 1000] [--jobs 4]

For each window of ``--window`` seconds, each network-level mode (``coop`` COOP-FULL, ``mp``
Max-Pressure everywhere, ``mix`` the best fixed hybrid of phase A, all with EV-RULE pre-emption
and the shield) is played from the start of the episode: the schedule chosen so far, the mode
over the window, then ``--lookahead`` seconds of COOP-FULL (the same continuation for every
mode). The mode of lowest cost over the window and the look-ahead is kept. The cost, fixed
before any run, is the vehicle-seconds of waiting + 10 x the seconds emergency vehicles spend
stopped + the person-seconds pedestrians wait, on the whole network.

Playing from the start costs about 2.5 times more than going on from a SUMO snapshot, but a
restored state leaves the uninterrupted episode (llm/snapshot.py): the oracle would plan on
another trajectory than the one it is measured on.

The chosen schedule is then played in an ordinary episode (pass 2), which gives the same
metrics as every other row and checks that the episode is deterministic: the cumulated
halting at the start of every window must be the planned one (``plan_matches_replay``). The
placebo plays schedules drawn uniformly at random (``--placebo`` draws per cell): the part of
a gain that chance alone gives.

Rows go to results/exploration/combined/raw/ (methods strategy_oracle, strategy_placebo).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from combined_eval import OUT, checkpoint  # noqa: E402

from cotraffic import config  # noqa: E402
from cotraffic.controllers.registry import make_controller  # noqa: E402
from cotraffic.controllers.schedule import MODES, ScheduledPolicy  # noqa: E402
from cotraffic.evaluation.runner import run_episode  # noqa: E402
from cotraffic.llm.rollout import EpisodeSpec, make_env  # noqa: E402
from cotraffic.seeds import TEST_SEEDS  # noqa: E402
from cotraffic.utils.io import git_commit, write_row  # noqa: E402

EV_WEIGHT = 10.0
THRESHOLDS = OUT / "congestion_thresholds.json"


def parse_mix(text: str, network: str) -> tuple[str, float]:
    """``h2:<beta>`` or ``h1:<quantile>`` (threshold read from the phase A profile)."""
    kind, value = text.split(":")
    if kind == "h1":
        q = json.loads(THRESHOLDS.read_text(encoding="utf-8"))[network][f"q{float(value):g}"]
        return "h1", float(q)
    return kind, float(value)


def episode_end(mode: str = "validation") -> float:
    v = config.load_protocol()[mode]
    return float(v["warmup_s"]) + float(v["measure_s"]) + float(v["cooldown_s"])


def run_until(env, policy, obs, until: float) -> tuple[float, dict]:
    """Play ``policy`` up to ``until``; the cost of that stretch (see the module doc)."""
    halting0, ev_stopped, ped = env.halting_sum, 0.0, 0.0
    while env.agents and env.now < until:
        obs, *_ = env.step(policy.act(env, obs))
        for ev in env.ev_ids:
            try:
                if env.conn.vehicle.getSpeed(ev) < 0.1:
                    ev_stopped += env.delta
            except Exception:  # noqa: BLE001 - the vehicle left during the step
                pass
        ped += sum(env.ped_waiting.values()) * env.delta
    waiting = (env.halting_sum - halting0) * env.delta
    return waiting + EV_WEIGHT * ev_stopped + ped, obs


def plan(task: tuple, mode: str = "validation") -> dict:
    """The oracle's schedule for one cell and one COOP-FULL training run (``mode``: the
    episode lengths of the protocol, ``quick`` in the tests)."""
    network, scenario, demand, seed, run, mix_text, window, lookahead = task
    mix = parse_mix(mix_text, network)
    base = make_controller("coop_full", checkpoint(network, run))
    scenarios = [] if scenario == "normal" else [scenario]
    env = make_env(EpisodeSpec(network, demand, scenarios, seed, mode), base.agent_cfg)
    end = episode_end(mode)
    schedule, costs, trace = [], [], []
    try:
        for w in range(int(np.ceil(end / window))):
            t0 = w * window
            cost, past = {}, set()
            for m in MODES:
                policy = ScheduledPolicy(base, schedule + [m], mix, window)  # then COOP-FULL
                obs, _ = env.reset(seed=seed)
                policy.reset(env)
                _, obs = run_until(env, policy, obs, t0)
                past.add(round(env.halting_sum, 6))
                cost[m], _ = run_until(env, policy, obs, min(end, t0 + window + lookahead))
            if len(past) != 1:  # the same schedule up to t0 must give the same episode
                raise RuntimeError(f"window {w}: the three modes do not share the same past")
            trace.append(past.pop())
            best = min(MODES, key=lambda m: (cost[m], MODES.index(m)))  # ties: coop first
            schedule.append(best)
            costs.append({m: round(c, 1) for m, c in cost.items()})
    finally:
        env.close()
    return {"schedule": schedule, "costs": costs, "trace": trace, "mix": mix}


class TracedPolicy(ScheduledPolicy):
    """Records the cumulated halting at the first decision of every window (pass 2)."""

    def reset(self, env) -> None:
        super().reset(env)
        self.trace: list[float] = []

    def act(self, env, obs):
        if int(env.now // self.strategy.window_s) == len(self.trace):
            self.trace.append(round(env.halting_sum, 6))
        return super().act(env, obs)


def play(network, scenario, demand, seed, run, schedule, mix, window, method, tag) -> dict:
    base = make_controller("coop_full", checkpoint(network, run))
    policy = TracedPolicy(base, schedule, mix, window)
    row = run_episode(
        method,
        network,
        demand,
        [scenario],
        seed,
        checkpoint=checkpoint(network, run),
        tag=tag,
        raw_dir=OUT / "raw",
        logs_dir=OUT / "logs",
        controller=policy,
        mode="validation",
    )
    row.update({"train_run": run, "window_s": window, **policy.summary()})
    return row, policy.trace


def oracle_task(task: tuple) -> dict:
    network, scenario, demand, seed, run, mix_text, window, lookahead = task
    p = plan(task)
    row, trace = play(network, scenario, demand, seed, run, p["schedule"], p["mix"], window,
                      "strategy_oracle", f"t{run}")  # fmt: skip
    row.update(
        {
            "mechanism": "strategy oracle (network-level mode per window, played from the start)",
            "lookahead_s": lookahead,
            "oracle_cost": "waiting_veh_s + 10 ev_stopped_s + ped_wait_s",
            "window_costs": json.dumps(p["costs"]),
            "plan_matches_replay": trace[: len(p["trace"])] == p["trace"],
        }
    )
    write_row(OUT / "raw" / f"{row['run_id']}.csv", row)
    return row


def placebo_task(task: tuple) -> dict:
    network, scenario, demand, seed, run, mix_text, window, draw = task
    key = zlib.crc32(f"{network}|{scenario}|{demand}|{seed}|{run}|{draw}".encode())
    rng = np.random.default_rng(key)
    schedule = [str(m) for m in rng.choice(MODES, size=int(np.ceil(episode_end() / window)))]
    mix = parse_mix(mix_text, network)
    row, _ = play(network, scenario, demand, seed, run, schedule, mix, window,
                  "strategy_placebo", f"t{run}-r{draw}")  # fmt: skip
    row.update({"mechanism": "strategy placebo (uniform random mode per window)", "draw": draw})
    write_row(OUT / "raw" / f"{row['run_id']}.csv", row)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mix", required=True, help="best fixed hybrid: h2:<beta> or h1:<q>")
    parser.add_argument("--networks", nargs="+", default=["grid4x4", "real_district"])
    parser.add_argument("--scenarios", nargs="+", default=["normal", "emergency", "incident"])
    parser.add_argument("--demands", nargs="+", default=["medium", "peak"])
    parser.add_argument("--runs", nargs="+", type=int, default=[1])
    parser.add_argument("--window", type=float, default=300.0)
    parser.add_argument("--lookahead", type=float, default=300.0)
    parser.add_argument("--placebo", type=int, default=3, help="random schedules per cell")
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    if args.seed in TEST_SEEDS:
        raise SystemExit("test seeds are never used to tune anything")
    if git_commit().endswith("-dirty") and not args.allow_dirty:
        raise SystemExit("tracked files have uncommitted changes: commit them first")
    # libsumo, inherited by the workers: over TraCI, the ports drawn by workers starting
    # together can collide (an oracle cell starts SUMO 28 times). Same episodes as TraCI,
    # checked on the phase A row hybrid_h2-t1-b4, grid4x4 emergency peak.
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
    cells = [
        (n, s, d)
        for n in args.networks
        for s in args.scenarios
        for d in args.demands
        if not (n == "real_district" and s == "pedestrians")
    ]
    common = [
        (n, s, d, args.seed, k, args.mix, args.window) for n, s, d in cells for k in args.runs
    ]
    oracles = [t + (args.lookahead,) for t in common]
    placebos = [t + (r,) for t in common for r in range(args.placebo)]
    print(f"{len(oracles)} oracle episodes, {len(placebos)} placebo episodes", flush=True)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        # the long oracle cells first, the short placebo episodes fill the idle workers
        futures = [pool.submit(oracle_task, t) for t in oracles]
        futures += [pool.submit(placebo_task, t) for t in placebos]
        for future in as_completed(futures):
            row = future.result()
            match = row.get("plan_matches_replay")
            print(f"done {row['run_id']}" + ("" if match is None else f" match={match}"),
                  flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
