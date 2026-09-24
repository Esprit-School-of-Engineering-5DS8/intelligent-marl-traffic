import numpy as np
import pytest

from cotraffic.demand.profiles import multiplier, peak_multiplier, poisson_arrivals

RUSH = [[0, 0.4], [900, 0.6], [1500, 1.0], [2700, 1.0], [3300, 0.6], [3600, 0.4]]


def test_constant_profile():
    assert multiplier("constant", 123.0) == 1.0
    assert multiplier(None, 5.0) == 1.0


def test_profile_interpolates_and_clamps():
    assert multiplier(RUSH, 450) == pytest.approx(0.5)
    assert multiplier(RUSH, 2000) == pytest.approx(1.0)
    assert multiplier(RUSH, -100) == pytest.approx(0.4)  # warm-up uses the first value
    assert multiplier(RUSH, 99999) == pytest.approx(0.4)
    assert peak_multiplier(RUSH) == 1.0


def test_arrivals_are_seeded_and_sorted():
    a = poisson_arrivals(1000, 0, 3600, np.random.default_rng(7))
    b = poisson_arrivals(1000, 0, 3600, np.random.default_rng(7))
    c = poisson_arrivals(1000, 0, 3600, np.random.default_rng(8))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert np.all(np.diff(a) >= 0) and a.min() >= 0 and a.max() < 3600


def test_arrival_rate_matches_expectation():
    counts = [len(poisson_arrivals(1200, 0, 3600, np.random.default_rng(s))) for s in range(200)]
    assert np.mean(counts) == pytest.approx(1200, rel=0.02)


def test_profile_thinning_matches_expected_volume():
    # expected number = integral of the rate over the hour
    t = np.linspace(0, 3600, 3601)
    expected = 1000 / 3600 * np.trapezoid(multiplier(RUSH, t), t)
    counts = [
        len(poisson_arrivals(1000, 0, 3600, np.random.default_rng(s), RUSH)) for s in range(200)
    ]
    assert np.mean(counts) == pytest.approx(expected, rel=0.03)


def test_profile_offset_shifts_the_peak():
    arrivals = np.concatenate(
        [
            poisson_arrivals(2000, 0, 4500, np.random.default_rng(s), RUSH, offset=900)
            for s in range(50)
        ]
    )
    warmup = np.sum(arrivals < 900) / 900
    peak = np.sum((arrivals > 900 + 1500) & (arrivals < 900 + 2700)) / 1200
    assert peak > 2 * warmup


def test_no_arrivals_for_empty_window():
    assert poisson_arrivals(1000, 10, 10, np.random.default_rng(0)).size == 0
