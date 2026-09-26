import numpy as np
import pytest

from cotraffic.analysis.stats import (
    bootstrap_ci,
    cliffs_delta,
    cliffs_magnitude,
    crossed_bootstrap_ci,
    holm,
    mann_whitney_p,
    paired_change_ci,
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


def test_crossed_bootstrap_widens_with_differences_between_training_runs():
    seeds = np.array([210.0, 205.0, 215.0, 200.0, 205.0])
    same = np.stack([seeds, seeds + 1, seeds - 1])
    spread = np.stack([seeds, seeds + 15, seeds - 15])
    m1, lo1, hi1 = crossed_bootstrap_ci(same)
    m2, lo2, hi2 = crossed_bootstrap_ci(spread)
    assert m1 == pytest.approx(m2) == pytest.approx(seeds.mean())
    assert hi2 - lo2 > hi1 - lo1
    # one row = ordinary bootstrap over test seeds; missing cells are ignored
    assert crossed_bootstrap_ci(seeds)[0] == pytest.approx(seeds.mean())
    with_gap = spread.copy()
    with_gap[0, 0] = np.nan
    assert crossed_bootstrap_ci(with_gap)[0] == pytest.approx(np.nanmean(with_gap))
    assert all(np.isnan(v) for v in crossed_bootstrap_ci([[np.nan]]))


def test_paired_change_removes_the_test_seed_effect():
    ref = np.array([150.0, 200.0, 120.0, 180.0, 160.0])  # large seed-to-seed variation
    table = np.stack([ref * 1.05, ref * 1.05 + 1, ref * 1.05 - 1])
    change, lo, hi = paired_change_ci(table, ref)
    assert change == pytest.approx(5.0, abs=0.1)
    assert 4.0 < lo <= change <= hi < 6.0
    # unpaired, the same data would be indistinguishable from the reference
    _, rlo, rhi = crossed_bootstrap_ci(ref)
    assert rlo < table.mean() < rhi
