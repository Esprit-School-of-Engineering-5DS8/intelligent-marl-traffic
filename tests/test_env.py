import numpy as np
import pytest

from cotraffic.envs.episodes import TrainingEpisodes
from cotraffic.envs.observations import block_slices
from cotraffic.envs.traffic_env import CoTrafficEnv
from cotraffic.evaluation.quick import FULL_OBSERVATION

pytestmark = pytest.mark.sumo


@pytest.fixture
def env():
    e = CoTrafficEnv(
        "grid2x2", TrainingEpisodes("grid2x2", ["peak"], episode_s=400), FULL_OBSERVATION
    )
    yield e
    e.close()


def test_spaces_and_bounds(env):
    obs, _ = env.reset(seed=0)
    assert set(obs) == set(env.possible_agents) == {"A0", "A1", "B0", "B1"}
    space = env.observation_space("A0")
    rng = np.random.default_rng(0)
    while env.agents:
        obs, rewards, term, trunc, _ = env.step({a: int(rng.integers(2)) for a in env.agents})
        for o in obs.values():
            assert space.contains(o)
        assert all(-5.0 <= r <= 5.0 for r in rewards.values())
    assert all(trunc.values()) and not any(term.values())


def test_block_layout_matches_observation_size(env):
    slices = block_slices(env.obs_cfg, env.pad)
    assert list(slices) == ["lanes", "phase", "neighbours", "emergency", "pedestrians", "buses"]
    assert max(s.stop for s in slices.values()) == env.builder.size


def test_signal_sequence_is_safe(env):
    """Replay the real signal states: lost greens go through yellow, greens last >= min green."""
    env.reset(seed=1)
    conn = env.conn
    tls = "A0"
    history = []
    rng = np.random.default_rng(3)
    min_green = env.timing["min_green"]

    def record(e, now):
        history.append((now, conn.trafficlight.getRedYellowGreenState(tls)))

    env.step_hooks.append(record)
    while env.agents:
        env.step({a: int(rng.integers(2)) for a in env.agents})

    crossings = env.intersections[tls].crossing_signals
    green_start = 0.0
    for (_, s0), (t1, s1) in zip(history, history[1:], strict=False):
        for i, (a, b) in enumerate(zip(s0, s1, strict=True)):
            if a in "Gg" and b in "rs" and i not in crossings:
                pytest.fail(f"signal {i} went from green to red without yellow at t={t1}")
        if "y" in s1 and "y" not in s0:
            assert t1 - green_start >= min_green, f"green of {t1 - green_start}s at t={t1}"
        if "y" in s0 and "y" not in s1:
            green_start = t1
    assert any("y" in s for _, s in history), "no phase change happened"


def test_uncontrolled_mode_leaves_sumo_program_running():
    e = CoTrafficEnv(
        "grid2x2",
        TrainingEpisodes("grid2x2", ["low"], episode_s=200),
        controlled=False,
        compute_observations=False,
    )
    try:
        e.reset(seed=0)
        program = e.conn.trafficlight.getProgram("A0")
        while e.agents:
            e.step(None)
        assert program == "0" and e.stats["decisions"] == 0
    finally:
        e.close()
