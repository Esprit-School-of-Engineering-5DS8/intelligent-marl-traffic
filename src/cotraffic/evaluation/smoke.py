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
    row = _quick("mp", "real_district", ["incident", "emergency", "buses", "pedestrians"])
    assert row["ev_count"] > 0 and row["bus_count"] > 0 and row["incident_start"] != ""
    return f"7 signals, all route scenarios: travel time {row['mean_travel_time']:.0f}s"


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


def run_smoke(only: list[str] | None = None) -> int:
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
