"""Snapshots: two restorations of the same situation replay identically (paired rollouts)."""

import pytest

from cotraffic.controllers.registry import make_controller
from cotraffic.llm.rollout import EpisodeSpec, make_env
from cotraffic.llm.snapshot import restore, take
from cotraffic.paths import CHECKPOINTS_DIR

pytestmark = pytest.mark.sumo


def test_two_restorations_replay_identically(tmp_path):
    checkpoint = CHECKPOINTS_DIR / "coop_full" / "grid4x4" / "seed1.zip"
    if not checkpoint.is_file():
        pytest.skip("COOP-FULL checkpoint not available")
    policy = make_controller("coop_full", checkpoint)
    spec = EpisodeSpec("grid4x4", "peak", ["emergency", "sensor_noise"], 1000, mode="validation")
    env = make_env(spec, policy.agent_cfg)

    def run(obs, seconds):
        end = env.now + seconds
        trace = []
        while env.now < end:
            obs, *_ = env.step(policy.act(env, obs))
            trace.append(
                (env.now, env.halting_sum, tuple(i.phase for i in env.intersections.values()))
            )
        return trace

    try:
        obs, _ = env.reset(seed=spec.seed)
        policy.reset(env)
        while env.now < 200:
            obs, *_ = env.step(policy.act(env, obs))
        snap = take(env, tmp_path, "s200", obs)
        traces = []
        for _ in range(2):
            env.reset(seed=spec.seed)
            policy.reset(env)
            traces.append(run(restore(env, snap), 100))
        assert traces[0] == traces[1]
        assert traces[0][0][0] == 205.0
    finally:
        env.close()
