"""A trained policy (PPO or DQN) used as a controller (deterministic actions, all agents
batched)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from cotraffic import config
from cotraffic.controllers.base import Controller
from cotraffic.recipes import normalize_recipe


def checkpoint_agent_config(method: str, checkpoint: Path) -> dict[str, Any]:
    """Agent config stored next to a selected checkpoint, else the current config file."""
    checkpoint = Path(checkpoint)
    sidecars = (checkpoint.with_suffix(".json"), Path(str(checkpoint) + ".json"))
    for sidecar in sidecars:
        if sidecar.is_file():
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if "config" in data:
                return data["config"]
    try:
        return config.load_agent(method)
    except FileNotFoundError:
        # Models registered from standalone recipes retain their full config in the
        # checkpoint sidecar; a registered policy should not depend on a legacy agent
        # YAML being present just to resolve its name.
        from cotraffic.recipes import load_recipe

        return load_recipe(method)


class LearnedPolicy(Controller):
    needs_observations = True

    def __init__(self, method: str, checkpoint: Path) -> None:
        super().__init__()
        from cotraffic.training.train import algorithm_class

        self.name = method
        self.checkpoint = Path(checkpoint)
        if not self.checkpoint.is_file():
            raise FileNotFoundError(f"checkpoint not found: {self.checkpoint}")
        self.agent_cfg = normalize_recipe(checkpoint_agent_config(method, self.checkpoint))
        # Saved recipes are self-contained; the normalizer must not replace them with a
        # lookup of configs/agents/<method>.yaml based on the old method identifier.
        self.agent_cfg["name"] = method
        algorithm = algorithm_class(self.agent_cfg.get("algorithm", "ppo"))
        self.model = algorithm.load(self.checkpoint, device="cpu")

    def parameters(self) -> dict[str, Any]:
        """Algorithm hyperparameters and the observation/reward switches that define the
        variant: an A/B table can then show the one key that actually differs."""
        algorithm = str(self.agent_cfg.get("algorithm", "ppo"))
        hyper = dict(self.agent_cfg.get(algorithm, {}))
        net_arch = hyper.pop("net_arch", None)
        params: dict[str, Any] = {
            "controller": self.name,
            "algorithm": algorithm,
            "checkpoint": self.checkpoint.name,
            **hyper,
        }
        if net_arch:
            params["net_arch"] = list(net_arch)
        for block in ("observation", "reward"):
            for key, value in (self.agent_cfg.get(block) or {}).items():
                params[f"{block}.{key}"] = value
        overlays = (self.agent_cfg.get("runtime") or {}).get("overlays") or []
        if overlays:
            params["runtime.overlays"] = [
                overlay if isinstance(overlay, str) else str(overlay.get("id", overlay))
                for overlay in overlays
            ]
        return params

    def reset(self, env) -> None:
        from cotraffic.forecasting.online import attach_forecaster

        if getattr(env, "obs_cfg", None) is not None and env.obs_cfg.forecast:
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
