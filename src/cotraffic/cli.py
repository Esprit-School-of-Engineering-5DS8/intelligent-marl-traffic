"""Command-line entry point: ``python -m cotraffic <command> [options]``.

Commands import their modules lazily so that ``--help`` is instant and commands that
only read result files (figures, tables) work without SUMO installed.
"""

from __future__ import annotations

import argparse
import os
import sys


def _libsumo_default() -> None:
    # libsumo is several times faster than TraCI; the GUI paths switch back explicitly.
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")


def cmd_networks(args: argparse.Namespace) -> int:
    from cotraffic import config
    from cotraffic.networks.build import build_network

    names = config.available("networks") if args.all else args.names
    for name in names:
        print(f"{name}: {build_network(name, force=args.force)}")
    return 0


def cmd_episode(args: argparse.Namespace) -> int:
    _libsumo_default()
    from cotraffic.evaluation.quick import random_episode

    summary = random_episode(
        args.net, args.demand, args.seconds, seed=args.seed, scenarios=args.scenarios
    )
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


def cmd_calibrate_demand(args: argparse.Namespace) -> int:
    _libsumo_default()
    import pandas as pd

    from cotraffic.evaluation.calibrate import demand_sweep

    out = demand_sweep(args.net, args.scales, args.methods, args.seeds, args.demand, args.jobs)
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(pd.read_csv(out).round(1).to_string(index=False))
    print(f"saved {out}")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    _libsumo_default()
    from cotraffic.training.reward_norm import calibrate_rewards

    out = calibrate_rewards(args.net)
    print(out.read_text(encoding="utf-8"))
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    _libsumo_default()
    from cotraffic.training.train import train

    folder = train(
        args.agent,
        args.net,
        args.seed,
        quick=args.quick,
        resume=not args.restart,
        total_timesteps=args.timesteps,
        threads=args.threads,
    )
    print(f"training run: {folder}")
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    _libsumo_default()
    from cotraffic.training.select import select_checkpoint, trained_runs

    runs = trained_runs(args.agent, args.net)
    if args.seeds:
        runs = [r for r in runs if r[2] in args.seeds]
    if not runs:
        print("no training run found")
        return 1
    for agent, network, seed in runs:
        print(f"selected {select_checkpoint(agent, network, seed, args.jobs)}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    _libsumo_default()
    from cotraffic.evaluation.matrix import run_matrix

    failures = run_matrix(args.experiment, args.jobs, args.force, args.methods)
    return 1 if failures else 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    from cotraffic.analysis.aggregate import run_aggregate

    for path in run_aggregate():
        print(f"wrote {path}")
    return 0


def cmd_tables(args: argparse.Namespace) -> int:
    from cotraffic.analysis.tables import build_report_tables

    print(f"wrote {build_report_tables()}")
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    _libsumo_default()
    from cotraffic.evaluation.smoke import run_smoke

    return run_smoke(only=args.only)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cotraffic", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("networks", help="build SUMO networks from configs/networks")
    p.add_argument("names", nargs="*", default=[])
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true", help="rebuild even if the file exists")
    p.set_defaults(func=cmd_networks)

    p = sub.add_parser("episode", help="run one random-policy episode (sanity check)")
    p.add_argument("--net", default="grid2x2")
    p.add_argument("--demand", default="medium")
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--scenarios", nargs="*", default=[])
    p.set_defaults(func=cmd_episode)

    p = sub.add_parser("calibrate-demand", help="sweep the peak demand rate (tuning seeds)")
    p.add_argument("--net", default="grid4x4")
    p.add_argument("--scales", type=float, nargs="+", default=[1.0, 1.5, 2.0])
    p.add_argument("--methods", nargs="+", default=["ft"])
    p.add_argument("--seeds", type=int, nargs="+", default=[5001])
    p.add_argument("--demand", default="peak")
    p.add_argument("--jobs", type=int, default=2)
    p.set_defaults(func=cmd_calibrate_demand)

    p = sub.add_parser("calibrate", help="reward normalisation constants from baseline runs")
    p.add_argument("--net", default="grid4x4")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("train", help="train one learned variant (PPO, parameter sharing)")
    p.add_argument("--agent", default="coop", help="config in configs/agents")
    p.add_argument("--net", default="grid4x4")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--quick", action="store_true", help="a few thousand steps, for smoke tests")
    p.add_argument("--timesteps", type=int, default=None, help="override total agent steps")
    p.add_argument("--restart", action="store_true", help="ignore existing checkpoints")
    p.add_argument("--threads", type=int, default=1, help="torch CPU threads")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("select", help="pick the best checkpoint of training runs (validation)")
    p.add_argument("--agent", default=None)
    p.add_argument("--net", default=None)
    p.add_argument("--seeds", type=int, nargs="*", default=None)
    p.add_argument("--jobs", type=int, default=2)
    p.set_defaults(func=cmd_select)

    p = sub.add_parser("evaluate", help="run an experiment matrix (configs/experiments)")
    p.add_argument("--experiment", default="full_matrix")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--force", action="store_true", help="rerun runs that already have results")
    p.add_argument(
        "--methods",
        nargs="*",
        default=None,
        help="only these methods ('baselines' = ft act mp ev_rule)",
    )
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("aggregate", help="statistics and summary tables from results/raw")
    p.set_defaults(func=cmd_aggregate)

    p = sub.add_parser("tables", help="write results/summary/REPORT_TABLES.md")
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser("smoke", help="quick end-to-end check of every feature")
    p.add_argument("--only", nargs="*", default=None, help="run only these checks")
    p.set_defaults(func=cmd_smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
