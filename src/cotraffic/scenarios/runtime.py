"""Perturbations applied while the simulation runs (evaluation-only scenarios).

Incidents, emergency vehicles, buses and pedestrians are injected through the route
files (see ``demand.generator``) and therefore affect every controller in the same
way. Sensor faults and communication losses act on what the controllers *see*.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cotraffic import config


@dataclass
class SensorNoise:
    """Gaussian noise on lane counts plus detectors that report 0 for the whole episode."""

    count_std_veh: float
    failed_fraction: float
    failed: set[str] = field(default_factory=set)

    def reset(self, lanes: Iterable[str], rng: np.random.Generator) -> None:
        lanes = sorted(lanes)
        n_failed = int(round(self.failed_fraction * len(lanes)))
        self.failed = set(rng.choice(lanes, size=n_failed, replace=False)) if n_failed else set()

    def apply(self, meas, rng: np.random.Generator) -> None:
        for lane in meas.lanes:
            if lane in self.failed:
                meas.count[lane] = meas.halting[lane] = meas.speed[lane] = 0.0
                continue
            count = max(0.0, meas.count[lane] + rng.normal(0.0, self.count_std_veh))
            halting = max(0.0, meas.halting[lane] + rng.normal(0.0, self.count_std_veh))
            meas.count[lane] = count
            meas.halting[lane] = min(halting, count)


@dataclass
class CommDropout:
    """Each neighbour message is lost with probability ``p``.

    ``stale`` keeps the last message that did arrive (what a receiver with a buffer
    would do); ``zero`` replaces it with zeros (no information).
    """

    p: float
    mode: str = "stale"
    last: dict[Hashable, np.ndarray] = field(default_factory=dict)
    sent: int = 0
    lost: int = 0

    def __post_init__(self) -> None:
        if self.mode not in ("stale", "zero"):
            raise ValueError(f"unknown dropout mode {self.mode!r}")

    def reset(self) -> None:
        self.last = {}
        self.sent = self.lost = 0

    def transmit(self, key: Hashable, message: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        self.sent += 1
        if rng.uniform() < self.p:
            self.lost += 1
            if self.mode == "stale":
                return self.last.get(key, np.zeros_like(message))
            return np.zeros_like(message)
        self.last[key] = message
        return message


def runtime_perturbations(scenarios: Iterable[str]) -> dict[str, Any]:
    """Build the runtime perturbations requested by a list of scenario names."""
    out: dict[str, Any] = {}
    for name in scenarios:
        cfg: Mapping[str, Any] = config.load("scenarios", name)
        if "sensor_noise" in cfg:
            c = cfg["sensor_noise"]
            out["sensor_noise"] = SensorNoise(
                float(c["count_std_veh"]), float(c["failed_fraction"])
            )
        if "comm_dropout" in cfg:
            c = cfg["comm_dropout"]
            out["comm_dropout"] = CommDropout(float(c["p"]), str(c.get("mode", "stale")))
    return out
