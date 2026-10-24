"""Compare IND (PPO), DQN and their ensemble on validation seeds (design choice only).

    python scripts/try_ensemble.py [--net grid4x4] [--demands peak medium]
        [--seeds 1000 1001] [--weights 0.5] [--train 1 2 3] [--jobs 2]

Writes results/exploration/ensemble_<net>.csv (one row per run) and prints the mean
travel and waiting times per controller. Test seeds are never used here.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR
from cotraffic.seeds import VALIDATION_SEEDS

SCRATCH = RESULTS_DIR / "tmp" / "ensemble"


def run(task: tuple[str, str, str, int, int, float]) -> dict:
    from cotraffic.controllers.ensemble import PpoDqnEnsemble
    from cotraffic.controllers.registry import make_controller
    from cotraffic.evaluation.runner import run_episode

    kind, net, demand, seed, train, weight = task
    ppo = CHECKPOINTS_DIR / "ind" / net / f"seed{train}.zip"
    dqn = CHECKPOINTS_DIR / "dqn" / net / f"seed{train}.zip"
    if kind == "ens":
        controller, method, tag = PpoDqnEnsemble(ppo, dqn, weight), "ens", f"w{weight}-t{train}"
    else:
        checkpoint = ppo if kind == "ind" else dqn
        controller, method, tag = make_controller(kind, checkpoint), kind, f"t{train}"
    row = run_episode(
        method,
        net,
        demand,
        (),
        seed,
        ssm=False,
        tag=tag,
        raw_dir=SCRATCH / "raw",
        logs_dir=SCRATCH / "logs",
        controller=controller,
        mode="validation",
    )
    return {
        "controller": method if kind != "ens" else f"ens_w{weight}",
        "train": train,
        "demand": demand,
        "seed": seed,
        "mean_travel_time": row["mean_travel_time"],
        "mean_waiting_time": row["mean_waiting_time"],
        "unfinished": row.get("unfinished", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--net", default="grid4x4")
    parser.add_argument("--demands", nargs="+", default=["peak", "medium"])
    parser.add_argument("--seeds", nargs="+", type=int, default=[1000, 1001])
    parser.add_argument("--weights", nargs="+", type=float, default=[0.5])
    parser.add_argument("--train", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if any(s not in VALIDATION_SEEDS for s in args.seeds):
        parser.error("design choices are made on validation seeds only (1000-1999)")

    tasks = [
        (kind, args.net, d, s, t, w)
        for d in args.demands
        for s in args.seeds
        for t in args.train
        for kind, w in [("ind", 0.0), ("dqn", 0.0)] + [("ens", w) for w in args.weights]
    ]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(run, tasks))
    df = pd.DataFrame(rows)
    out = RESULTS_DIR / "exploration" / f"ensemble_{args.net}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(
        df.groupby(["demand", "controller"])[
            ["mean_travel_time", "mean_waiting_time", "unfinished"]
        ]
        .mean()
        .round(1)
    )
    print(f"\n{out}")


if __name__ == "__main__":
    main()
