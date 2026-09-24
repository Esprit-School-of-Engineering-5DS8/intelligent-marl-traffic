import numpy as np
import pytest

from cotraffic.analysis.stats import (
    bootstrap_ci,
    cliffs_delta,
    cliffs_magnitude,
    holm,
    mann_whitney_p,
)


def test_bootstrap_ci_contains_the_mean_and_is_reproducible():
    x = [10.0, 12.0, 11.0, 13.0, 9.0]
    mean, lo, hi = bootstrap_ci(x)
    assert mean == pytest.approx(11.0)
    assert lo < mean < hi
    assert bootstrap_ci(x) == (mean, lo, hi)


def test_bootstrap_ci_edge_cases():
    assert bootstrap_ci([5.0]) == (5.0, 5.0, 5.0)
    assert all(np.isnan(v) for v in bootstrap_ci([]))


def test_bootstrap_ci_coverage_is_close_to_95_percent():
    rng = np.random.default_rng(1)
    covered = 0
    for i in range(300):
        sample = rng.normal(50, 10, size=30)
        _, lo, hi = bootstrap_ci(sample, n_boot=2000, seed=i)
        covered += lo <= 50 <= hi
    assert 0.90 <= covered / 300 <= 0.98


def test_holm_matches_hand_computation():
    # sorted p: 0.01 (x3), 0.02 (x2), 0.04 (x1) -> 0.03, 0.04, 0.04
    assert holm([0.04, 0.01, 0.02]) == pytest.approx([0.04, 0.03, 0.04])
    assert holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])
    out = holm([0.01, float("nan")])
    assert out[0] == pytest.approx(0.01) and np.isnan(out[1])


def test_cliffs_delta():
    assert cliffs_delta([1, 2, 3], [4, 5, 6]) == -1.0
    assert cliffs_delta([4, 5, 6], [1, 2, 3]) == 1.0
    assert cliffs_delta([1, 2], [1, 2]) == 0.0
    assert cliffs_magnitude(0.1) == "negligible"
    assert cliffs_magnitude(-0.4) == "medium"
    assert cliffs_magnitude(0.9) == "large"


def test_mann_whitney_detects_a_clear_difference():
    assert mann_whitney_p([1, 2, 3, 4, 5], [10, 11, 12, 13, 14]) < 0.05
    assert mann_whitney_p([1, 2, 3], [1, 2, 3]) > 0.5
    assert mann_whitney_p([2, 2], [2, 2]) == 1.0
