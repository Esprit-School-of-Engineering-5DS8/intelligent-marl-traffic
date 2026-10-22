"""Uniformly random phase requests (filtered by the shield); a sanity-check lower bound."""

from __future__ import annotations

from typing import Any

import numpy as np

from cotraffic.controllers.base import Controller


class RandomPolicy(Controller):
    name = "random"

    def __init__(self, seed: int = 0) -> None:
        super().__init__()
        self.rng = np.random.default_rng(seed)

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        return {
            tid: int(self.rng.integers(inter.n_phases)) for tid, inter in env.intersections.items()
        }
