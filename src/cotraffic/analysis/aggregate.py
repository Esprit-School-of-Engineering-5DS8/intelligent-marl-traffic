"""From one CSV per run to summary tables with confidence intervals and tests."""

from __future__ import annotations

import json
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
from cotraffic.analysis.style import (
    BASELINE_METHODS,
    HIGHER_IS_BETTER,
    LLM_METHODS,
    METRIC_LABELS,
)
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


LLM_HEALTH_COLUMNS = (
    "run_id",
    "network",
    "scenario",
    "demand",
    "seed",
    "llm_provider",
    "llm_model",
    "llm_calls",
    "llm_success",
    "llm_errors",
    "llm_fallbacks",
    "llm_rounds",
    "llm_coverage_pct",
    "llm_prompt_tokens",
    "llm_completion_tokens",
    "llm_latency_ms_mean",
    "llm_budget_hit",
    "llm_status",
    "llm_valid",
    "llm_last_error",
)


def llm_valid_column(df: pd.DataFrame) -> pd.Series:
    """1 where an LLM run's metrics describe the LLM rather than its Max-Pressure fallback.

    Runs written after the budget existed carry ``llm_valid`` directly. Older rows are
    recovered from the same counters: ``llm_calls`` counts every attempt, ``llm_success``
    only the attempts the model answered, so a cell with zero successful calls (the
    rate-limited grid3x3 peak cells) is a fallback result whatever it is labelled.
    """
    if "llm_valid" in df.columns:
        return pd.to_numeric(df["llm_valid"], errors="coerce").fillna(0).astype(int)
    if "llm_success" not in df.columns:
        return pd.Series(1, index=df.index)
    success = pd.to_numeric(df["llm_success"], errors="coerce").fillna(0)
    calls = pd.to_numeric(df.get("llm_calls", 0), errors="coerce").fillna(0)
    return ((success > 0) & (calls == success)).astype(int)


def llm_health(df: pd.DataFrame) -> pd.DataFrame:
    """One row per LLM run: did the model drive it, and what did that cost?

    Written to ``results/summary/llm_health.csv`` whether or not the cell is usable, so a
    degraded run is a recorded result instead of a quiet one.
    """
    if "method" not in df.columns or not (df["method"] == "llm").any():
        return pd.DataFrame()
    sub = df[df["method"] == "llm"].copy()
    sub["llm_valid"] = llm_valid_column(sub)
    if "llm_status" not in sub.columns:  # runs written before the verdict existed
        success = pd.to_numeric(sub.get("llm_success", 0), errors="coerce").fillna(0)
        calls = pd.to_numeric(sub.get("llm_calls", 0), errors="coerce").fillna(0)
        available = pd.to_numeric(sub.get("llm_available", 0), errors="coerce").fillna(0)
        sub["llm_errors"] = (calls - success).clip(lower=0)
        sub["llm_status"] = np.select(
            [available == 0, calls > success, success > 0],
            ["unavailable", "degraded", "ok"],
            default="silent",
        )
    # A round is one decision the model was asked for. Legacy rows counted every fallback
    # *step* as a round (the steps between calls), which turned a clean run into a 4%
    # coverage; answered/attempted is the same quantity on both generations of rows.
    rounds = pd.to_numeric(sub.get("llm_calls", 0), errors="coerce").fillna(0)
    answered = pd.to_numeric(sub.get("llm_success", 0), errors="coerce").fillna(0)
    sub["llm_rounds"] = rounds
    sub["llm_coverage_pct"] = np.where(rounds > 0, 100.0 * answered / rounds, 0.0).round(1)
    keep = [c for c in LLM_HEALTH_COLUMNS if c in sub.columns]
    return sub[keep].sort_values(["network", "demand", "seed"]).reset_index(drop=True)


def valid_only(df: pd.DataFrame) -> pd.DataFrame:
    """Rows the statistics are allowed to use: LLM cells only when they are LLM results."""
    if "method" not in df.columns:
        return df
    invalid = (df["method"] == "llm") & (llm_valid_column(df) != 1)
    return df[~invalid]


def hyperparameters(df: pd.DataFrame) -> pd.DataFrame:
    """Long table: one row per (configuration, hyperparameter) of the runs in ``df``.

    ``param_hash`` is a digest of the full parameter set and ``runs`` counts the result
    rows that share it, so the table answers both "what were the knobs?" and "which of
    these numbers came from the same model?".
    """
    if "parameters" not in df.columns:
        return pd.DataFrame()
    digest = (
        df["param_hash"].astype(str)
        if "param_hash" in df.columns
        else df["parameters"].astype(str)
    )
    frame = df.assign(_params=df["parameters"].astype(str), _digest=digest)
    rows = []
    for (method, variant, key), group in frame.groupby(
        ["method", "variant", "_digest"], dropna=False
    ):
        try:
            params = json.loads(group["_params"].iloc[0])
        except (TypeError, ValueError):
            continue
        for name, value in sorted(params.items()):
            rows.append(
                {
                    "method": method,
                    "variant": variant,
                    "param_hash": key,
                    "runs": len(group),
                    "parameter": name,
                    "value": value,
                }
            )
    return pd.DataFrame(rows)


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


def other_families() -> dict[str, set[tuple[str, str, str, str]]]:
    """Families of experiments added after the report (one family each)."""
    from cotraffic import config

    return {name: core_cells(name) for name in ("dqn",) if name in config.available("experiments")}


def assign_families(
    comp: pd.DataFrame,
    core: set[tuple[str, str, str, str]],
    others: dict[str, set[tuple[str, str, str, str]]] | None = None,
) -> pd.DataFrame:
    """Holm correction within each (comparison, family) group; see ``core_cells``.

    ``others`` gives further families of their own (the DQN experiment, added after the
    report), so that they change neither the core nor the exploratory p-values."""
    comp = comp.copy()
    others = others or {}

    def family(key: tuple[str, str, str, str]) -> str:
        if key in core:
            return "core"
        return next((name for name, cells in others.items() if key in cells), "exploratory")

    comp["family"] = [
        family(key)
        for key in zip(
            comp["network"], comp["scenario"], comp["demand"], comp["method"], strict=True
        )
    ]
    # The LLM comparisons are their own family: they are a different kind of claim (costly
    # external model vs controller) and must not move the report's corrected p-values.
    comp.loc[comp["comparison"].astype(str).str.startswith("llm_"), "family"] = "llm"
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
    health = llm_health(df)
    if not health.empty:
        path = out_dir / "llm_health.csv"
        health.to_csv(path, index=False)
        written.append(path)
    params = hyperparameters(df)
    if not params.empty:
        path = out_dir / "hyperparameters.csv"
        params.to_csv(path, index=False)
        written.append(path)
    # An LLM cell that never reached the model measured Max-Pressure, so it is reported in
    # llm_health.csv but kept out of every table that claims to be about the LLM.
    stats = valid_only(df)
    dropped = len(df) - len(stats)
    if dropped:
        print(f"aggregate: {dropped} LLM run(s) dropped as fallback-only; see llm_health.csv")
    summary = summarise(stats)
    path = out_dir / "summary.csv"
    summary.to_csv(path, index=False)
    written.append(path)
    methods = sorted(stats["method"].unique())
    learned = [m for m in methods if m not in BASELINE_METHODS and m not in LLM_METHODS]
    baselines = [m for m in methods if m in BASELINE_METHODS]
    llm = [m for m in methods if m in LLM_METHODS]
    for metric in (
        "mean_travel_time",
        "mean_waiting_time",
        "co2_total_kg",
        "ev_delay",
        "person_weighted_delay",
        "ped_mean_waiting_time",
    ):
        if metric not in stats.columns:
            continue
        tables = [
            compare(stats, metric, [m for m in baselines if m != "ft"], "ft").assign(
                comparison="baselines_vs_ft"
            )
        ]
        if llm:
            # Max-Pressure is the LLM's own fallback, so it is the reference that says
            # whether the model adds anything over the cheap controller it degrades to.
            tables.append(compare(stats, metric, llm, "mp").assign(comparison="llm_vs_mp"))
            tables.append(compare(stats, metric, llm, "ft").assign(comparison="llm_vs_ft"))
            if "coop" in methods:
                tables.append(compare(stats, metric, llm, "coop").assign(comparison="llm_vs_coop"))
        if learned:
            tables += [
                compare(stats, metric, learned, "best_baseline").assign(
                    comparison="learned_vs_best"
                ),
                compare(stats, metric, learned, "ft").assign(comparison="learned_vs_ft"),
            ]
        tables = [t for t in tables if not t.empty and "p_value" in t]
        if not tables:
            continue
        comp = assign_families(pd.concat(tables, ignore_index=True), core, other_families())
        path = out_dir / f"comparisons_{metric}.csv"
        comp.to_csv(path, index=False)
        written.append(path)
    counts = df.groupby(CELL + ["method"]).size().rename("runs").reset_index()
    path = out_dir / "run_counts.csv"
    counts.to_csv(path, index=False)
    written.append(path)
    _prune_derived(out_dir, written)
    return written


OWNED_PATTERNS = ("comparisons_*.csv", "llm_health.csv", "hyperparameters.csv")


def _prune_derived(out_dir: Path, written: Sequence[Path]) -> None:
    """Delete this step's previous outputs that the new raw data no longer produces.

    A metric that disappears with its runs (EV delay and pedestrian waits only existed on
    the retired networks) stops being written, and a left-over CSV of it keeps feeding the
    dashboard and the report: they list cells for a scenario nothing can produce any more.
    """
    keep = {Path(p).resolve() for p in written}
    for pattern in OWNED_PATTERNS:
        for path in out_dir.glob(pattern):
            if path.resolve() not in keep:
                path.unlink()
                print(f"aggregate: removed stale {path.name} (no runs left for it)")
