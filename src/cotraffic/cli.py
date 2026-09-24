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

    p = sub.add_parser("smoke", help="quick end-to-end check of every feature")
    p.add_argument("--only", nargs="*", default=None, help="run only these checks")
    p.set_defaults(func=cmd_smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
