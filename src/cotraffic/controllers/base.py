"""Common interface of all signal controllers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class Controller:
    """A controller either acts through the environment (and therefore through the
    safety shield) or lets SUMO run a signal program (``controlled = False``)."""

    name = "base"
    controlled = True
    needs_observations = False

    def __init__(self) -> None:
        self.agent_cfg: dict[str, Any] = {}

    def additional_files(self, network: str, demand: str) -> list[Path]:
        """Extra SUMO files the controller needs, e.g. its signal programs."""
        return []

    def step_hooks(self) -> list:
        """Callbacks run after every simulation second (``hook(env, now)``)."""
        return []

    def reset(self, env) -> None:
        return None

    def act(self, env, obs: dict[str, Any]) -> dict[str, int] | None:
        return None
