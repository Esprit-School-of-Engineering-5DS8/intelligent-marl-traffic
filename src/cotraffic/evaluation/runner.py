"""Run one evaluation episode and store its metrics.

One run = (method, network, scenario(s), demand, seed). It writes
``results/raw/<run_id>.csv`` (one row: identifiers, git commit, all metrics) and
``results/logs/timeseries/<run_id>.csv`` (per-minute network state). SUMO's large
output files are deleted once the metrics are computed.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cotraffic import config
from cotraffic.controllers.base import Controller
from cotraffic.controllers.registry import make_controller
from cotraffic.envs.episodes import evaluation_episode, split_scenarios
from cotraffic.envs.traffic_env import CoTrafficEnv
from cotraffic.evaluation.metrics import compute_metrics
from cotraffic.paths import LOGS_DIR, RAW_DIR, RESULTS_DIR
from cotraffic.utils.io import git_commit, write_row


def run_id(
    method: str, network: str, scenarios: Sequence[str], demand: str, seed: int, tag: str = ""
) -> str:
    scen = "+".join(scenarios) or "normal"
    return "__".join([method + (f"-{tag}" if tag else ""), network, scen, demand, f"s{seed}"])


def run_episode(
    method: str,
    network: str,
    demand: str,
    scenarios: Sequence[str] = (),
    seed: int = 0,
    checkpoint: Path | None = None,
    quick: bool = False,
    ssm: bool = True,
    tag: str = "",
    raw_dir: Path = RAW_DIR,
    logs_dir: Path = LOGS_DIR,
    controller: Controller | None = None,
    record_decisions: bool = False,
    keep_outputs: bool = False,
    scale: float = 1.0,
    mode: str = "evaluation",
    extra: bool = False,
) -> dict[str, Any]:
    """Simulate one episode with ``method`` and return (and store) its result row.

    ``extra`` adds the measurements of :mod:`cotraffic.evaluation.extra` to the row and
    writes their per-vehicle and per-green logs; the matrix stores such runs apart, in
    ``results/extra/``."""
    protocol = config.load_protocol()
    scenarios = [s for s in scenarios if s != "normal"]
    controller = controller or make_controller(method, checkpoint)
    rid = run_id(method, network, scenarios, demand, seed, tag)
    out_dir = RESULTS_DIR / "tmp" / rid
    if out_dir.exists():
        shutil.rmtree(out_dir)
    episode = evaluation_episode(
        network,
        demand,
        scenarios,
        seed,
        output_dir=out_dir,
        ssm=ssm,
        additional=controller.additional_files(network, demand),
        protocol=protocol,
        quick=quick,
        scale=scale,
        mode=mode,
    )
    _, runtime = split_scenarios(scenarios)
    incident = episode.bundle.meta.get("incident")
    incident_queue: list[tuple[float, float]] = []

    def record_incident(env, now: float) -> None:
        if int(now) % 10 == 0:
            incident_queue.append((now, env.conn.edge.getLastStepHaltingNumber(incident["edge"])))

    hooks = controller.step_hooks() + ([record_incident] if incident else [])
    probe = None
    if extra:
        from cotraffic.evaluation.extra import ExtraProbe

        probe = ExtraProbe((episode.measure_from, episode.measure_to))
        hooks.append(probe)
    env = CoTrafficEnv(
        network,
        lambda rng: episode,
        controller.agent_cfg,
        controlled=controller.controlled,
        runtime_scenarios=runtime,
        step_hooks=hooks,
        compute_observations=controller.needs_observations,
        record_decisions=record_decisions,
        protocol=protocol,
    )
    latencies: list[float] = []
    wall = time.perf_counter()
    try:
        obs, _ = env.reset(seed=seed)
        controller.reset(env)
        while env.agents:
            start = time.perf_counter()
            actions = controller.act(env, obs)
            if controller.controlled:
                latencies.append(time.perf_counter() - start)
            obs, _rewards, _term, _trunc, _infos = env.step(actions)
        summary = env.episode_summary()
        teleported = set(env.teleported)
        decisions = list(env.decisions)
    finally:
        env.close()
    wall = time.perf_counter() - wall

    metrics, series, distribution = compute_metrics(
        out_dir,
        episode.bundle.route_files,
        (episode.measure_from, episode.measure_to),
        episode.end_time,
        protocol,
        teleported,
        ssm,
        incident,
    )
    extra_metrics: dict[str, float] = {}
    if probe is not None:
        extra_metrics, ev_log, green_log = probe.finish(out_dir, episode.bundle.route_files)
        for name, log in (("emergency", ev_log), ("pedestrian_greens", green_log)):
            if not log.empty:
                folder = logs_dir / name
                folder.mkdir(parents=True, exist_ok=True)
                log.insert(0, "run_id", rid)
                log.to_csv(folder / f"{rid}.csv", index=False)
    if incident_queue:
        q = pd.DataFrame(incident_queue, columns=["time", "incident_edge_halting"])
        q["minute"] = (q["time"] // 60).astype(int)
        series = series.merge(
            q.groupby("minute")["incident_edge_halting"].mean().reset_index(),
            on="minute",
            how="left",
        )
    row: dict[str, Any] = {
        "run_id": rid,
        "method": method,
        "variant": tag or method,
        "network": network,
        "scenario": "+".join(scenarios) or "normal",
        "demand": demand,
        "seed": seed,
        "checkpoint": str(checkpoint) if checkpoint else "",
        "git_commit": git_commit(),
        "quick": quick,
        "demand_scale": scale,
    }
    row.update(metrics)
    row.update(extra_metrics)
    n_agents = max(1, len(env.possible_agents))
    row.update(
        {
            "sim_wall_time_s": wall,
            "decisions": summary["decisions"],
            "switches": summary["switches"],
            "shield_interventions": sum(summary[k] for k in summary if k.startswith("shield_")),
            **{k: summary[k] for k in summary if k.startswith("shield_")},
            "messages_lost": summary.get("messages_lost", 0),
            "inference_ms_per_decision": 1000 * float(np.mean(latencies)) / n_agents
            if latencies
            else 0.0,
            "inference_ms_per_step": 1000 * float(np.mean(latencies)) if latencies else 0.0,
            "incident_start": episode.bundle.meta.get("incident", {}).get("start", ""),
            "preemptions": getattr(controller, "preemptions", ""),
        }
    )
    write_row(raw_dir / f"{rid}.csv", row)
    ts_dir = logs_dir / "timeseries"
    ts_dir.mkdir(parents=True, exist_ok=True)
    series.insert(0, "run_id", rid)
    series.to_csv(ts_dir / f"{rid}.csv", index=False)
    dist_dir = logs_dir / "waiting_distributions"
    dist_dir.mkdir(parents=True, exist_ok=True)
    distribution.insert(0, "run_id", rid)
    distribution.to_csv(dist_dir / f"{rid}.csv", index=False)
    if decisions:
        dec_dir = logs_dir / "decisions"
        dec_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(decisions).to_csv(dec_dir / f"{rid}.csv", index=False)
    if not keep_outputs:
        shutil.rmtree(out_dir, ignore_errors=True)
    return row
