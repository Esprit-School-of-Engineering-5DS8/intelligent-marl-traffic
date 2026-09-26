"""From one CSV per run to summary tables with confidence intervals and tests."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from cotraffic.analysis.stats import (
    cliffs_delta,
    cliffs_magnitude,
    crossed_bootstrap_ci,
    holm,
    mann_whitney_p,
    paired_change_ci,
)
from cotraffic.analysis.style import BASELINE_METHODS, HIGHER_IS_BETTER, METRIC_LABELS
from cotraffic.paths import RAW_DIR, SUMMARY_DIR

CELL = ["network", "scenario", "demand"]
TRAIN_SEED_RE = r"-t(\d+)__"


def load_raw(raw_dir: Path = RAW_DIR, allow_quick: bool = False) -> pd.DataFrame:
    files = sorted(Path(raw_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no result file in {raw_dir}")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if "quick" in df and not allow_quick:
        quick = df["quick"].astype(str).str.lower() == "true"
        if quick.any():
            raise ValueError(f"{quick.sum()} quick-mode rows in {raw_dir}; they are not results")
    return df


def core_cells(experiment: str = "core") -> set[tuple[str, str, str, str]]:
    """(network, scenario, demand, method) of the core experiment.

    The core cells and variants form the confirmatory family of the report: their tests
    are Holm-corrected together, and results added later (extended matrix, sensitivity
    variants) form a separate, exploratory family, so that they cannot change the
    report's corrected p-values.
    """
    from cotraffic import config

    exp = config.load("experiments", experiment)
    return {
        (cell["network"], scenario, demand, method)
        for cell in exp["cells"]
        for method in cell["methods"]
        for demand in cell["demands"]
        for scenario in cell["scenarios"]
    }


def assign_families(comp: pd.DataFrame, core: set[tuple[str, str, str, str]]) -> pd.DataFrame:
    """Holm correction within each (comparison, family) group; see ``core_cells``."""
    comp = comp.copy()
    comp["family"] = [
        "core" if key in core else "exploratory"
        for key in zip(
            comp["network"], comp["scenario"], comp["demand"], comp["method"], strict=True
        )
    ]
    comp["p_holm"] = comp.groupby(["comparison", "family"])["p_value"].transform(
        lambda p: pd.Series(holm(p.tolist()), index=p.index)
    )
    comp["significant"] = comp["p_holm"] < 0.05
    return comp


def seed_table(group: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Values of one method in one cell as a (training run x test seed) table.

    Learned methods have one row per training seed (tag ``-t<k>`` of the run id);
    baselines have a single row.
    """
    train = (
        group["run_id"].astype(str).str.extract(TRAIN_SEED_RE)[0].fillna("-")
        if "run_id" in group
        else pd.Series("-", index=group.index)
    )
    values = pd.to_numeric(group[metric], errors="coerce")
    frame = pd.DataFrame({"train": train, "seed": group["seed"], "value": values})
    return frame.pivot_table(index="train", columns="seed", values="value", aggfunc="mean")


def summarise(df: pd.DataFrame, metrics: Sequence[str] | None = None) -> pd.DataFrame:
    """Long table: one row per (cell, method, metric) with n, mean and bootstrap CI
    (two-way over training runs and test seeds for learned methods, see ``stats``)."""
    metrics = [m for m in (metrics or METRIC_LABELS) if m in df.columns]
    rows = []
    for key, group in df.groupby(CELL + ["method"], sort=False):
        for metric in metrics:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                continue
            table = seed_table(group, metric)
            mean, lo, hi = crossed_bootstrap_ci(table.to_numpy())
            rows.append(
                {
                    **dict(zip(CELL + ["method"], key, strict=True)),
                    "metric": metric,
                    "n": len(values),
                    "n_train": len(table),
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
    ``paired_improvement_*``: the same comparison paired on test seeds (method minus
    reference on the same seed), with a two-way bootstrap CI; positive = better.
    """
    lower_better = metric not in HIGHER_IS_BETTER
    rows = []
    for key, cell in df.groupby(CELL, sort=False):
        groups = dict(tuple(cell.groupby("method")))
        values = {
            m: pd.to_numeric(g[metric], errors="coerce").dropna().to_numpy()
            for m, g in groups.items()
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
            cand_table = seed_table(groups[cand], metric)
            ref_table = seed_table(groups[ref], metric)
            seeds = sorted(set(cand_table.columns) & set(ref_table.columns))
            change, lo, hi = paired_change_ci(
                cand_table[seeds].to_numpy(), ref_table[seeds].mean(axis=0).to_numpy()
            )
            sign = -1.0 if lower_better else 1.0
            paired = sorted((sign * lo, sign * hi))
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
                    "paired_improvement_pct": sign * change,
                    "paired_ci_lo": paired[0],
                    "paired_ci_hi": paired[1],
                    "n": a.size,
                    "n_reference": b.size,
                    "n_train": len(cand_table),
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["p_holm"] = holm(out["p_value"].tolist())
        out["effect"] = out["cliffs_delta"].map(cliffs_magnitude)
        out["significant"] = out["p_holm"] < 0.05
    return out


def run_aggregate(
    raw_dir: Path = RAW_DIR, out_dir: Path = SUMMARY_DIR, allow_quick: bool = False
) -> list[Path]:
    df = load_raw(raw_dir, allow_quick)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    core = core_cells()
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
        tables = [
            compare(df, metric, [m for m in baselines if m != "ft"], "ft").assign(
                comparison="baselines_vs_ft"
            )
        ]
        if learned:
            tables += [
                compare(df, metric, learned, "best_baseline").assign(comparison="learned_vs_best"),
                compare(df, metric, learned, "ft").assign(comparison="learned_vs_ft"),
            ]
        tables = [t for t in tables if not t.empty and "p_value" in t]
        if not tables:
            continue
        comp = assign_families(pd.concat(tables, ignore_index=True), core)
        path = out_dir / f"comparisons_{metric}.csv"
        comp.to_csv(path, index=False)
        written.append(path)
    counts = df.groupby(CELL + ["method"]).size().rename("runs").reset_index()
    path = out_dir / "run_counts.csv"
    counts.to_csv(path, index=False)
    written.append(path)
    return written
