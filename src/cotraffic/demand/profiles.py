"""Time-of-day demand profiles and arrival sampling."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

Profile = Sequence[Sequence[float]] | str | None


def multiplier(profile: Profile, t: np.ndarray | float) -> np.ndarray | float:
    """Demand multiplier at relative time ``t`` (s since the start of the demand hour).

    ``profile`` is ``None``/``"constant"`` or a list of ``[time_s, multiplier]`` points,
    linearly interpolated and held constant outside the given range.
    """
    if profile is None or profile == "constant":
        return np.ones_like(t, dtype=float) if isinstance(t, np.ndarray) else 1.0
    points = sorted((float(a), float(b)) for a, b in profile)
    times, values = zip(*points, strict=True)
    return np.interp(t, times, values)


def peak_multiplier(profile: Profile) -> float:
    if profile is None or profile == "constant":
        return 1.0
    return max(float(b) for _, b in profile)


def poisson_arrivals(
    rate_per_hour: float,
    begin: float,
    end: float,
    rng: np.random.Generator,
    profile: Profile = None,
    offset: float = 0.0,
) -> np.ndarray:
    """Arrival times of a non-homogeneous Poisson process on ``[begin, end)``.

    The instantaneous rate is ``rate_per_hour * multiplier(profile, t - offset)``.
    Sampling uses thinning of a homogeneous process at the peak rate, which is exact.
    """
    if end <= begin or rate_per_hour <= 0:
        return np.empty(0)
    peak = rate_per_hour * peak_multiplier(profile) / 3600.0
    n = rng.poisson(peak * (end - begin))
    times = np.sort(rng.uniform(begin, end, size=n))
    if profile is None or profile == "constant":
        return times
    rate = rate_per_hour * np.asarray(multiplier(profile, times - offset)) / 3600.0
    keep = rng.uniform(size=n) < rate / peak
    return times[keep]
