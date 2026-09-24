"""Short sanity-check episodes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from cotraffic.envs.episodes import TrainingEpisodes
from cotraffic.envs.traffic_env import CoTrafficEnv

FULL_OBSERVATION = {
    "observation": {"neighbours": True, "emergency": True, "pedestrians": True, "buses": True},
    "reward": {"person_weighted": True, "co2": 0.5, "ev": 1.0, "ped": 0.2},
}


def random_episode(
    network: str, demand: str, seconds: float, seed: int = 0, scenarios: Sequence[str] = ()
) -> dict[str, Any]:
    """Uniformly random phase requests (filtered by the shield) for ``seconds``."""
    episodes = TrainingEpisodes(network, [demand], scenarios, episode_s=seconds)
    env = CoTrafficEnv(network, episodes, FULL_OBSERVATION)
    rng = np.random.default_rng(seed)
    try:
        obs, _ = env.reset(seed=seed)
        dims = {int(o.shape[0]) for o in obs.values()}
        summary: dict[str, Any] = {}
        while env.agents:
            actions = {a: int(rng.integers(env.action_space(a).n)) for a in env.agents}
            obs, _rewards, _term, _trunc, infos = env.step(actions)
            for o in obs.values():
                if not np.all(np.isfinite(o)):
                    raise ValueError("non-finite observation")
            summary = next(iter(infos.values())).get("episode_summary", summary)
        summary["agents"] = len(env.possible_agents)
        summary["obs_dim"] = sorted(dims)
        return summary
    finally:
        env.close()
