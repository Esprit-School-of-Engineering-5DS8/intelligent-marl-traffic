#!/usr/bin/env python3
"""
evaluation/report_plots.py
Phase 6 deliverable A (part 2): figures for the report, from the recorded
runs in `results/` (gitignored). Output PNGs go to docs/test/phase6/figures/.

Figures
- step_wait_<scenario>.png : mean step waiting time over time (mean across
  seeds per arm) with event windows shaded.
- bars_ev.png             : EV duration / waiting per scenario and arm.
- bars_ped.png            : pedestrian mean / p95 waiting (S4, S5).
- bars_civilian.png       : civilian step-wait, tripinfo wait and time loss.
- bars_arrivals.png       : arrived vehicles per scenario and arm.
- llm_ops.png             : LLM calls by role and recorded-call latency.

Owner note: `evaluation/visualize_metrics.py` belongs to Member 5 (F5); this
script is the Phase 6 report generator and does not touch it.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from evaluation.collect_results import _load_summaries, _pick_runs  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ARM_COLORS = {
    "sumo_default": "#444444",
    "fixed": "#999999",
    "max_pressure": "#1f77b4",
    "ev_priority": "#2ca02c",
    "ped_priority": "#ff7f0e",
    "llm_team": "#d62728",
}

# Shaded event windows / vertical EV departures per scenario (seconds).
EVENTS: Dict[str, List[Dict[str, Any]]] = {
    "grid_3x3": [{"start": 600, "end": 600.001, "label": "EV depart", "color": "#ffd966"}],
    "grid_3x3_peak": [],
    "grid_3x3_incident": [
        {"start": 1200, "end": 1500, "label": "incident A1A0", "color": "#ffcccc"},
    ],
    "grid_3x3_ev": [{"start": 600, "end": 600.001, "label": "EV depart", "color": "#ffd966"}],
    "grid_3x3_ev2": [
        {"start": 600, "end": 600.001, "label": "EV1", "color": "#ffd966"},
        {"start": 615, "end": 615.001, "label": "EV2", "color": "#ffeab3"},
    ],
    "grid_3x3_ev_incident": [
        {"start": 600, "end": 600.001, "label": "EV depart", "color": "#ffd966"},
        {"start": 620, "end": 860, "label": "incident B1B0", "color": "#ffcccc"},
    ],
    "grid_3x3_ped": [
        {"start": 300, "end": 540, "label": "pedestrian burst B1", "color": "#cce5ff"},
    ],
    "grid_3x3_ped_combo": [
        {"start": 300, "end": 540, "label": "pedestrian burst", "color": "#cce5ff"},
        {"start": 400, "end": 640, "label": "incident A1A0", "color": "#ffcccc"},
        {"start": 450, "end": 450.001, "label": "EV depart", "color": "#ffd966"},
    ],
    # MoST has continuous real emergency traffic; no fixed event window.
    "monaco": [],
}


def _load_step_waits(run_dir: str) -> List[float]:
    path = os.path.join(run_dir, "simulation_metrics.csv")
    if not os.path.isfile(path):
        return []
    waits: List[float] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                waits.append(float(row["total_waiting_time_s"]))
            except (KeyError, TypeError, ValueError):
                waits.append(0.0)
    return waits


def _mean_curve(curves: Sequence[Sequence[float]]) -> List[float]:
    if not curves:
        return []
    length = min(len(curve) for curve in curves)
    return [sum(curve[i] for curve in curves) / len(curves) for i in range(length)]


def _group_by_arm(runs: Sequence[Dict[str, Any]], scenario: str) -> Dict[str, List[Dict[str, Any]]]:
    by_arm: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        if run.get("scenario") != scenario:
            continue
        by_arm.setdefault(str(run.get("arm")), []).append(run)
    return {arm: _pick_runs(group)[0] for arm, group in by_arm.items()}


def _mean_std(runs: Sequence[Dict[str, Any]], metric: str) -> Tuple[float, float]:
    values = [float(run[metric]) for run in runs if run.get(metric) is not None]
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    var = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, var ** 0.5


def _mark_events(ax, scenario: str) -> None:
    for event in EVENTS.get(scenario, []):
        if event["end"] - event["start"] <= 1.0:
            ax.axvline(event["start"], color=event["color"], linewidth=2.5, linestyle="--")
            ax.text(event["start"], 0.98, event["label"], rotation=90, va="top", ha="right",
                    fontsize=7, transform=ax.get_xaxis_transform())
        else:
            ax.axvspan(event["start"], event["end"], color=event["color"], alpha=0.45, zorder=0)
            ax.text((event["start"] + event["end"]) / 2, 0.98, event["label"],
                    va="top", ha="center", fontsize=7, transform=ax.get_xaxis_transform())


def plot_step_wait(runs: Sequence[Dict[str, Any]], scenario: str, out_path: str) -> None:
    by_arm = _group_by_arm(runs, scenario)
    if not by_arm:
        return
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for arm in sorted(by_arm):
        curves = [_load_step_waits(run["_dir"]) for run in by_arm[arm]]
        curves = [curve for curve in curves if curve]
        if not curves:
            continue
        curve = _mean_curve(curves)
        x = list(range(1, len(curve) + 1))
        ax.plot(x, curve, label=f"{arm} (n={len(curves)})", color=ARM_COLORS.get(arm), linewidth=1.6)
    _mark_events(ax, scenario)
    ax.set_xlabel("simulation time (s)")
    ax.set_ylabel("total waiting time (s)")
    ax.set_title(f"{scenario}: mean total step waiting time")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _bar_panel(ax, scenarios: Sequence[str], runs: Sequence[Dict[str, Any]],
               metric: str, ylabel: str, title: str) -> None:
    width = 0.8 / max(1, len(ARM_COLORS))
    arms_used: List[str] = []
    for scenario in scenarios:
        for arm in _group_by_arm(runs, scenario):
            if arm not in arms_used:
                arms_used.append(arm)
    arms_used = [arm for arm in ARM_COLORS if arm in arms_used]
    positions = range(len(scenarios))
    for index, arm in enumerate(arms_used):
        means, stds, xs = [], [], []
        for scenario_index, scenario in enumerate(scenarios):
            group = _group_by_arm(runs, scenario).get(arm)
            if not group:
                continue
            mean, std = _mean_std(group, metric)
            means.append(mean)
            stds.append(std)
            xs.append(scenario_index + (index - (len(arms_used) - 1) / 2) * width)
        ax.bar(xs, means, width=width, yerr=stds, capsize=2, label=arm,
               color=ARM_COLORS.get(arm))
    ax.set_xticks(list(positions))
    ax.set_xticklabels([scenario.replace("grid_3x3", "S").replace("_", "\n") for scenario in scenarios],
                       fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.25, axis="y")


def plot_bars(runs: Sequence[Dict[str, Any]], out_dir: str) -> None:
    ev_scenarios = ["grid_3x3_ev", "grid_3x3_ev2", "grid_3x3_ev_incident", "grid_3x3_ped_combo", "monaco"]
    ped_scenarios = ["grid_3x3_ped", "grid_3x3_ped_combo"]
    civ_scenarios = ["grid_3x3", "grid_3x3_peak", "grid_3x3_incident", "monaco"]
    all_scenarios = ["grid_3x3", "grid_3x3_peak", "grid_3x3_incident",
                     "grid_3x3_ev", "grid_3x3_ev2", "grid_3x3_ev_incident",
                     "grid_3x3_ped", "grid_3x3_ped_combo", "monaco"]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    _bar_panel(axes[0], ev_scenarios, runs, "ev_mean_duration_s", "s", "EV travel time")
    _bar_panel(axes[1], ev_scenarios, runs, "ev_mean_waiting_s", "s", "EV waiting time")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "bars_ev.png"), dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    _bar_panel(axes[0], ped_scenarios, runs, "ped_mean_waiting_s", "s", "Pedestrian mean wait")
    _bar_panel(axes[1], ped_scenarios, runs, "ped_p95_waiting_s", "s", "Pedestrian p95 wait")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "bars_ped.png"), dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    _bar_panel(axes[0], civ_scenarios, runs, "mean_step_waiting_time_s", "s", "Civilian mean step wait")
    _bar_panel(axes[1], civ_scenarios, runs, "mean_tripinfo_waiting_s", "s", "Civilian tripinfo wait")
    _bar_panel(axes[2], civ_scenarios, runs, "mean_time_loss_s", "s", "Civilian time loss")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "bars_civilian.png"), dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4))
    _bar_panel(ax, all_scenarios, runs, "arrived_vehicles", "vehicles", "Arrived vehicles")
    ax.legend(fontsize=7, ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "bars_arrivals.png"), dpi=150)
    plt.close(fig)


def _grouped_bars(ax, cluster_labels, arms, values_by, title, ylabel,
                  colors=None, annotate=None):
    """
    Grouped bar helper for headline panels.

    `values_by[(arm, cluster_label)] = (mean, std)`; clusters on the x axis,
    one bar per arm inside a cluster. `annotate` optionally maps an arm to a
    short label drawn above its bars.
    """
    colors = colors or ARM_COLORS
    cluster_count = len(cluster_labels)
    width = 0.8 / max(1, len(arms))
    for index, arm in enumerate(arms):
        xs, means, stds = [], [], []
        for cluster_index, label in enumerate(cluster_labels):
            value = values_by.get((arm, label))
            if value is None:
                continue
            xs.append(cluster_index + (index - (len(arms) - 1) / 2) * width)
            means.append(value[0])
            stds.append(value[1])
        ax.bar(xs, means, width=width, yerr=stds, capsize=2,
               color=colors.get(arm, "#888888"), label=arm)
    ax.set_xticks(range(cluster_count))
    ax.set_xticklabels(cluster_labels, fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.25, axis="y")
    ax.legend(fontsize=8)
    if annotate:
        for arm, note in annotate.items():
            if any((arm, label) in values_by for label in cluster_labels):
                ax.text(0.99, 0.02, note, transform=ax.transAxes, ha="right",
                        fontsize=7, color=colors.get(arm, "#888888"))


def _scenario_metric_values(runs, scenarios, arms, metric,
                            scenario_labels=None):
    values = {}
    labels = scenario_labels or scenarios
    for scenario, label in zip(scenarios, labels):
        by_arm = _group_by_arm(runs, scenario)
        for arm in arms:
            group = by_arm.get(arm)
            if group:
                values[(arm, label)] = _mean_std(group, metric)
    return values


def plot_headline_grid(runs: Sequence[Dict[str, Any]], out_path: str) -> None:
    """One figure with the four decisive 3x3 results."""
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8))

    # (a) S3 incident: step-wait curves (A3 is bit-identical to A2 here).
    ax = axes[0][0]
    for arm in ("sumo_default", "max_pressure", "llm_team"):
        group = _group_by_arm(runs, "grid_3x3_incident").get(arm)
        if not group:
            continue
        curves = [_load_step_waits(run["_dir"]) for run in group]
        curves = [curve for curve in curves if curve]
        if not curves:
            continue
        curve = _mean_curve(curves)
        ax.plot(range(1, len(curve) + 1), curve, color=ARM_COLORS.get(arm),
                linewidth=1.5, label=arm)
    _mark_events(ax, "grid_3x3_incident")
    ax.set_title("S3 incident: step waiting time  (A3 = A2)", fontsize=10)
    ax.set_xlabel("sim time (s)")
    ax.set_ylabel("total wait (s)")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)

    # (b) EV travel time across the EV scenarios.
    ax = axes[0][1]
    scenarios = ["grid_3x3_ev", "grid_3x3_ev2", "grid_3x3_ev_incident",
                 "grid_3x3_ped_combo"]
    values = _scenario_metric_values(runs, scenarios,
                                     ["max_pressure", "ev_priority", "llm_team"],
                                     "ev_mean_duration_s",
                                     ["1 EV", "2 EVs", "EV+incident", "combo S5"])
    _grouped_bars(ax, ["1 EV", "2 EVs", "EV+incident", "combo S5"],
                  ["max_pressure", "ev_priority", "llm_team"], values,
                  "EV travel time (lower is better)", "s")

    # (c) S4 pedestrian waits.
    ax = axes[1][0]
    group_by_arm = _group_by_arm(runs, "grid_3x3_ped")
    values = {}
    for arm in ("max_pressure", "ped_priority", "llm_team"):
        group = group_by_arm.get(arm)
        if not group:
            continue
        values[(arm, "mean")] = _mean_std(group, "ped_mean_waiting_s")
        values[(arm, "p95")] = _mean_std(group, "ped_p95_waiting_s")
    _grouped_bars(ax, ["mean", "p95"], ["max_pressure", "ped_priority", "llm_team"],
                  values, "S4 pedestrian wait, 5 seeds", "s")

    # (d) Civilian step wait: the LLM team never costs more than its base.
    ax = axes[1][1]
    scenarios = ["grid_3x3", "grid_3x3_peak", "grid_3x3_incident",
                 "grid_3x3_ped_combo"]
    values = _scenario_metric_values(runs, scenarios,
                                     ["max_pressure", "llm_team"],
                                     "mean_step_waiting_time_s",
                                     ["S0", "S1", "S3", "S5"])
    _grouped_bars(ax, ["S0", "S1", "S3", "S5"], ["max_pressure", "llm_team"],
                  values, "Civilian step wait: LLM team vs base policy", "s")

    fig.suptitle("3x3 grid: headline results", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_headline_monaco(runs: Sequence[Dict[str, Any]], out_path: str) -> None:
    """One figure with the four decisive MoST Monaco results."""
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.5))
    arms = ["sumo_default", "max_pressure", "llm_team"]

    # (a) step-wait curves
    ax = axes[0][0]
    for arm in arms:
        group = _group_by_arm(runs, "monaco").get(arm)
        if not group:
            continue
        curves = [_load_step_waits(run["_dir"]) for run in group]
        curves = [curve for curve in curves if curve]
        if not curves:
            continue
        curve = _mean_curve(curves)
        ax.plot(range(1, len(curve) + 1), curve, color=ARM_COLORS.get(arm),
                linewidth=1.5, label=arm)
    ax.set_xlabel("sim time (s, 07:00 start)")
    ax.set_ylabel("total wait (s)")
    ax.set_title("MoST Monaco: step waiting time", fontsize=10)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)

    # (b) emergency-vehicle travel and waiting time
    ax = axes[0][1]
    group_by_arm = _group_by_arm(runs, "monaco")
    values = {}
    for arm in arms:
        group = group_by_arm.get(arm)
        if not group:
            continue
        values[(arm, "duration")] = _mean_std(group, "ev_mean_duration_s")
        values[(arm, "waiting")] = _mean_std(group, "ev_mean_waiting_s")
    _grouped_bars(ax, ["duration", "waiting"], arms, values,
                  "Real emergency fleet (vClass=emergency)", "s")

    # (c) arrivals
    ax = axes[1][0]
    values = _scenario_metric_values(runs, ["monaco"], arms, "arrived_vehicles",
                                     ["arrived"])
    _grouped_bars(ax, ["arrived"], arms, values,
                  "Completed civilian vehicles", "vehicles")

    # (d) pedestrian waits
    ax = axes[1][1]
    values = {}
    for arm in arms:
        group = group_by_arm.get(arm)
        if not group:
            continue
        values[(arm, "mean")] = _mean_std(group, "ped_mean_waiting_s")
        values[(arm, "p95")] = _mean_std(group, "ped_p95_waiting_s")
    _grouped_bars(ax, ["mean", "p95"], arms, values,
                  "Pedestrian wait (<personinfo>)", "s")

    fig.suptitle("MoST Monaco: headline results", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_llm_ops(runs: Sequence[Dict[str, Any]], out_dir: str) -> None:
    llm_runs = [run for run in runs if str(run.get("arm")) == "llm_team"]
    scenarios = sorted({str(run.get("scenario")) for run in llm_runs})
    roles = ["operator", "emergency", "pedestrian"]
    colors = {"operator": "#1f77b4", "emergency": "#d62728", "pedestrian": "#2ca02c"}

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    ax = axes[0]
    width = 0.25
    for role_index, role in enumerate(roles):
        xs, means = [], []
        for scenario_index, scenario in enumerate(scenarios):
            groups = _pick_runs([run for run in llm_runs if run.get("scenario") == scenario])[0]
            key = f"llm_{role}_calls"
            values = [float(run.get(key, 0) or 0) for run in groups]
            if not values or max(values) <= 0:
                continue
            value = sum(values) / len(values)
            means.append(value)
            xs.append(scenario_index + (role_index - 1) * width)
        if means:
            ax.bar(xs, means, width=width, label=role, color=colors[role])
    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels([s.replace("grid_3x3", "S").replace("_", "\n") for s in scenarios], fontsize=8)
    ax.set_ylabel("LLM calls per run (mean over seeds)")
    ax.set_title("LLM calls by role", fontsize=10)
    ax.grid(alpha=0.25, axis="y")
    ax.legend(fontsize=8)

    # Recorded latencies from decisions.jsonl (replayed/mock runs excluded).
    ax = axes[1]
    latencies_by_scenario: List[Tuple[str, List[float]]] = []
    for scenario in scenarios:
        values: List[float] = []
        for run in llm_runs:
            if run.get("scenario") != scenario:
                continue
            if not ((run.get("llm_tokens_in") or 0) > 0):
                continue
            path = os.path.join(run["_dir"], "decisions.jsonl")
            if not os.path.isfile(path):
                continue
            import json
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if record.get("agent") in roles and record.get("latency_s") is not None:
                        values.append(float(record["latency_s"]))
        if values:
            latencies_by_scenario.append((scenario, values))
    if latencies_by_scenario:
        ax.boxplot([values for _, values in latencies_by_scenario], tick_labels=[
            scenario.replace("grid_3x3", "S").replace("_", "\n")
            for scenario, _ in latencies_by_scenario], showfliers=False)
    ax.set_ylabel("latency per call (s)")
    ax.set_title("Recorded call latency (cache-miss batches)", fontsize=10)
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "llm_ops.png"), dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Phase 6 report figures from results/")
    parser.add_argument("--results", default="results")
    parser.add_argument("--out", default=os.path.join("docs", "test", "phase6", "figures"))
    args = parser.parse_args()

    runs = _load_summaries(os.path.abspath(args.results))
    if not runs:
        parser.error(f"no summary.json found under {args.results}")
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    for scenario in sorted({str(run.get("scenario")) for run in runs}):
        path = os.path.join(out_dir, f"step_wait_{scenario}.png")
        plot_step_wait(runs, scenario, path)
        print(f"[fig] {path}")
    plot_bars(runs, out_dir)
    print(f"[fig] {out_dir}/bars_*.png")
    plot_headline_grid(runs, os.path.join(out_dir, "headline_grid_3x3.png"))
    print(f"[fig] {out_dir}/headline_grid_3x3.png")
    plot_headline_monaco(runs, os.path.join(out_dir, "headline_monaco.png"))
    print(f"[fig] {out_dir}/headline_monaco.png")
    plot_llm_ops(runs, out_dir)
    print(f"[fig] {out_dir}/llm_ops.png")


if __name__ == "__main__":
    main()
