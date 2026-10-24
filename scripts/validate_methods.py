"""Compare controllers on validation seeds before any evaluation on test seeds.

    python scripts/validate_methods.py --net grid4x4 --scenarios pedestrians --demand peak \
        --methods coop_full coop_full_guard ped_rule_mp mp_guard --seeds 1000 1001 1002 [--jobs 2]

Any controller name works, including the ``<method>_guard`` variants (same controller,
shield with the spillback guard and detector recall). Learned methods run with each of
their selected checkpoints. Writes results/exploration/validate_<net>_<scenario>_<demand>.csv
and prints, per controller, the mean travel and waiting times and the number of runs that
gridlocked (vehicles still in the network at the end).
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from cotraffic.controllers.registry import BASELINES, base_method
from cotraffic.evaluation.matrix import find_checkpoints
from cotraffic.paths import RESULTS_DIR
from cotraffic.seeds import VALIDATION_SEEDS

SCRATCH = RESULTS_DIR / "tmp" / "validate"


def run(task: tuple) -> dict:
    from cotraffic.evaluation.runner import run_episode

    method, net, scenarios, demand, seed, checkpoint, tag = task
    row = run_episode(
        method,
        net,
        demand,
        scenarios,
        seed,
        checkpoint=checkpoint,
        ssm=False,
        tag=tag,
        raw_dir=SCRATCH / "raw",
        logs_dir=SCRATCH / "logs",
        mode="validation",
    )
    return {
        "controller": method,
        "train": tag,
        "seed": seed,
        "mean_travel_time": row["mean_travel_time"],
        "mean_waiting_time": row["mean_waiting_time"],
        "ped_mean_waiting_time": row.get("ped_mean_waiting_time"),
        "ev_delay": row.get("ev_delay"),
        "unfinished": row.get("unfinished", 0),
        "spillback_interventions": row.get("shield_spillback", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--net", default="grid4x4")
    parser.add_argument("--scenarios", nargs="*", default=[])
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--methods", nargs="+", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[1000, 1001, 1002])
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if any(s not in VALIDATION_SEEDS for s in args.seeds):
        parser.error("design choices are made on validation seeds only (1000-1999)")

    scenarios = tuple(args.scenarios)
    tasks = []
    for method in args.methods:
        if base_method(method) in BASELINES:
            variants = [(None, "")]
        else:
            variants = [(p, f"t{k}") for k, p in find_checkpoints(method, args.net)]
            if not variants:
                parser.error(f"no checkpoint for {method} on {args.net}")
        for checkpoint, tag in variants:
            for seed in args.seeds:
                tasks.append((method, args.net, scenarios, args.demand, seed, checkpoint, tag))

    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        df = pd.DataFrame(list(pool.map(run, tasks)))
    name = "+".join(scenarios) or "normal"
    out = RESULTS_DIR / "exploration" / f"validate_{args.net}_{name}_{args.demand}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    df["gridlocked"] = df["unfinished"] > 100
    summary = df.groupby("controller").agg(
        runs=("seed", "size"),
        travel=("mean_travel_time", "mean"),
        waiting=("mean_waiting_time", "mean"),
        ped_wait=("ped_mean_waiting_time", "mean"),
        ev_delay=("ev_delay", "mean"),
        gridlocked=("gridlocked", "sum"),
        guard_switches=("spillback_interventions", "mean"),
    )
    print(summary.round(1).to_string())
    print(f"\n{out}")


if __name__ == "__main__":
    main()
