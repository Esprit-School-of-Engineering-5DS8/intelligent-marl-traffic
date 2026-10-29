"""The layered controller (controllers/hybrid.py): strategy, tactics, pre-emption."""

from types import SimpleNamespace

import pytest
from test_combined import OBS, FixedGuide, FixedLogits
from test_llm_team_controller import FakeEnv

from cotraffic.controllers.hybrid import (
    BacklogStrategy,
    CongestionStrategy,
    HybridPolicy,
    PedRuleGuide,
    TeamRoleGuide,
    neighbourhood_queue,
)
from cotraffic.envs.ev import EVState, UpcomingTLS

LOGITS = [[2.0, 0.0], [0.0, 1.0]]  # COOP-FULL alone: A0 -> 0, B0 -> 1


class FixedMp:
    def __init__(self, actions):
        self.actions = actions

    def reset(self, env):
        pass

    def act(self, env, obs):
        return dict(self.actions)


class FixedModes:
    name = "fixed"

    def __init__(self, modes):
        self._modes = modes

    def reset(self, env):
        pass

    def modes(self, env):
        return dict(self._modes)

    def summary(self):
        return {}


def policy(**kw):
    p = HybridPolicy(FixedLogits(LOGITS), **kw)
    p.mp = FixedMp({"A0": 1, "B0": 0})
    return p


def test_coop_mode_without_guides_is_coop_full():
    p = policy()
    assert p.act(None, OBS) == {"A0": 0, "B0": 1}
    assert p.summary()["share_coop"] == 1.0 and p.changed_decisions == 0


def test_mp_mode_takes_max_pressure_phase_at_its_junctions_only():
    p = policy(strategy=FixedModes({"A0": "mp", "B0": "coop"}))
    assert p.act(None, OBS) == {"A0": 1, "B0": 1}
    s = p.summary()
    assert s["share_mp"] == 0.5 and s["share_coop"] == 0.5 and p.changed_decisions == 1


def test_mp_bias_moves_a_decision_only_beyond_the_logit_gap():
    weak = policy(mp_beta=0.5)  # A0 gap 2, B0 gap 1: nothing moves
    assert weak.act(None, OBS) == {"A0": 0, "B0": 1} and weak.mix_changed == 0
    strong = policy(mp_beta=3.0)  # both junctions follow Max-Pressure
    assert strong.act(None, OBS) == {"A0": 1, "B0": 0}
    assert strong.mix_changed == 2 and strong.summary()["share_mix"] == 1.0


def test_emergency_preemption_takes_precedence_over_pedestrians_and_modes():
    p = policy(
        strategy=FixedModes({"A0": "mp", "B0": "mp"}),
        ped_guide=FixedGuide({"A0": 1, "B0": 1}),
        ev_guide=FixedGuide({"A0": 0}),
    )
    assert p.act(None, OBS) == {"A0": 0, "B0": 1}
    s = p.summary()
    assert s["share_ev"] == 0.5 and s["share_ped"] == 0.5 and s["share_mp"] == 0.0


def env_with_queues(queues, now=0.0):
    inters = {t: SimpleNamespace(in_lanes=[t]) for t in queues}
    links = {"A0": {"E": ("B0", [], frozenset())}, "B0": {"W": ("A0", [], frozenset())}}
    meas = SimpleNamespace(queue=lambda lanes: queues[lanes[0]])
    return SimpleNamespace(intersections=inters, meas=meas, neighbour_links=links, now=now)


def test_neighbourhood_queue_is_the_largest_around_a_junction():
    env = env_with_queues({"A0": 0.1, "B0": 0.7, "C0": 0.2})
    assert neighbourhood_queue(env) == {"A0": 0.7, "B0": 0.7, "C0": 0.2}


def test_congestion_strategy_decides_every_period_on_the_last_minute():
    queues = {"A0": 0.1, "B0": 0.6, "C0": 0.1}
    env = env_with_queues(queues)
    s = CongestionStrategy(threshold=0.5, period_s=300.0, window_s=60.0)
    s.reset(env)
    assert s.modes(env) == {"A0": "mp", "B0": "mp", "C0": "coop"}  # A0 next to B0
    queues["B0"] = 0.0
    for t in (100.0, 200.0, 295.0):  # inside the period: the modes are kept
        env.now = t
        assert s.modes(env)["B0"] == "mp"
    env.now = 300.0
    assert s.modes(env) == {"A0": "coop", "B0": "coop", "C0": "coop"}
    assert s.summary()["mode_switches"] == 4  # A0, B0 to Max-Pressure, then back


def test_team_role_guide_keeps_only_its_roles():
    env = FakeEnv()
    env.now = 5.0
    env.ev_states = [EVState("ev0", "edge", "lane", 10.0, (UpcomingTLS("B0", 2, 20.0, "r"),))]
    emergency, pedestrian = TeamRoleGuide(("emergency",)), TeamRoleGuide(("pedestrian",))
    emergency.reset(env)
    pedestrian.reset(env)
    assert list(emergency.requests(env)) == ["B0"]
    assert pedestrian.requests(env) == {}  # no pedestrian waiting, and no emergency role
    assert pedestrian.name == "team_pedestrian"


def test_ped_rule_guide_serves_a_crossing_after_the_wait():
    link = SimpleNamespace(crossing=":c0", index=2)
    inter = SimpleNamespace(
        crossing_links=[link],
        phase_links=[frozenset({0, 1}), frozenset({2, 3})],
        phase=0,
        in_yellow=False,
        green_states=["GGrr", "rrGG"],
    )
    waits = {"p1": 35.0, "p2": 5.0}
    env = SimpleNamespace(
        protocol={"baselines": {"ped_rule_wait_s": 30}},
        intersections={"A0": inter},
        person_ids=set(waits),
        walkingareas={":w0"},
        crossing_owner={":c0": "A0"},
        conn=SimpleNamespace(
            person=SimpleNamespace(
                getRoadID=lambda p: ":w0",
                getWaitingTime=lambda p: waits[p],
                getNextEdge=lambda p: ":c0",
            )
        ),
    )
    guide = PedRuleGuide()
    guide.reset(env)
    assert guide.requests(env) == {"A0": 1}
    waits["p1"] = 10.0
    assert guide.requests(env) == {}


@pytest.mark.sumo
def test_hybrid_in_max_pressure_mode_everywhere_requests_what_max_pressure_requests():
    from cotraffic.controllers.classical import MaxPressure
    from cotraffic.controllers.registry import make_controller
    from cotraffic.llm.rollout import EpisodeSpec, make_env
    from cotraffic.paths import CHECKPOINTS_DIR

    checkpoint = CHECKPOINTS_DIR / "coop_full" / "grid4x4" / "seed1.zip"
    if not checkpoint.is_file():
        pytest.skip("COOP-FULL checkpoint not available")
    base = make_controller("coop_full", checkpoint)
    hybrid = HybridPolicy(base, CongestionStrategy(threshold=0.0))  # every junction congested
    mp = MaxPressure()
    env = make_env(EpisodeSpec("grid4x4", "peak", [], 1000), base.agent_cfg)
    try:
        obs, _ = env.reset(seed=1000)
        hybrid.reset(env)
        mp.reset(env)
        while env.now < 300:
            expected = {k: int(v) for k, v in mp.act(env, obs).items()}
            actions = hybrid.act(env, obs)
            assert actions == expected
            obs, *_ = env.step(actions)
    finally:
        env.close()
    assert hybrid.summary()["share_mp"] == 1.0


def backlog_env(now: float, pending: int):
    sim = SimpleNamespace(getPendingVehicles=lambda: [f"v{i}" for i in range(pending)])
    return SimpleNamespace(
        now=now, intersections={"A0": None, "B0": None}, conn=SimpleNamespace(simulation=sim)
    )


def test_backlog_strategy_puts_the_whole_network_in_mp_while_the_entrance_queue_is_long():
    s = BacklogStrategy(threshold=2.0, period_s=300.0, window_s=60.0)
    s.reset(backlog_env(0, 0))
    assert s.modes(backlog_env(0, 5)) == {"A0": "mp", "B0": "mp"}  # 5 vehicles > 2
    for t in range(5, 300, 5):  # held for the period, whatever the queue
        assert s.modes(backlog_env(t, 0)) == {"A0": "mp", "B0": "mp"}
    assert s.modes(backlog_env(300, 2)) == {}  # mean of the last minute 2/13: COOP-FULL mode
    assert s.summary() == {
        "threshold": 2.0, "period_s": 300.0, "mode_switches": 2, "periods_mp": 0.5
    }  # fmt: skip
    s.reset(backlog_env(0, 0))
    assert s.modes(backlog_env(0, 2)) == {}  # equal to the threshold: not above it


class FixedAdvisor:
    """An LLM advice of phase 1 at A0, strong enough to change COOP-FULL's choice there."""

    def reset(self, env):
        pass

    def bias_logits(self, env, agents, logits):
        out = logits.copy()
        out[agents.index("A0"), 1] += 10.0
        return out

    def summary(self):
        return {"llm_calls": 0}


def test_llm_advice_moves_coop_full_but_not_max_pressure_nor_pre_emption():
    p = policy(advisor=FixedAdvisor())
    assert p.act(None, OBS) == {"A0": 1, "B0": 1}  # COOP-FULL alone: A0 -> 0
    assert p.changed_decisions == 1 and p.summary()["llm_calls"] == 0
    p = policy(strategy=FixedModes({"A0": "mp"}), advisor=FixedAdvisor())
    p.mp = FixedMp({"A0": 0, "B0": 0})
    assert p.act(None, OBS)["A0"] == 0  # Max-Pressure decides there, without the advice
    p = policy(ev_guide=FixedGuide({"A0": 0}), advisor=FixedAdvisor())
    assert p.act(None, OBS)["A0"] == 0  # the emergency vehicle first
    assert policy().advisor is None  # without an advisor: the controller of phase A
