"""Quick end-to-end checks of every feature (``make smoke``).

Each check runs in minutes at most and raises on failure. New features register a
check here so that the smoke run is also a regression test of everything before.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable

CHECKS: dict[str, Callable[[], str]] = {}


def check(name: str):
    def register(fn: Callable[[], str]) -> Callable[[], str]:
        CHECKS[name] = fn
        return fn

    return register


@check("networks")
def _networks() -> str:
    from cotraffic.networks.build import ensure_network

    return ", ".join(ensure_network(n).name for n in ("grid2x2", "grid4x4", "grid8x8"))


@check("random_episode")
def _random_episode() -> str:
    from cotraffic.evaluation.quick import random_episode

    s = random_episode(
        "grid2x2", "medium", 600, seed=0, scenarios=["emergency", "pedestrians", "buses"]
    )
    assert s["decisions"] > 0 and s["sim_time"] >= 600, s
    return f"{s['decisions']} decisions, {s['switches']} switches, {s['wall_time_s']:.1f}s wall"


@check("pettingzoo_api")
def _pettingzoo_api() -> str:
    from pettingzoo.test import parallel_api_test

    from cotraffic.envs.episodes import TrainingEpisodes
    from cotraffic.envs.traffic_env import CoTrafficEnv
    from cotraffic.evaluation.quick import FULL_OBSERVATION

    env = CoTrafficEnv(
        "grid2x2", TrainingEpisodes("grid2x2", ["low"], episode_s=300), FULL_OBSERVATION
    )
    try:
        parallel_api_test(env, num_cycles=40)
    finally:
        env.close()
    return "parallel_api_test passed"


CORE_METRICS = (
    "mean_travel_time",
    "mean_waiting_time",
    "mean_queue",
    "throughput_per_h",
    "co2_g_per_km",
    "person_weighted_delay",
    "gini_waiting_time",
)


def _quick(
    method: str, network: str, scenarios: list[str], demand: str = "medium", controller=None
) -> dict:
    """One quick-mode evaluation run whose row must be complete and plausible."""
    import math

    from cotraffic.evaluation.runner import run_episode
    from cotraffic.paths import RESULTS_DIR

    row = run_episode(
        method,
        network,
        demand,
        scenarios,
        seed=7,
        quick=True,
        raw_dir=RESULTS_DIR / "tmp" / "smoke_raw",
        logs_dir=RESULTS_DIR / "tmp" / "smoke_logs",
        controller=controller,
    )
    for key in CORE_METRICS:
        value = float(row[key])
        assert not math.isnan(value), f"{method} {scenarios}: {key} is NaN"
    assert row["mean_travel_time"] > 0 and row["throughput_per_h"] > 0, row
    return row


@check("real_district")
def _real_district() -> str:
    from cotraffic.networks.build import ensure_network

    ensure_network("real_district")
    # no pedestrians on the district: its OpenStreetMap import has almost no sidewalks
    # (FAILURES F-011); evaluation refuses that scenario there
    row = _quick("mp", "real_district", ["incident", "emergency", "buses"])
    assert row["ev_count"] > 0 and row["bus_count"] > 0 and row["incident_start"] != ""
    return f"7 signals, incident + emergency + buses: travel time {row['mean_travel_time']:.0f}s"


@check("scenarios_grid4x4")
def _scenarios() -> str:
    from cotraffic.controllers.random_policy import RandomPolicy
    from cotraffic.evaluation.quick import FULL_OBSERVATION

    checks = {
        "normal": lambda r: True,
        "incident": lambda r: r["incident_start"] != "",
        "emergency": lambda r: r["ev_count"] >= 3,
        "pedestrians": lambda r: r["ped_count"] > 0,
        "buses": lambda r: r["bus_count"] > 0,
    }
    for scenario, ok in checks.items():
        row = _quick("mp", "grid4x4", [scenario])
        assert ok(row), f"scenario {scenario} had no effect: {row}"
    for scenario in ("sensor_noise", "comm_dropout_30"):
        ctrl = RandomPolicy()
        ctrl.agent_cfg = FULL_OBSERVATION
        ctrl.needs_observations = True
        row = _quick("random", "grid4x4", [scenario], controller=ctrl)
    assert row["messages_lost"] > 0, "comm dropout lost no message"
    return f"{len(checks) + 2} scenarios"


@check("baselines")
def _baselines() -> str:
    parts = []
    for method in ("ft", "act", "mp", "ev_rule"):
        row = _quick(method, "grid4x4", ["emergency"], demand="peak")
        parts.append(f"{method} {row['mean_travel_time']:.0f}s")
    return ", ".join(parts)


@check("training")
def _training() -> str:
    """Quick PPO run, resume from its checkpoint, then evaluate the policy."""
    import shutil

    from cotraffic.training.train import list_checkpoints, run_dir, train

    folder = run_dir("coop", "grid2x2", 0) / "quick"
    shutil.rmtree(folder, ignore_errors=True)
    train("coop", "grid2x2", 0, quick=True, total_timesteps=1024)
    train("coop", "grid2x2", 0, quick=True, total_timesteps=2048)
    steps = [s for s, _ in list_checkpoints(folder / "checkpoints")]
    assert steps and steps[-1] >= 2048, steps
    from cotraffic.controllers.rl_policy import LearnedPolicy

    ctrl = LearnedPolicy("coop", list_checkpoints(folder / "checkpoints")[-1][1])
    row = _quick("coop", "grid2x2", ["emergency"], controller=ctrl)
    from cotraffic.explainability.explain import explain_episode

    log = explain_episode(
        "coop", ctrl.checkpoint, "grid2x2", "medium", ["emergency"], 7, max_rows=200
    )
    assert log.is_file()
    log.unlink()
    shutil.rmtree(folder, ignore_errors=True)
    return f"trained to {steps[-1]} steps with resume, evaluated: {row['mean_travel_time']:.0f}s"


@check("analysis")
def _analysis() -> str:
    """Quick matrix -> statistics -> report tables -> figures, in a temporary folder."""
    import shutil

    from cotraffic.analysis.aggregate import run_aggregate
    from cotraffic.analysis.figures import build_figures
    from cotraffic.analysis.tables import build_report_tables
    from cotraffic.evaluation.matrix import run_matrix
    from cotraffic.paths import RESULTS_DIR

    assert run_matrix("quick", jobs=2) == 0
    raw, logs = RESULTS_DIR / "tmp" / "quick_raw", RESULTS_DIR / "tmp" / "quick_logs"
    out = RESULTS_DIR / "tmp" / "smoke_summary"
    shutil.rmtree(out, ignore_errors=True)
    run_aggregate(raw, out, allow_quick=True)
    tables = build_report_tables(raw, out)
    report = build_figures(raw, logs, out / "figures", allow_quick=True)
    drawn = [line for line in report if "skipped" not in line]
    assert tables.is_file() and any("fig02" in line for line in drawn), report
    return f"tables + {len(drawn)} figures from the quick matrix"


@check("forecast")
def _forecast() -> str:
    import pandas as pd

    from cotraffic.forecasting.dataset import build_dataset
    from cotraffic.forecasting.models import evaluate
    from cotraffic.paths import RESULTS_DIR

    work = RESULTS_DIR / "tmp" / "smoke_forecast"
    build_dataset("grid2x2", seeds_per_level=1, jobs=2, mode="validation", out_dir=work)
    scores = pd.read_csv(evaluate("grid2x2", work, work))
    assert scores["mae"].notna().all() and len(scores["model"].unique()) == 4
    return f"{len(scores)} scores for 4 models"


@check("assistant")
def _assistant() -> str:
    """Questions and demo requests answered from the result files, without a language model
    (the fallback path every answer can take)."""
    from cotraffic.assistant.ask import ask
    from cotraffic.assistant.scenario import plan_demo

    reply = ask("Quel est le meilleur contrôleur à la pointe sur la grille ?", llm=None)
    assert reply.finding.found and reply.finding.table is not None, reply.text
    plan = plan_demo("MP contre COOP-FULL à Tunis avec un accident et des piétons", llm=None)
    assert plan.spec.network == "real_district_ped" and "--follow-incident" in plan.command
    return f"best on grid4x4 peak: {reply.finding.table.iloc[0, 0]}; demo: {plan.spec.network}"


@check("dashboard")
def _dashboard() -> str:
    """The FastAPI backend the dashboard calls answers health, policy and the catalog."""
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200 and health.json()["ok"] is True, health.text
        policy = client.get("/api/policy")
        assert policy.status_code == 200, policy.text
        body = policy.json()
        assert body["available"] is True, body
        methods = {item["method"] for item in body["catalog"]}
        assert {"mp", "coop", "llm"} <= methods, methods
    return f"api ok, policy {body['method']} on {body['network']}"


def run_smoke(only: list[str] | None = None) -> int:
    # All checks share one process. pandas and scikit-learn import pyarrow, whose DLLs
    # clash with the Arrow library bundled in libsumo once libsumo is loaded; load them
    # before the first simulation, as the single-purpose commands do.
    import pandas  # noqa: F401
    import sklearn  # noqa: F401

    failures = 0
    for name, fn in CHECKS.items():
        if only and name not in only:
            continue
        start = time.perf_counter()
        try:
            msg = fn()
            print(f"[ ok ] {name:<22} {time.perf_counter() - start:6.1f}s  {msg}")
        except Exception:  # noqa: BLE001 - every failure must be reported, not raised mid-run
            failures += 1
            print(f"[FAIL] {name:<22} {time.perf_counter() - start:6.1f}s")
            traceback.print_exc()
    print(f"smoke: {failures} failure(s)")
    return 1 if failures else 0
