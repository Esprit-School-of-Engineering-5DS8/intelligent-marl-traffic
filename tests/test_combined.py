"""COOP-FULL guided during emergencies (controllers/combined.py): A' (bias), B' (switch)."""

from types import SimpleNamespace

import pytest
from test_llm_team_controller import FakeEnv

from cotraffic.controllers.combined import EvRuleGuide, GuidedPolicy, TeamGuide
from cotraffic.envs.ev import EVState, UpcomingTLS


class FixedLogits:
    """A PPO stand-in with fixed logits (one row per agent, in observation order)."""

    def __init__(self, logits):
        import torch

        self.logits = torch.tensor(logits)
        self.model = SimpleNamespace(policy=self)
        self.agent_cfg, self.name = {}, "coop_full"

    def obs_to_tensor(self, batch):
        return batch, None

    def get_distribution(self, obs):
        return SimpleNamespace(distribution=SimpleNamespace(logits=self.logits))

    def reset(self, env):
        pass


class FixedGuide:
    name = "fixed"

    def __init__(self, requests):
        self.requested = requests

    def reset(self, env):
        pass

    def requests(self, env):
        return dict(self.requested)

    def summary(self):
        return {}


OBS = {"A0": [0.0], "B0": [0.0]}
LOGITS = [[2.0, 0.0], [0.0, 1.0]]  # PPO alone: A0 -> 0, B0 -> 1


def test_without_requests_the_policy_is_ppo_alone():
    policy = GuidedPolicy(FixedLogits(LOGITS), FixedGuide({}), "bias", 16.0)
    assert policy.act(None, OBS) == {"A0": 0, "B0": 1}
    assert policy.guided_decisions == policy.changed_decisions == 0


def test_bias_moves_the_decision_only_when_beta_beats_the_logit_gap():
    weak = GuidedPolicy(FixedLogits(LOGITS), FixedGuide({"A0": 1}), "bias", 1.0)
    assert weak.act(None, OBS) == {"A0": 0, "B0": 1}  # gap 2 > beta 1: PPO keeps phase 0
    assert weak.guided_decisions == 1 and weak.changed_decisions == 0
    strong = GuidedPolicy(FixedLogits(LOGITS), FixedGuide({"A0": 1}), "bias", 4.0)
    assert strong.act(None, OBS) == {"A0": 1, "B0": 1}
    assert strong.changed_decisions == 1 and strong.summary()["beta"] == 4.0


def test_switch_takes_the_guided_phase_at_guided_junctions_only():
    # switching needs no beta (the evaluation passes None)
    policy = GuidedPolicy(FixedLogits(LOGITS), FixedGuide({"A0": 1, "Z9": 0}), "switch", None)
    assert policy.act(None, OBS) == {"A0": 1, "B0": 1}
    assert policy.summary()["guide_mode"] == "switch" and policy.changed_decisions == 1
    assert policy.summary()["beta"] == ""
    with pytest.raises(ValueError):
        GuidedPolicy(FixedLogits(LOGITS), FixedGuide({}), "vote")
    with pytest.raises(ValueError):
        GuidedPolicy(FixedLogits(LOGITS), FixedGuide({}), "bias", None)


def test_team_guide_guides_only_during_its_preemption_windows():
    env = FakeEnv()
    guide = TeamGuide()
    guide.reset(env)
    assert guide.requests(env) == {}  # no emergency vehicle: no guidance at all
    env.now = 5.0
    env.ev_states = [EVState("ev0", "edge", "lane", 10.0, (UpcomingTLS("B0", 2, 20.0, "r"),))]
    requested = guide.requests(env)
    assert list(requested) == ["B0"] and 0 <= requested["B0"] < 3
    assert guide.summary()["guide_preemptions"] >= 1


def test_ev_rule_guide_claims_the_vehicle_phase_within_range():
    inter = SimpleNamespace(green_states=["GGrr", "rrGG"])
    tls = {"ev0": [("A0", 2, 120.0, "r")], "ev1": [("B0", 0, 900.0, "r")]}
    env = SimpleNamespace(
        protocol={"baselines": {"ev_preemption_range_m": 200}},
        intersections={"A0": inter, "B0": inter},
        ev_ids={"ev0", "ev1"},
        conn=SimpleNamespace(vehicle=SimpleNamespace(getNextTLS=lambda ev: tls[ev])),
    )
    guide = EvRuleGuide()
    guide.reset(env)
    assert guide.requests(env) == {"A0": 1}  # B0's vehicle is beyond 200 m
    guide.requests(env)
    assert guide.summary()["guide_preemptions"] == 1


@pytest.mark.sumo
def test_guided_coop_full_is_coop_full_until_an_emergency_vehicle_comes():
    from cotraffic.controllers.registry import make_controller
    from cotraffic.llm.rollout import EpisodeSpec, make_env
    from cotraffic.paths import CHECKPOINTS_DIR

    checkpoint = CHECKPOINTS_DIR / "coop_full" / "grid4x4" / "seed1.zip"
    if not checkpoint.is_file():
        pytest.skip("COOP-FULL checkpoint not available")
    base = make_controller("coop_full", checkpoint)
    alone = make_controller("coop_full", checkpoint)
    policy = GuidedPolicy(base, TeamGuide(), "switch")
    spec = EpisodeSpec("grid4x4", "peak", ["emergency"], 1000, mode="quick")
    env = make_env(spec, base.agent_cfg)
    try:
        obs, _ = env.reset(seed=1000)
        policy.reset(env)
        alone.reset(env)
        while env.now < 1200 and policy.guided_decisions == 0:
            expected = alone.act(env, obs)
            actions = policy.act(env, obs)
            if policy.guided_decisions == 0:
                assert {k: int(v) for k, v in expected.items()} == actions
            obs, *_ = env.step(actions)
    finally:
        env.close()
    assert policy.guided_decisions > 0
