"""Disjoint seed ranges, so that no demand realisation is used for two purposes.

* test (evaluation) seeds: 0-999, chosen in the experiment configs
* validation seeds (checkpoint selection, design choices): 1000-1999
* tuning seeds (demand calibration, fixed-time plans): 5000-5999
* forecasting dataset: 6000+
* training seeds: a fixed pool starting at 100000
"""

from __future__ import annotations

from collections.abc import Iterable

VALIDATION_SEED_BASE = 1_000
FORECAST_SEED_BASE = 6_000
TRAINING_SEED_BASE = 100_000

TEST_SEEDS = range(0, VALIDATION_SEED_BASE)
VALIDATION_SEEDS = range(VALIDATION_SEED_BASE, 2 * VALIDATION_SEED_BASE)


def check_seeds(seeds: Iterable[int], allowed: range, purpose: str) -> None:
    """Raise if a seed lies outside the range reserved for ``purpose``."""
    bad = sorted({int(s) for s in seeds if int(s) not in allowed})
    if bad:
        raise ValueError(
            f"{purpose} seeds must lie in {allowed.start}-{allowed.stop - 1}; got {bad}"
        )
