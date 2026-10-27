"""``results/summary/REPORT_TABLES.md``: the report's tables, generated from result files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cotraffic.analysis.style import DEMAND_ORDER, METRIC_LABELS, label, method_sort_key
from cotraffic.paths import CHECKPOINTS_DIR, RAW_DIR, SUMMARY_DIR

PEAK_METRICS = [
    "mean_travel_time",
    "mean_waiting_time",
    "mean_queue",
    "throughput_per_h",
    "p95_waiting_time",
    "gini_waiting_time",
    "co2_g_per_km",
    "stops_per_vehicle",
    "ssm_conflicts_per_1000_veh",
    "shield_interventions",
    "unfinished",
    "teleports_total",
]
SCENARIO_METRICS = {
    "emergency": ["ev_travel_time", "ev_delay", "mean_travel_time", "mean_waiting_time"],
    "incident": ["mean_travel_time", "mean_waiting_time", "mean_queue", "p95_waiting_time"],
    "pedestrians": ["ped_mean_waiting_time", "ped_max_waiting_time", "mean_travel_time"],
    "buses": ["person_weighted_delay", "bus_delay", "mean_travel_time"],
}
DEFAULT_SCENARIO_METRICS = ["mean_travel_time", "mean_waiting_time", "mean_queue"]


def _fmt(mean: float, lo: float, hi: float) -> str:
    if mean == lo == hi == 0:
        return "0"
    digits = 0 if abs(mean) >= 100 else (1 if abs(mean) >= 1 else 3)
    return f"{mean:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"


def _cell(summary: pd.DataFrame, metric: str, **where) -> pd.DataFrame:
    sel = summary["metric"] == metric
    for key, value in where.items():
        sel &= summary[key] == value
    return summary[sel]


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out + [""]


def demand_table(summary: pd.DataFrame, network: str, scenario: str, metric: str) -> list[str]:
    sub = _cell(summary, metric, network=network, scenario=scenario)
    if sub.empty:
        return []
    demands = [d for d in DEMAND_ORDER if d in set(sub["demand"])]
    methods = sorted(sub["method"].unique(), key=method_sort_key)
    rows = []
    for m in methods:
        row = [label(m)]
        for d in demands:
            r = sub[(sub["method"] == m) & (sub["demand"] == d)]
            row.append(
                _fmt(r["mean"].iloc[0], r["ci_lo"].iloc[0], r["ci_hi"].iloc[0]) if len(r) else "-"
            )
        rows.append(row)
    name = METRIC_LABELS.get(metric, metric)
    title = f"**{name}** - {network}, scenario `{scenario}` (mean [95% CI])"
    return [title, ""] + _table(["Method"] + demands, rows)


def metrics_table(
    summary: pd.DataFrame, network: str, scenario: str, demand: str, metrics: list[str]
) -> list[str]:
    sub = summary[
        (summary["network"] == network)
        & (summary["scenario"] == scenario)
        & (summary["demand"] == demand)
    ]
    metrics = [m for m in metrics if m in set(sub["metric"])]
    if sub.empty or not metrics:
        return []
    methods = sorted(sub["method"].unique(), key=method_sort_key)
    rows = []
    for m in methods:
        row = [label(m)]
        for metric in metrics:
            r = sub[(sub["method"] == m) & (sub["metric"] == metric)]
            row.append(
                _fmt(r["mean"].iloc[0], r["ci_lo"].iloc[0], r["ci_hi"].iloc[0]) if len(r) else "-"
            )
        rows.append(row)
    title = f"**{network}, scenario `{scenario}`, demand `{demand}`** (mean [95% CI])"
    return [title, ""] + _table(["Method"] + [METRIC_LABELS.get(m, m) for m in metrics], rows)


def comparison_table(comp: pd.DataFrame, kind: str, family: str = "core") -> list[str]:
    """Rows of the comparisons made against ``kind`` (``ft`` or ``best_baseline``) in one
    Holm family (``core``: the report's confirmatory tests; ``exploratory``: the rest)."""
    sub = comp[comp["kind"] == kind]
    if "family" in sub:
        sub = sub[sub["family"] == family]
    if sub.empty:
        return []
    rows = []
    for _, r in sub.sort_values(["network", "scenario", "demand"]).iterrows():
        rows.append(
            [
                r["network"],
                r["scenario"],
                r["demand"],
                label(r["method"]),
                label(r["reference"]),
                f"{r['mean']:.1f}",
                f"{r['reference_mean']:.1f}",
                f"{r['improvement_pct']:+.1f}%",
                f"{r['paired_improvement_pct']:+.1f}% [{r['paired_ci_lo']:+.1f}, "
                f"{r['paired_ci_hi']:+.1f}]",
                f"{r['p_holm']:.3g}",
                f"{r['cliffs_delta']:+.2f} ({r['effect']})",
            ]
        )
    header = [
        "Network",
        "Scenario",
        "Demand",
        "Method",
        "Reference",
        "Mean",
        "Ref. mean",
        "Improvement",
        "Paired by test seed [95% CI]",
        "p (Holm)",
        "Cliff's delta",
    ]
    return _table(header, rows)


def build_report_tables(raw_dir: Path = RAW_DIR, summary_dir: Path = SUMMARY_DIR) -> Path:
    summary = pd.read_csv(summary_dir / "summary.csv")
    raw = pd.concat(
        [pd.read_csv(f) for f in sorted(Path(raw_dir).glob("*.csv"))], ignore_index=True
    )
    commits = sorted(raw["git_commit"].astype(str).unique())
    lines = [
        "# Report tables",
        "",
        f"Generated by `python -m cotraffic tables` from {len(raw)} runs in `results/raw` "
        f"(code versions: {', '.join(commits)}). Do not edit by hand.",
        "Each cell: mean over runs [95% bootstrap CI]. Lower is better except throughput.",
        "Learned methods: 3 training runs x 5 test seeds; their CI resamples both (two-way "
        "bootstrap). Baselines: 5 test seeds.",
        "",
    ]
    for network in sorted(summary["network"].unique()):
        lines += [f"## {network}", ""]
        for metric in ("mean_travel_time", "mean_waiting_time"):
            lines += demand_table(summary, network, "normal", metric)
        if "peak" in set(summary[summary["network"] == network]["demand"]):
            lines += metrics_table(summary, network, "normal", "peak", PEAK_METRICS)
        for scenario in sorted(
            set(summary[summary["network"] == network]["scenario"]) - {"normal"}
        ):
            metrics = SCENARIO_METRICS.get(scenario, DEFAULT_SCENARIO_METRICS)
            for demand in [d for d in DEMAND_ORDER if d in set(summary["demand"])]:
                lines += metrics_table(summary, network, scenario, demand, metrics)
    comp_file = summary_dir / "comparisons_mean_travel_time.csv"
    if comp_file.is_file():
        comp = pd.read_csv(comp_file)
        lines += [
            "## Comparisons - mean travel time",
            "",
            "Mann-Whitney U, Holm-corrected within each table; Cliff's delta < 0 means the "
            "method has lower travel times than the reference. The test treats the 15 runs of "
            "a learned method as independent although they come from 3 training runs, so its "
            "p-values are optimistic (conclusions with delta = +-1 are unaffected). "
            "Improvement > 0 = better; the paired column compares method and reference on the "
            "same test seed, with a two-way bootstrap CI.",
            "",
        ]
        for reference, family, title in (
            ("ft", "core", "Against fixed-time (FT)"),
            ("best_baseline", "core", "Against the best baseline of each cell"),
            (
                "best_baseline",
                "exploratory",
                "Exploratory: extended and sensitivity cells against the best baseline "
                "(separate Holm family)",
            ),
        ):
            table = comparison_table(comp, reference, family)
            if table:
                lines += [f"### {title}", ""] + table
        llm = comp[comp["method"] == "llm"]
        for reference, title in (
            ("mp", "LLM against Max-Pressure (the controller it falls back to)"),
            ("ft", "LLM against fixed-time (status quo)"),
            ("coop", "LLM against the learned cooperative policy"),
        ):
            table = comparison_table(llm, reference, "llm")
            if table:
                lines += [f"### {title}", ""] + table
    lines += llm_table(summary_dir)
    lines += hyperparameter_table(summary_dir, raw)
    lines += failures_table(raw)
    lines += training_table()
    lines += forecast_tables(summary_dir)
    lines += importance_tables(summary_dir)
    out = summary_dir / "REPORT_TABLES.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _plain(value: object) -> str:
    """A markdown-cell rendering of one number: NaN as '-' and no trailing '.0'."""
    if isinstance(value, float):
        if value != value:
            return "-"
        return str(int(value)) if value == int(value) else f"{value:.1f}"
    return str(value)


def llm_table(summary_dir: Path) -> list[str]:
    """Whether each LLM run described the model or its Max-Pressure fallback, and its cost.

    Without this table a rate-limited cell is indistinguishable from an LLM result; the
    comparison tables only ever contain rows whose status is ``ok``.
    """
    path = summary_dir / "llm_health.csv"
    if not path.is_file():
        return []
    health = pd.read_csv(path)
    if health.empty:
        return []
    ok = int(pd.to_numeric(health.get("llm_valid", 0), errors="coerce").fillna(0).sum())
    intro = (
        f"{len(health)} runs of the LLM controller, {ok} of them usable. `ok` means the "
        "provider was ready and the model answered every round it was asked in; "
        "`degraded` means some calls failed (quota, network, invalid JSON) and part of "
        "the episode ran on Max-Pressure; `budget` means the per-episode call cap was "
        "reached; `unavailable` means no API key. Anything but `ok` measures the fallback, "
        "so those runs are excluded from `summary.csv` and from the LLM comparisons above."
    )
    fields = [
        ("network", "Network"),
        ("demand", "Demand"),
        ("seed", "Seed"),
        ("llm_status", "Status"),
        ("llm_valid", "Valid"),
        ("llm_calls", "Calls"),
        ("llm_success", "Answered"),
        ("llm_errors", "Failed"),
        ("llm_rounds", "Rounds"),
        ("llm_coverage_pct", "Coverage %"),
        ("llm_fallbacks", "Fallbacks"),
        ("llm_prompt_tokens", "Prompt tok"),
        ("llm_completion_tokens", "Out tok"),
        ("llm_latency_ms_mean", "Latency ms"),
        ("llm_last_error", "Last error"),
    ]
    present = [(c, h) for c, h in fields if c in health.columns]
    order = [c for c, _ in present]
    rows = []
    for _, r in health.sort_values(
        [c for c in ("network", "demand", "seed") if c in health.columns]
    ).iterrows():
        row = []
        for column in order:
            text = _plain(r[column])
            if column == "llm_last_error":
                text = text[:60].replace("|", "/")
            row.append(text)
        rows.append(row)
    header = [h for _, h in present]
    return ["## LLM controller - is the model actually driving?", "", intro, ""] + _table(
        header, rows
    )


def hyperparameter_table(summary_dir: Path, raw: pd.DataFrame | None = None) -> list[str]:
    """One row per configuration actually run, with the knobs that produced the numbers."""
    path = summary_dir / "hyperparameters.csv"
    params = pd.read_csv(path) if path.is_file() else pd.DataFrame()
    legacy = 0
    if raw is not None:
        # Rows written before every result carried its configuration. Rather than leave
        # the table out (and let a reader assume the knobs are uninteresting), the report
        # states that those runs cannot be attributed to a configuration.
        legacy = (
            int(raw["parameters"].isna().sum())
            if "parameters" in raw.columns
            else len(raw)
        )
    if params.empty and not legacy:
        return []
    ordered = []
    grouped = (
        params.groupby(["method", "variant", "param_hash"], dropna=False)
        if not params.empty
        else []
    )
    for (method, variant, digest), group in grouped:
        knobs = " · ".join(
            f"{r['parameter']}={r['value']}"
            for _, r in group.sort_values("parameter").iterrows()
        )
        ordered.append((str(method), str(variant), str(digest), int(group["runs"].max()), knobs))
    ordered.sort(key=lambda r: (method_sort_key(r[0]), -r[3], r[2]))
    rows = [
        [label(method), variant, digest, str(runs), knobs.replace("|", "/")]
        for method, variant, digest, runs, knobs in ordered
    ]
    intro = (
        "Every configuration present in `results/raw`, read from each result row's "
        "`parameters`. `Config` is a digest of the whole parameter set, so rows sharing one "
        "came from the same model; `Runs` is how many result rows used it. For the learned "
        "variants the varying keys are the ones named in `configs/agents/*.yaml`."
    )
    if legacy:
        intro += (
            f" {legacy} run(s) predate the `parameters` column and are not listed: they were "
            "made before every result row recorded its configuration, and re-deriving their "
            "knobs from today's config files would describe the configs, not the runs."
        )
    header = ["Method", "Variant", "Config", "Runs", "Hyperparameters"]
    lines = ["## Hyperparameters of every configuration run", "", intro, ""]
    return lines + (_table(header, rows) if rows else [])


def failures_table(raw: pd.DataFrame) -> list[str]:
    """Teleports, unfinished and never-inserted vehicles per method and cell."""
    cols = [c for c in ("teleports_total", "unfinished", "never_inserted") if c in raw]
    if not cols:
        return []
    rows = []
    keys = ["network", "scenario", "demand", "method"]
    stats = raw.groupby(keys)[cols].agg(["mean", "max"])
    order = sorted(
        stats.index,
        key=lambda k: (
            k[0],
            k[1],
            DEMAND_ORDER.index(k[2]) if k[2] in DEMAND_ORDER else 9,
            method_sort_key(k[3]),
        ),
    )
    for key in order:
        r = stats.loc[key]
        rows.append(
            [key[0], key[1], key[2], label(key[3])]
            + [f"{r[(c, 'mean')]:.1f} ({r[(c, 'max')]:.0f})" for c in cols]
        )
    header = ["Network", "Scenario", "Demand", "Method"] + [
        f"{METRIC_LABELS.get(c, c.replace('_', ' '))} per run, mean (max)" for c in cols
    ]
    intro = (
        "A teleport is SUMO removing a vehicle stuck for 300 s (+300 s added to its travel "
        "time); unfinished vehicles are still in the network at the end, never-inserted ones "
        "could not enter it. All are counted in the travel-time metrics (ADR-005)."
    )
    return ["## Teleports and unfinished vehicles", "", intro, ""] + _table(header, rows)


def training_time(run: Path) -> tuple[float, str]:
    """Training time of a run (min) and a note when the measured time is not usable.

    Estimated as episodes x median time per episode (PPO updates included): the laptop was
    suspended during some runs, and a resumed run records only its last session.
    """
    import json

    log = run / "episodes.csv"
    if not log.is_file():
        return float("nan"), ""
    ep = pd.read_csv(log)
    step = ep["train_wall_s"].diff()
    step = step[step > 0]
    estimate = len(ep) * float(step.median()) / 60 if len(step) else float("nan")
    info = run / "run_info.json"
    sessions = (
        json.loads(info.read_text(encoding="utf-8")).get("sessions", []) if (info.is_file()) else []
    )
    measured = sum(x["wall_time_s"] for x in sessions) / 60
    notes = [
        f"resumed at {x['resumed_from_steps']:,} steps"
        for x in sessions
        if x.get("resumed_from_steps")
    ]
    if len(step) and step.max() > 5 * step.median():
        notes.append(f"laptop suspended during the run (measured {measured:.0f} min)")
    return estimate, "; ".join(notes)


def training_table() -> list[str]:
    """Training cost and selected checkpoint of every learned policy."""
    import json

    from cotraffic.paths import TRAINING_DIR

    rows = []
    for path in sorted(CHECKPOINTS_DIR.glob("*/*/seed*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        best = d["scores"][str(d["selected_steps"])]["mean_travel_time"]
        minutes, note = training_time(
            TRAINING_DIR / d["agent"] / d["network"] / f"seed{d['training_seed']}"
        )
        rows.append(
            [
                label(d["agent"]),
                d["network"],
                str(d["training_seed"]),
                f"{d.get('total_timesteps') or 0:,}",
                "-" if pd.isna(minutes) else f"{minutes:.0f}",
                f"{d['selected_steps']:,}",
                f"{best:.1f}",
                note,
            ]
        )
    if not rows:
        return []
    header = [
        "Variant",
        "Network",
        "Training seed",
        "Agent steps",
        "Training time (min)",
        "Selected checkpoint (steps)",
        "Validation travel time (s)",
        "Note",
    ]
    intro = (
        "Checkpoints chosen on validation seeds 1000+ (`python -m cotraffic select`). "
        "Training time = episodes x median time per episode, PPO updates included, with up "
        "to three runs sharing the laptop."
    )
    return ["## Training runs", "", intro, ""] + _table(header, rows)


def forecast_tables(summary_dir: Path) -> list[str]:
    lines: list[str] = []
    for path in sorted(summary_dir.glob("forecast_*.csv")):
        df = pd.read_csv(path)
        network = path.stem.removeprefix("forecast_")
        lines += [
            f"## Inflow forecasting - {network}",
            "",
            "Next-5-minute arrivals per approach (vehicles); MAE and RMSE on the test part.",
            "",
        ]
        for split in df["split"].unique():
            sub = df[(df["split"] == split) & (df["demand"] == "all")].sort_values("mae")
            rows = [
                [
                    r["model"],
                    f"{r['mae']:.2f}",
                    f"{r['rmse']:.2f}",
                    f"{r['mean_target']:.1f}",
                    str(r["n"]),
                ]
                for _, r in sub.iterrows()
            ]
            header = ["Model", "MAE", "RMSE", "Mean target", "Test rows"]
            lines += [f"**Split: {split}**", ""] + _table(header, rows)
    return lines


def importance_tables(summary_dir: Path) -> list[str]:
    lines: list[str] = []
    for path in sorted(summary_dir.glob("importance_*.csv")):
        df = pd.read_csv(path).sort_values("action_change_rate", ascending=False)
        first = df.iloc[0]
        base_ev = first.get("ev_delay_base", float("nan"))
        ev_text = "" if pd.isna(base_ev) else f", EV delay {base_ev:.1f} s"
        lines += [
            f"## Feature-group importance - {label(first['method'])}, {first['network']}",
            "",
            f"Demand `{first['demand']}`, scenario `{first['scenario']}`, seeds {first['seeds']}; "
            f"without shuffling: travel time {first['travel_time_base']:.1f} s{ev_text}. "
            "Blocks that are constant in these episodes are left out.",
            "",
        ]
        has_ev = "ev_delay_increase_pct" in df and df["ev_delay_increase_pct"].notna().any()
        rows = []
        for _, r in df.iterrows():
            row = [
                r["group"],
                f"{100 * r.get('active_share', 1.0):.0f}%",
                f"{100 * r['action_change_rate']:.1f}%",
                f"{100 * r.get('action_change_rate_active', r['action_change_rate']):.1f}%",
                f"{r['travel_time_increase_pct']:+.1f}%",
            ]
            if has_ev:
                row.append(f"{r['ev_delay_increase_pct']:+.0f}%")
            rows.append(row)
        header = [
            "Observation block",
            "Non-zero in",
            "Decisions changed (all)",
            "Decisions changed (block non-zero)",
            "Travel time when shuffled",
        ] + (["EV delay when shuffled"] if has_ev else [])
        lines += _table(header, rows)
    return lines
