"""From one CSV per run to summary tables with confidence intervals and tests."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from cotraffic.analysis.stats import (
    bootstrap_ci,
    cliffs_delta,
    cliffs_magnitude,
    holm,
    mann_whitney_p,
)
from cotraffic.analysis.style import BASELINE_METHODS, HIGHER_IS_BETTER, METRIC_LABELS
from cotraffic.paths import RAW_DIR, SUMMARY_DIR

CELL = ["network", "scenario", "demand"]


def load_raw(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    files = sorted(Path(raw_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no result file in {raw_dir}")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if "quick" in df:
        quick = df["quick"].astype(str).str.lower() == "true"
        if quick.any():
            raise ValueError(f"{quick.sum()} quick-mode rows in {raw_dir}; they are not results")
    return df


def summarise(df: pd.DataFrame, metrics: Sequence[str] | None = None) -> pd.DataFrame:
    """Long table: one row per (cell, method, metric) with n, mean and bootstrap CI."""
    metrics = [m for m in (metrics or METRIC_LABELS) if m in df.columns]
    rows = []
    for key, group in df.groupby(CELL + ["method"], sort=False):
        for metric in metrics:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                continue
            mean, lo, hi = bootstrap_ci(values.to_numpy())
            rows.append(
                {
                    **dict(zip(CELL + ["method"], key, strict=True)),
                    "metric": metric,
                    "n": len(values),
                    "mean": mean,
                    "ci_lo": lo,
                    "ci_hi": hi,
                    "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                }
            )
    return pd.DataFrame(rows)


def compare(
    df: pd.DataFrame, metric: str, candidates: Sequence[str], reference: str = "best_baseline"
) -> pd.DataFrame:
    """Each candidate method against a reference in every cell where both were run.

    ``reference`` is a method id (e.g. ``ft``) or ``best_baseline``: the baseline with the
    best mean of this metric in the cell. p-values are Holm-corrected over the whole table.
    """
    lower_better = metric not in HIGHER_IS_BETTER
    rows = []
    for key, cell in df.groupby(CELL, sort=False):
        values = {
            m: pd.to_numeric(g[metric], errors="coerce").dropna().to_numpy()
            for m, g in cell.groupby("method")
        }
        if reference == "best_baseline":
            present = {m: v.mean() for m, v in values.items() if m in BASELINE_METHODS and v.size}
            if not present:
                continue
            ref = (min if lower_better else max)(present, key=present.get)
        else:
            ref = reference
        if ref not in values or not values[ref].size:
            continue
        for cand in candidates:
            if cand == ref or cand not in values or not values[cand].size:
                continue
            a, b = values[cand], values[ref]
            ref_mean = float(b.mean())
            gain = (ref_mean - a.mean()) if lower_better else (a.mean() - ref_mean)
            rows.append(
                {
                    **dict(zip(CELL, key, strict=True)),
                    "method": cand,
                    "reference": ref,
                    "kind": reference,
                    "metric": metric,
                    "mean": float(a.mean()),
                    "reference_mean": ref_mean,
                    "improvement_pct": 100.0 * gain / ref_mean if ref_mean else np.nan,
                    "p_value": mann_whitney_p(a, b),
                    "cliffs_delta": cliffs_delta(a, b),
                    "n": a.size,
                    "n_reference": b.size,
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["p_holm"] = holm(out["p_value"].tolist())
        out["effect"] = out["cliffs_delta"].map(cliffs_magnitude)
        out["significant"] = out["p_holm"] < 0.05
    return out


def run_aggregate(raw_dir: Path = RAW_DIR, out_dir: Path = SUMMARY_DIR) -> list[Path]:
    df = load_raw(raw_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    summary = summarise(df)
    path = out_dir / "summary.csv"
    summary.to_csv(path, index=False)
    written.append(path)
    methods = sorted(df["method"].unique())
    learned = [m for m in methods if m not in BASELINE_METHODS]
    baselines = [m for m in methods if m in BASELINE_METHODS]
    for metric in (
        "mean_travel_time",
        "mean_waiting_time",
        "co2_total_kg",
        "ev_delay",
        "person_weighted_delay",
        "ped_mean_waiting_time",
    ):
        if metric not in df.columns:
            continue
        tables = [compare(df, metric, [m for m in baselines if m != "ft"], "ft")]
        if learned:
            tables += [
                compare(df, metric, learned, "best_baseline"),
                compare(df, metric, learned, "ft"),
            ]
        comp = (
            pd.concat([t for t in tables if not t.empty], ignore_index=True)
            if any(not t.empty for t in tables)
            else pd.DataFrame()
        )
        if comp.empty:
            continue
        path = out_dir / f"comparisons_{metric}.csv"
        comp.to_csv(path, index=False)
        written.append(path)
    counts = df.groupby(CELL + ["method"]).size().rename("runs").reset_index()
    path = out_dir / "run_counts.csv"
    counts.to_csv(path, index=False)
    written.append(path)
    return written
