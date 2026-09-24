"""Demand calibration: how congested is each network under the classical controllers?

The peak rate of a network is chosen so that fixed-time control shows clear congestion
without permanent gridlock. We sweep a multiplier of the configured peak rate on seeds
reserved for tuning (5000-5999), never on evaluation seeds.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from cotraffic.paths import RESULTS_DIR

SWEEP_COLUMNS = [
    "method",
    "demand_scale",
    "seed",
    "vehicles",
    "mean_travel_time",
    "mean_waiting_time",
    "mean_time_loss",
    "p95_waiting_time",
    "mean_queue",
    "mean_insertion_backlog",
    "throughput_per_h",
    "unfinished",
    "never_inserted",
    "teleports_total",
    "sim_wall_time_s",
]


def _one(args: tuple[str, str, str, float, int]) -> dict:
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
    from cotraffic.controllers.registry import make_controller
    from cotraffic.evaluation.runner import run_episode

    network, method, demand, scale, seed = args
    kwargs = {"scale": scale} if method == "ft" else {}
    controller = make_controller(method, **kwargs)
    return run_episode(
        method,
        network,
        demand,
        [],
        seed,
        ssm=False,
        scale=scale,
        controller=controller,
        tag=f"x{scale:g}",
        raw_dir=RESULTS_DIR / "calibration" / "raw",
        logs_dir=RESULTS_DIR / "calibration" / "logs",
    )


def demand_sweep(
    network: str,
    scales: Sequence[float],
    methods: Sequence[str] = ("ft",),
    seeds: Sequence[int] = (5001,),
    demand: str = "peak",
    jobs: int = 2,
) -> Path:
    tasks = [
        (network, m, demand, float(s), int(seed)) for m in methods for s in scales for seed in seeds
    ]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(_one, tasks))
    df = pd.DataFrame(rows)[SWEEP_COLUMNS].sort_values(["method", "demand_scale", "seed"])
    out = RESULTS_DIR / "calibration" / f"{network}_demand_sweep.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_file():
        old = pd.read_csv(out)
        keep = ~old.set_index(["method", "demand_scale", "seed"]).index.isin(
            df.set_index(["method", "demand_scale", "seed"]).index
        )
        df = pd.concat([old[keep], df]).sort_values(["method", "demand_scale", "seed"])
    df.to_csv(out, index=False)
    return out
