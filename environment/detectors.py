"""
environment/detectors.py
Code-side alert detection (plan section 4.5): the LLM interprets alerts, the
detectors produce them.

`QueueAlertDetector` watches the per-TLS, per-axis queues the fast layer
already collects and raises a `queue_growth` alert when an axis stays above a
halted-vehicle threshold for `sustain_s`. Alerts have a TTL (they appear in
snapshots for a while) and a per-axis cooldown so a long incident re-alerts at
a readable cadence instead of every tick.

Pure Python over state dicts: no TraCI, fully unit-testable. The incident S3
(A1A0 blocked) is exactly this pattern: one axis accumulates halted vehicles
and stays there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

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

    def to_dict(self) -> Dict[str, Any]:
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
    above_since: Optional[float] = None
    cooldown_until: float = 0.0


class QueueAlertDetector:
    """Sustained per-axis queue threshold detector with cooldown and TTL."""

    def __init__(self, config: Optional[QueueDetectorConfig] = None):
        self.config = config or QueueDetectorConfig()
        self._track: Dict[Tuple[str, str], _Track] = {}
        self._active: List[Alert] = []
        self.count = 0

    def update(self, states: Mapping[str, Mapping[str, Any]], t: float) -> List[Alert]:
        """Evaluate all TLS; returns alerts that fire at this tick."""
        fired: List[Alert] = []
        for tls_id, state in states.items():
            for axis in AXES:
                queue = int(state.get(QUEUE_KEY[axis], 0) or 0)
                track = self._track.setdefault((tls_id, axis), _Track())
                if queue < self.config.queue_threshold:
                    track.above_since = None
                    continue
                if track.above_since is None:
                    track.above_since = t
                if (t - track.above_since < self.config.sustain_s
                        or t < track.cooldown_until):
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

    def active(self, t: float) -> List[Alert]:
        self._active = [a for a in self._active if t < a.t + self.config.alert_ttl_s]
        return list(self._active)

    def clear(self) -> None:
        self._track.clear()
        self._active.clear()
