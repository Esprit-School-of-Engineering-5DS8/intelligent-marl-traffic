"""Queue and throughput forecast over the live run's compact history.

Pure functions so the projection is testable without SUMO. The session publishes one
sample per decision — ``t``, ``clock``, ``queue``, ``throughputPerMin``,
``avgSpeedKmh`` — and this module smooths it with an EWMA and extends it with a damped
linear trend. Every projected point is ``last smoothed value + slope × time``, clamped
to physical bounds; nothing here invents demand.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

DEFAULT_ALPHA = 0.35
DEFAULT_HORIZON_MIN = 15
MAX_QUEUE = 500.0
DAMPING = 0.9
TREND_WINDOW = 30


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def queue_of(sample: dict[str, Any]) -> float:
    """The session's history calls the field ``queued``, the forecast calls it ``queue``.

    Accepting either keeps a projection from silently reading 0 when the two schemas
    drift apart.
    """
    value = sample.get("queue")
    if value is None:
        value = sample.get("queued")
    return float(value or 0.0)


def ewma(values: Iterable[float], alpha: float = DEFAULT_ALPHA) -> list[float]:
    """Exponential smoothing; the first value seeds the series unchanged."""
    weight = clamp(float(alpha), 0.01, 1.0)
    smoothed: list[float] = []
    current: float | None = None
    for value in values:
        number = float(value)
        current = number if current is None else weight * number + (1.0 - weight) * current
        smoothed.append(current)
    return smoothed


def linear_trend(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares ``(slope, intercept)`` over ``(t, value)`` points.

    The slope is in value units per second, which is what the projection multiplies by
    an offset in seconds.
    """
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return 0.0, float(points[0][1])
    xs = [float(x) for x, _ in points]
    ys = [float(y) for _, y in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0, mean_y
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    return slope, mean_y - slope * mean_x


def confidence(samples: Sequence[dict[str, Any]]) -> float:
    """How much to trust the projection: sample count, discounted by queue spread.

    A short run is reported as low confidence, and a corridor whose queue swings hard
    is reported lower than a steady one with the same number of samples.
    """
    queues = [queue_of(sample) for sample in samples]
    if not queues:
        return 0.3
    base = min(0.9, 0.4 + len(queues) / 120.0)
    if len(queues) >= 3:
        mean = sum(queues) / len(queues)
        variance = sum((value - mean) ** 2 for value in queues) / len(queues)
        spread = math.sqrt(variance) / max(1.0, abs(mean))
        base -= min(0.25, spread * 0.5)
    return round(clamp(base, 0.3, 0.95), 2)


def clock(seconds: float) -> str:
    total = int(seconds) % 86400
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def project(
    samples: Sequence[dict[str, Any]],
    horizon_minutes: int = DEFAULT_HORIZON_MIN,
    interval_s: int = 60,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, Any]:
    """Project ``queue``/``throughputPerMin`` for ``horizon_minutes`` ahead.

    ``samples`` must be ordered by ``t`` (the session's history is). The last measured
    sample is returned unchanged in ``measured`` so the caller can draw the split
    between what happened and what is expected.
    """
    usable = [sample for sample in samples if sample.get("t") is not None]
    if len(usable) < 2:
        raise ValueError("at least two samples are needed to forecast")

    queues = ewma([queue_of(sample) for sample in usable], alpha)
    rates = ewma([float(sample.get("throughputPerMin") or 0.0) for sample in usable], alpha)
    speeds = [float(sample.get("avgSpeedKmh") or 0.0) for sample in usable]

    window = list(zip([float(sample["t"]) for sample in usable], queues))[-TREND_WINDOW:]
    slope, _ = linear_trend(window)

    horizon = max(1, int(horizon_minutes))
    step_s = max(1, int(interval_s))
    steps = max(1, horizon * 60 // step_s)
    last_t = int(usable[-1]["t"])
    last_queue = queues[-1]
    last_rate = max(0.0, rates[-1])
    last_speed = speeds[-1] if speeds else 0.0

    points: list[dict[str, Any]] = []
    for step in range(1, steps + 1):
        offset = step * step_s
        damping = DAMPING ** (step - 1)
        queue = clamp(last_queue + slope * offset * damping, 0.0, MAX_QUEUE)
        points.append(
            {
                "t": last_t + offset,
                "clock": clock(last_t + offset),
                "queue": round(queue, 1),
                "throughputPerMin": round(last_rate, 1),
                "avgSpeedKmh": round(last_speed, 1),
            }
        )

    peak = max(points, key=lambda point: point["queue"])
    measured = [
        {
            "t": int(sample["t"]),
            "clock": sample.get("clock") or clock(sample["t"]),
            "queue": queue_of(sample),
            "throughputPerMin": float(sample.get("throughputPerMin") or 0.0),
            "avgSpeedKmh": float(sample.get("avgSpeedKmh") or 0.0),
        }
        for sample in usable[-60:]
    ]
    return {
        "horizonMin": horizon,
        "intervalS": step_s,
        "method": "ewma + damped linear trend",
        "alpha": alpha,
        "samples": len(usable),
        "confidence": confidence(usable),
        "measured": measured,
        "points": points,
        "current": measured[-1],
        "peak": peak,
    }
