"""Network-level schedules of modes (controllers/schedule.py), for the strategy oracle."""

from types import SimpleNamespace

import pytest
from test_combined import OBS, FixedLogits
from test_hybrid import FixedMp

from cotraffic.controllers.hybrid import CongestionStrategy
from cotraffic.controllers.schedule import ScheduledPolicy, ScheduleStrategy

LOGITS = [[2.0, 0.0], [0.0, 1.0]]  # COOP-FULL alone: A0 -> 0, B0 -> 1; Max-Pressure: 1, 0


def env_at(now: float):
    return SimpleNamespace(now=now, intersections={"A0": None, "B0": None}, ev_ids=set())


def policy(schedule, mix=("h2", 3.0)):
    p = ScheduledPolicy(FixedLogits(LOGITS), schedule, mix, window_s=300.0)
    p.mp = FixedMp({"A0": 1, "B0": 0})
    p.ev_guide = None  # no emergency vehicle in these tests
    return p


def test_schedule_gives_one_mode_per_window_then_coop():
    s = ScheduleStrategy(["mp", "coop", "mix"], window_s=300.0)
    assert [s.mode_at(t) for t in (0, 299, 300, 650, 900, 5000)] == [
        "mp", "mp", "coop", "mix", "coop", "coop"
    ]  # fmt: skip
    assert s.modes(env_at(10)) == {"A0": "mp", "B0": "mp"}
    assert s.modes(env_at(310)) == {}
    assert s.summary()["windows_mp"] == 0.3333  # rounded to 4 decimals
    with pytest.raises(ValueError):
        ScheduleStrategy(["coop", "llm"])


def test_scheduled_policy_switches_mode_at_window_boundaries():
    p = policy(["coop", "mp", "mix"])  # mix = H2, beta 3: both junctions follow Max-Pressure
    assert p.act(env_at(0), OBS) == {"A0": 0, "B0": 1}
    assert p.act(env_at(300), OBS) == {"A0": 1, "B0": 0}
    assert p.act(env_at(600), OBS) == {"A0": 1, "B0": 0}
    assert p.mp_beta == 3.0
    assert p.act(env_at(900), OBS) == {"A0": 0, "B0": 1} and p.mp_beta == 0.0
    s = p.summary()
    assert s["share_coop"] == 0.5 and s["share_mp"] == 0.25 and s["share_mix"] == 0.25
    assert s["mix"] == "h2:3"


def test_mix_is_h1_with_a_threshold_or_h2_with_a_beta():
    p = policy(["coop"], mix=("h1", 0.5))
    assert isinstance(p.strategy.h1, CongestionStrategy) and p.strategy.h1.threshold == 0.5
    assert policy(["coop"]).strategy.h1 is None
    with pytest.raises(ValueError):
        ScheduledPolicy(FixedLogits(LOGITS), [], ("h3", 1.0))


@pytest.mark.sumo
def test_oracle_replays_follow_the_planned_trajectory():
    """Played again in a new environment, the oracle's schedule gives the cumulated halting
    planned at the start of every window: the planned trajectory is the measured one."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from strategy_oracle import TracedPolicy, plan

    from cotraffic.controllers.registry import make_controller
    from cotraffic.llm.rollout import EpisodeSpec, make_env
    from cotraffic.paths import CHECKPOINTS_DIR

    checkpoint = CHECKPOINTS_DIR / "coop_full" / "grid4x4" / "seed1.zip"
    if not checkpoint.is_file():
        pytest.skip("COOP-FULL checkpoint not available")
    task = ("grid4x4", "emergency", "peak", 1000, 1, "h2:2", 600.0, 300.0)
    p = plan(task, mode="quick")
    assert len(p["schedule"]) == len(p["costs"]) == 2  # 1200 s in windows of 600 s
    base = make_controller("coop_full", checkpoint)
    policy = TracedPolicy(base, p["schedule"], p["mix"], 600.0)
    env = make_env(EpisodeSpec("grid4x4", "peak", ["emergency"], 1000, "quick"), base.agent_cfg)
    try:
        obs, _ = env.reset(seed=1000)
        policy.reset(env)
        while env.agents and env.now < 1200:
            obs, *_ = env.step(policy.act(env, obs))
    finally:
        env.close()
    assert policy.trace[: len(p["trace"])] == p["trace"]
