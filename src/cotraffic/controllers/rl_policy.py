"""A trained policy (PPO or DQN) used as a controller (deterministic actions, all agents
batched)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from cotraffic import config
from cotraffic.controllers.base import Controller


def checkpoint_agent_config(method: str, checkpoint: Path) -> dict[str, Any]:
    """Agent config stored next to a selected checkpoint, else the current config file."""
    sidecar = Path(checkpoint).with_suffix(".json")
    if sidecar.is_file():
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        if "config" in data:
            return data["config"]
    return config.load_agent(method)


class LearnedPolicy(Controller):
    needs_observations = True

    def __init__(self, method: str, checkpoint: Path) -> None:
        super().__init__()
        from cotraffic.training.train import algorithm_class

        self.name = method
        self.checkpoint = Path(checkpoint)
        if not self.checkpoint.is_file():
            raise FileNotFoundError(f"checkpoint not found: {self.checkpoint}")
        self.agent_cfg = checkpoint_agent_config(method, self.checkpoint)
        algorithm = algorithm_class(self.agent_cfg.get("algorithm", "ppo"))
        self.model = algorithm.load(self.checkpoint, device="cpu")

    def reset(self, env) -> None:
        from cotraffic.forecasting.online import attach_forecaster

        attach_forecaster(env, env.network)
        expected = self.model.observation_space.shape
        if env.observation_space(env.possible_agents[0]).shape != expected:
            raise ValueError(
                f"{self.checkpoint.name} expects observations of shape {expected}, "
                f"network {env.network} gives {env.observation_space(env.possible_agents[0]).shape}"
            )

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        agents = list(obs)
        actions, _ = self.model.predict(np.stack([obs[a] for a in agents]), deterministic=True)
        return {a: int(x) for a, x in zip(agents, actions, strict=True)}
