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

    def parameters(self) -> dict[str, Any]:
        """The hyperparameters this controller actually runs with.

        Recorded on every result row, so a table can say *what* produced a number
        instead of only naming the method. Values must be JSON-serialisable; return the
        effective ones (after config files, environment overrides and defaults), not the
        ones that were merely requested.
        """
        return {"controller": self.name}

    def step_hooks(self) -> list:
        """Callbacks run after every simulation second (``hook(env, now)``)."""
        return []

    def reset(self, env) -> None:
        return None

    def act(self, env, obs: dict[str, Any]) -> dict[str, int] | None:
        return None
