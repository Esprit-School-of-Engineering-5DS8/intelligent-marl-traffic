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

    return ", ".join(ensure_network(n).name for n in ("grid2x2", "grid4x4"))


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
