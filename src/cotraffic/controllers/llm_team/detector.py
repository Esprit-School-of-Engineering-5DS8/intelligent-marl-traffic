"""Code-side queue alerts consumed by the supervisor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

AXES = ("NS", "EW")
QUEUE_KEY = {"NS": "ns_queue", "EW": "ew_queue"}


@dataclass(frozen=True)
class Alert:
    kind: str
    tls_id: str
    axis: str
    queue: int
    since_s: float
    severity: str
    t: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "tls": self.tls_id,
            "axis": self.axis,
            "queue": self.queue,
            "since_s": round(self.since_s, 1),
            "severity": self.severity,
        }


@dataclass(frozen=True)
class QueueDetectorConfig:
    queue_threshold: int = 15
    sustain_s: float = 20.0
    cooldown_s: float = 120.0
    alert_ttl_s: float = 120.0
    high_severity_queue: int = 30


@dataclass
class _Track:
    above_since: float | None = None
    cooldown_until: float = 0.0


class QueueAlertDetector:
    def __init__(self, config: QueueDetectorConfig | None = None) -> None:
        self.config = config or QueueDetectorConfig()
        self._track: dict[tuple[str, str], _Track] = {}
        self._active: list[Alert] = []
        self.count = 0

    def update(
        self, states: Mapping[str, Mapping[str, Any]], t: float
    ) -> list[Alert]:
        fired: list[Alert] = []
        for tls_id, state in states.items():
            for axis in AXES:
                queue = int(state.get(QUEUE_KEY[axis], 0) or 0)
                track = self._track.setdefault((tls_id, axis), _Track())
                if queue < self.config.queue_threshold:
                    track.above_since = None
                    continue
                if track.above_since is None:
                    track.above_since = t
                if (
                    t - track.above_since < self.config.sustain_s
                    or t < track.cooldown_until
                ):
                    continue
                alert = Alert(
                    kind="queue_growth",
                    tls_id=tls_id,
                    axis=axis,
                    queue=queue,
                    since_s=track.above_since,
                    severity="high" if queue >= self.config.high_severity_queue else "medium",
                    t=t,
                )
                fired.append(alert)
                self._active.append(alert)
                self.count += 1
                track.cooldown_until = t + self.config.cooldown_s
                track.above_since = t
        self._active = [a for a in self._active if t < a.t + self.config.alert_ttl_s]
        return fired

    def active(self, t: float) -> list[Alert]:
        self._active = [a for a in self._active if t < a.t + self.config.alert_ttl_s]
        return list(self._active)

    def clear(self) -> None:
        self._track.clear()
        self._active.clear()
