"""Statistics used in every comparison of the report.

* 95% confidence interval of a mean: percentile bootstrap (10 000 resamples), which does
  not assume normality - with 5 to 15 runs per cell, normality cannot be checked. The runs
  of a learned method form a training-seed x test-seed table (3 x 5): both factors are
  resampled as clusters (two-way bootstrap), so the interval includes the variation
  between training runs; a baseline has one row and gets the ordinary bootstrap over test
  seeds.
* Paired differences: method minus reference on the same test seed, with the same two-way
  resampling (the reference's test seeds are resampled together with the method's).
* Test: two-sided Mann-Whitney U (rank-based, no normality assumption). It treats the 15
  runs of a learned method as independent, which they are not (3 training runs); p-values
  of learned methods are therefore optimistic, and conclusions rest on the intervals and
  effect sizes as much as on p.
* Multiple comparisons: Holm's step-down correction over the family of tests of a table.
* Effect size: Cliff's delta, with Romano et al. (2006) thresholds for its magnitude.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy import stats


def bootstrap_ci(
    values: Sequence[float], n_boot: int = 10_000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float, float]:
    """Mean and percentile-bootstrap confidence interval."""
    x = np.asarray(values, dtype=float)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return float("nan"), float("nan"), float("nan")
    if x.size == 1:
        return float(x[0]), float(x[0]), float(x[0])
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, x.size, size=(n_boot, x.size))].mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(x.mean()), float(lo), float(hi)


def _counts(n_boot: int, n: int, rng: np.random.Generator) -> np.ndarray:
    """How often each of ``n`` units is drawn in each of ``n_boot`` resamples."""
    draws = rng.integers(0, n, size=(n_boot, n))
    return (draws[:, :, None] == np.arange(n)).sum(axis=1).astype(float)


def crossed_bootstrap_ci(
    table: np.ndarray | Sequence[Sequence[float]],
    n_boot: int = 10_000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Mean of a (training run x test seed) table and a two-way cluster bootstrap CI.

    Rows and columns are resampled independently with replacement; missing cells (NaN)
    are left out of each resampled mean. A single row reduces to the ordinary bootstrap
    over test seeds.
    """
    t = np.atleast_2d(np.asarray(table, dtype=float))
    ok = ~np.isnan(t)
    if not ok.any():
        return float("nan"), float("nan"), float("nan")
    mean = float(t[ok].mean())
    if ok.sum() == 1:
        return mean, mean, mean
    rng = np.random.default_rng(seed)
    rows, cols = _counts(n_boot, t.shape[0], rng), _counts(n_boot, t.shape[1], rng)
    total = np.einsum("bi,ij,bj->b", rows, np.where(ok, t, 0.0), cols)
    count = np.einsum("bi,ij,bj->b", rows, ok.astype(float), cols)
    means = total[count > 0] / count[count > 0]
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return mean, float(lo), float(hi)


def paired_change_ci(
    table: np.ndarray | Sequence[Sequence[float]],
    reference: Sequence[float],
    n_boot: int = 10_000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Change of a method relative to a reference, paired on test seeds, in percent.

    ``table`` is (training run x test seed), ``reference`` has one value per test seed
    (same column order). Returns 100 * mean(method - reference) / mean(reference) over the
    seeds where both exist, with a two-way bootstrap CI (training runs and test seeds
    resampled; the reference follows its test seeds).
    """
    t = np.atleast_2d(np.asarray(table, dtype=float))
    ref = np.asarray(reference, dtype=float)
    keep = ~np.isnan(ref) & (~np.isnan(t)).any(axis=0)
    t, ref = t[:, keep], ref[keep]
    if t.size == 0:
        return float("nan"), float("nan"), float("nan")
    diff = t - ref[None, :]
    ok = ~np.isnan(diff)
    point = float(100 * diff[ok].mean() / ref.mean())
    rng = np.random.default_rng(seed)
    rows, cols = _counts(n_boot, t.shape[0], rng), _counts(n_boot, t.shape[1], rng)
    total = np.einsum("bi,ij,bj->b", rows, np.where(ok, diff, 0.0), cols)
    count = np.einsum("bi,ij,bj->b", rows, ok.astype(float), cols)
    ref_mean = cols @ ref / cols.sum(axis=1)
    valid = count > 0
    pct = 100 * total[valid] / count[valid] / ref_mean[valid]
    lo, hi = np.percentile(pct, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return point, float(lo), float(hi)


def mann_whitney_p(a: Sequence[float], b: Sequence[float]) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.size == 0 or b.size == 0:
        return float("nan")
    if np.all(a == a[0]) and np.all(b == b[0]) and a[0] == b[0]:
        return 1.0
    return float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)


def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (NaN entries are left out of the family)."""
    p = np.asarray(pvalues, dtype=float)
    out = np.full(p.shape, np.nan)
    idx = np.where(~np.isnan(p))[0]
    m = idx.size
    if m == 0:
        return out.tolist()
    order = idx[np.argsort(p[idx])]
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        out[i] = running
    return out.tolist()


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """P(a > b) - P(a < b) over all pairs; in [-1, 1], 0 = no difference."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.size == 0 or b.size == 0:
        return float("nan")
    diff = a[:, None] - b[None, :]
    return float((np.sum(diff > 0) - np.sum(diff < 0)) / (a.size * b.size))


def cliffs_magnitude(delta: float) -> str:
    d = abs(delta)
    if np.isnan(d):
        return ""
    if d < 0.147:
        return "negligible"
    if d < 0.33:
        return "small"
    if d < 0.474:
        return "medium"
    return "large"
