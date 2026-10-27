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
    from cotraffic.recipes import load_recipe
    from cotraffic.training.train import train

    name = args.recipe or args.agent
    recipe = load_recipe(name)
    folder = train(
        recipe.get("name", name),
        args.net,
        args.seed,
        quick=args.quick,
        resume=not args.restart,
        total_timesteps=args.timesteps,
        threads=args.threads,
        recipe=recipe,
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


def cmd_validate(args: argparse.Namespace) -> int:
    _libsumo_default()
    import pandas as pd

    from cotraffic.training.select import validation_table

    out = validation_table(args.agents, args.baselines, args.net, args.seed, jobs=args.jobs)
    df = pd.read_csv(out)
    print(df.pivot_table(index="method", columns="demand", values="mean_travel_time").round(1))
    print(f"saved {out}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    _libsumo_default()
    from cotraffic.evaluation.matrix import run_matrix

    failures = run_matrix(args.experiment, args.jobs, args.force, args.methods, args.extra)
    return 1 if failures else 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    from cotraffic.analysis.aggregate import run_aggregate

    for path in run_aggregate():
        print(f"wrote {path}")
    return 0


def cmd_forecast(args: argparse.Namespace) -> int:
    _libsumo_default()
    import pandas as pd

    from cotraffic.forecasting.dataset import DATA_DIR, build_dataset
    from cotraffic.forecasting.models import evaluate

    if args.rebuild or not (DATA_DIR / f"inflow_{args.net}.csv").is_file():
        print(f"dataset: {build_dataset(args.net, args.seeds, args.jobs)}")
    out = evaluate(args.net)
    from cotraffic.forecasting.online import export_ridge

    print(f"model for the agents: {export_ridge(args.net)}")
    table = pd.read_csv(out)
    print(table[table["demand"] == "all"].round(2).to_string(index=False))
    print(f"saved {out}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    _libsumo_default()
    from pathlib import Path

    from cotraffic.explainability.explain import explain_episode, permutation_importance
    from cotraffic.paths import CHECKPOINTS_DIR

    ckpt = (
        Path(args.checkpoint)
        if args.checkpoint
        else CHECKPOINTS_DIR / args.agent / args.net / "seed1.zip"
    )
    log = explain_episode(args.agent, ckpt, args.net, args.demand, args.scenarios, args.seed)
    print(f"decision log: {log}")
    if not args.no_importance:
        out = permutation_importance(
            args.agent,
            ckpt,
            args.net,
            args.demand,
            args.scenarios,
            args.importance_seeds,
            online=not args.offline,
        )
        print(f"importance: {out}")
    return 0


def cmd_figures(args: argparse.Namespace) -> int:
    from cotraffic.analysis.figures import build_figures

    for line in build_figures():
        print(line)
    return 0


def cmd_tables(args: argparse.Namespace) -> int:
    from cotraffic.analysis.tables import build_report_tables

    print(f"wrote {build_report_tables()}")
    return 0


def _llm(args: argparse.Namespace):
    from cotraffic.assistant.llm import LocalLLM

    if args.no_llm:
        return None
    llm = LocalLLM()
    usable, message = llm.status()
    if not usable:
        print(f"(local model not used: {message})")
        return None
    return llm


def cmd_ask(args: argparse.Namespace) -> int:
    from cotraffic.assistant.ask import ask

    reply = ask(" ".join(args.question), _llm(args), write=not args.fast)
    print(reply.text)
    if reply.finding.table is not None and args.table:
        print()
        print(reply.finding.table.to_string(index=False))
    print(
        f"\n[question lue par : {reply.read_by} ; réponse écrite par : {reply.written_by}"
        + (f" ; source : {reply.finding.source}" if reply.finding.source else "")
        + (f" ; {reply.note}" if reply.note else "")
        + "]"
    )
    return 0


def cmd_demo_plan(args: argparse.Namespace) -> int:
    import subprocess

    from cotraffic.assistant.scenario import plan_demo

    plan = plan_demo(" ".join(args.request), _llm(args))
    print("command:", subprocess.list2cmdline(plan.command))
    for note in plan.notes:
        print("note:", note)
    print(f"[requête lue par : {plan.read_by}]")
    if args.run:
        return subprocess.call(plan.command)
    return 0


def cmd_llm_status(args: argparse.Namespace) -> int:
    from cotraffic.assistant.llm import LocalLLM

    usable, message = LocalLLM().status()
    print(("ok: " if usable else "not ready: ") + message)
    return 0 if usable else 1


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
    p.add_argument("--net", default="grid3x3")
    p.add_argument("--scales", type=float, nargs="+", default=[1.0, 1.5, 2.0])
    p.add_argument("--methods", nargs="+", default=["ft"])
    p.add_argument("--seeds", type=int, nargs="+", default=[5001])
    p.add_argument("--demand", default="peak")
    p.add_argument("--jobs", type=int, default=2)
    p.set_defaults(func=cmd_calibrate_demand)

    p = sub.add_parser("calibrate", help="reward normalisation constants from baseline runs")
    p.add_argument("--net", default="grid3x3")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("train", help="train one learned recipe (PPO, parameter sharing)")
    p.add_argument("--agent", default="coop", help="recipe/preset name (configs/recipes or agents)")
    p.add_argument("--recipe", default=None, help="recipe name or path (overrides --agent)")
    p.add_argument("--net", default="grid3x3")
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

    p = sub.add_parser("validate", help="compare variants on validation seeds (design choices)")
    p.add_argument("--agents", nargs="+", required=True)
    p.add_argument("--baselines", nargs="*", default=["mp"])
    p.add_argument("--net", default="grid3x3")
    p.add_argument("--seed", type=int, default=1, help="training seed of the runs")
    p.add_argument("--jobs", type=int, default=2)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("evaluate", help="run an experiment matrix (configs/experiments)")
    p.add_argument("--experiment", default="full_matrix")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--force", action="store_true", help="rerun runs that already have results")
    p.add_argument(
        "--methods",
        nargs="*",
        default=None,
        help="only these methods ('baselines' = ft act mp ev_rule ev_rule_mp ped_rule_mp)",
    )
    p.add_argument(
        "--extra",
        action="store_true",
        help="with the dashboard's extra measurements, stored in results/extra/",
    )
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("aggregate", help="statistics and summary tables from results/raw")
    p.set_defaults(func=cmd_aggregate)

    p = sub.add_parser("forecast", help="inflow forecasting: dataset, models, scores")
    p.add_argument("--net", default="grid3x3")
    p.add_argument("--seeds", type=int, default=4, help="runs per demand level")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_forecast)

    p = sub.add_parser("explain", help="decision log and feature-group importance of a policy")
    p.add_argument("--agent", default="coop_full")
    p.add_argument("--net", default="grid3x3")
    p.add_argument(
        "--checkpoint", default=None, help="default: results/checkpoints/<agent>/<net>/seed1.zip"
    )
    p.add_argument("--demand", default="peak")
    p.add_argument("--scenarios", nargs="*", default=["emergency"])
    p.add_argument("--seed", type=int, default=3)
    p.add_argument("--importance-seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    p.add_argument("--no-importance", action="store_true")
    p.add_argument("--offline", action="store_true", help="skip the online replays (faster)")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("figures", help="report figures into figures/ (PNG + SVG)")
    p.set_defaults(func=cmd_figures)

    p = sub.add_parser("tables", help="write results/summary/REPORT_TABLES.md")
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser("ask", help="question about the results, answered in French")
    p.add_argument("question", nargs="+")
    p.add_argument("--no-llm", action="store_true", help="keywords and fixed sentences only")
    p.add_argument("--fast", action="store_true", help="the model reads the question only")
    p.add_argument("--table", action="store_true", help="also print the table of values")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("demo-plan", help="side-by-side demo described in plain words")
    p.add_argument("request", nargs="+")
    p.add_argument("--no-llm", action="store_true", help="keywords only")
    p.add_argument("--run", action="store_true", help="launch the demo")
    p.set_defaults(func=cmd_demo_plan)

    p = sub.add_parser("llm-status", help="is the local language model (Ollama) ready?")
    p.set_defaults(func=cmd_llm_status)

    p = sub.add_parser("smoke", help="quick end-to-end check of every feature")
    p.add_argument("--only", nargs="*", default=None, help="run only these checks")
    p.set_defaults(func=cmd_smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # French text and symbols on a Windows console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
