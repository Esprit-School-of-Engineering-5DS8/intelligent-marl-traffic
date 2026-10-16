#!/usr/bin/env python3
"""
evaluation/collect_results.py
Phase 6 deliverable A (part 1): consolidate `results/<scenario>/<arm>/
seed_<n>/summary.json` into committed, deterministic CSV tables.

Outputs (under --out, default docs/test/phase6/tables):
- all_results.csv              one row per recorded run (all summary fields)
- per_scenario/<scen>_by_arm.csv  arms x metrics (mean +/- std over seeds)
- llm_ops.csv                  per-run LLM operations per role (calls,
                               latency from decisions.jsonl, tokens)

Notes:
- `results/` is gitignored; these CSVs are the committed artifact. Re-run
  after every experiment batch:
      python evaluation/collect_results.py
- Runs recorded with `--llm replay` (or `--llm mock`) are measurement-
  equivalent but carry no latency/token counters; they are flagged
  `recorded=False` in all_results.csv and excluded from latency/token
  aggregation in llm_ops.csv (call counts are still summarised).
- Arms with both `seed_none` and explicit seeds: the seeded runs win in the
  per-scenario tables (and the choice is stated in the `seeds` column).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

RUN_KEY_FIELDS = ["scenario", "arm", "seed"]

# Metrics aggregated in the per-scenario tables (order matters for the CSV).
AGG_METRICS = [
    "mean_step_waiting_time_s",
    "mean_speed_m_s",
    "arrived_vehicles",
    "mean_duration_s",
    "mean_tripinfo_waiting_s",
    "mean_time_loss_s",
    "ev_count",
    "ev_mean_duration_s",
    "ev_mean_waiting_s",
    "ev_max_duration_s",
    "ped_count",
    "ped_mean_waiting_s",
    "ped_p95_waiting_s",
    "ped_mean_duration_s",
    "llm_calls",
    "llm_fallbacks",
    "detector_alerts",
]

ROLES = ("operator", "emergency", "pedestrian")


def _to_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 4) -> Any:
    number = _to_float(value)
    return "" if number is None else round(number, digits)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
    return ordered[index]


def _load_summaries(results_root: str) -> List[Dict[str, Any]]:
    runs: List[Dict[str, Any]] = []
    for scenario in sorted(os.listdir(results_root)):
        scenario_dir = os.path.join(results_root, scenario)
        if not os.path.isdir(scenario_dir):
            continue
        for arm in sorted(os.listdir(scenario_dir)):
            arm_dir = os.path.join(scenario_dir, arm)
            if not os.path.isdir(arm_dir):
                continue
            for seed_dir in sorted(os.listdir(arm_dir)):
                if not seed_dir.startswith("seed_"):
                    continue
                path = os.path.join(arm_dir, seed_dir, "summary.json")
                if not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8") as handle:
                    summary = json.load(handle)
                summary.setdefault("scenario", scenario)
                summary.setdefault("arm", arm)
                summary.setdefault("seed", seed_dir[len("seed_"):])
                summary["_dir"] = os.path.join(arm_dir, seed_dir)
                runs.append(summary)
    return runs


def _llm_ops(run: Dict[str, Any]) -> Dict[str, Any]:
    """Per-role call counts plus recorded latency/token statistics."""
    recorded = (_to_float(run.get("llm_tokens_in")) or 0.0) > 0.0
    ops: Dict[str, Any] = {
        "scenario": run.get("scenario"),
        "arm": run.get("arm"),
        "seed": run.get("seed"),
        "recorded": int(recorded),
    }
    calls = {role: 0 for role in ROLES}
    fresh_calls = 0
    latencies: List[float] = []
    tokens_in = tokens_out = tokens_cached = 0.0
    decisions_path = os.path.join(str(run.get("_dir", "")), "decisions.jsonl")
    if os.path.isfile(decisions_path):
        with open(decisions_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = record.get("agent")
                if role not in calls:
                    continue
                calls[role] += 1
                if recorded:
                    latency = _to_float(record.get("latency_s"))
                    # Replayed cache hits carry latency 0.0 and no usage; only
                    # fresh endpoint calls feed the latency/token statistics
                    # (a run may mix a replayed checkpoint prefix with fresh
                    # calls after a resume).
                    if latency is not None and latency > 0.5:
                        fresh_calls += 1
                        latencies.append(latency)
                        tokens_in += _to_float(record.get("tokens_in")) or 0.0
                        tokens_out += _to_float(record.get("tokens_out")) or 0.0
                        tokens_cached += _to_float(record.get("tokens_cached")) or 0.0
    for role in ROLES:
        ops[f"calls_{role}"] = calls[role]
    ops["calls_total"] = sum(calls.values())
    ops["calls_fresh"] = fresh_calls
    ops["latency_mean_s"] = round(_mean(latencies), 3)
    ops["latency_median_s"] = round(statistics.median(latencies), 3) if latencies else ""
    ops["latency_p90_s"] = round(_percentile(latencies, 0.90), 3) if latencies else ""
    ops["latency_max_s"] = round(max(latencies), 3) if latencies else ""
    ops["tokens_in"] = int(tokens_in)
    ops["tokens_out"] = int(tokens_out)
    ops["tokens_cached"] = int(tokens_cached)
    return ops


def _pick_runs(runs: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """Prefer explicit seeds over seed_none for a (scenario, arm) group."""
    seeded = [run for run in runs if str(run.get("seed")) != "none"]
    if seeded:
        return seeded, "seeded"
    return list(runs), "seed_none"


def write_all_results(runs: Sequence[Dict[str, Any]], out_path: str) -> None:
    base_fields = ["scenario", "arm", "seed", "steps", "recorded"]
    extra_fields: List[str] = []
    for run in runs:
        for key in run:
            if key.startswith("_") or key in base_fields:
                continue
            if key not in extra_fields:
                extra_fields.append(key)
    fields = base_fields + sorted(extra_fields)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for run in sorted(runs, key=lambda r: (str(r["scenario"]), str(r["arm"]), str(r["seed"]))):
            record = {key: _round(run.get(key)) for key in fields}
            record["scenario"] = run.get("scenario")
            record["arm"] = run.get("arm")
            record["seed"] = run.get("seed")
            record["recorded"] = int((_to_float(run.get("llm_tokens_in")) or 0.0) > 0.0)
            writer.writerow(record)


def write_by_arm(runs: Sequence[Dict[str, Any]], scenario: str, out_path: str) -> None:
    by_arm: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        if run.get("scenario") != scenario:
            continue
        by_arm.setdefault(str(run.get("arm")), []).append(run)

    columns = ["scenario", "arm", "runs", "seeds"]
    for metric in AGG_METRICS:
        columns += [f"{metric}_mean", f"{metric}_std"]

    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for arm in sorted(by_arm):
            selected, seed_kind = _pick_runs(by_arm[arm])
            record: Dict[str, Any] = {
                "scenario": scenario,
                "arm": arm,
                "runs": len(selected),
                "seeds": seed_kind,
            }
            for metric in AGG_METRICS:
                values = [_to_float(run.get(metric)) for run in selected]
                present = [value for value in values if value is not None]
                record[f"{metric}_mean"] = round(_mean(present), 4)
                record[f"{metric}_std"] = round(_std(present), 4)
            writer.writerow(record)


def write_llm_ops(runs: Sequence[Dict[str, Any]], out_path: str) -> None:
    llm_runs = [run for run in runs if str(run.get("arm")) == "llm_team"]
    columns = [
        "scenario", "arm", "seed", "recorded",
        "calls_operator", "calls_emergency", "calls_pedestrian", "calls_total", "calls_fresh",
        "latency_mean_s", "latency_median_s", "latency_p90_s", "latency_max_s",
        "tokens_in", "tokens_out", "tokens_cached",
    ]
    rows = sorted(
        (_llm_ops(run) for run in llm_runs),
        key=lambda r: (str(r["scenario"]), str(r["seed"])),
    )
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate results/*/summary.json into committed tables")
    parser.add_argument("--results", default="results", help="results root directory")
    parser.add_argument("--out", default=os.path.join("docs", "test", "phase6", "tables"),
                        help="output directory for the committed tables")
    args = parser.parse_args()

    runs = _load_summaries(os.path.abspath(args.results))
    if not runs:
        parser.error(f"no summary.json found under {args.results}")

    out_root = os.path.abspath(args.out)
    per_scenario_dir = os.path.join(out_root, "per_scenario")
    os.makedirs(per_scenario_dir, exist_ok=True)

    all_path = os.path.join(out_root, "all_results.csv")
    write_all_results(runs, all_path)
    print(f"[csv] {all_path} ({len(runs)} runs)")

    scenarios = sorted({str(run.get("scenario")) for run in runs})
    for scenario in scenarios:
        path = os.path.join(per_scenario_dir, f"{scenario}_by_arm.csv")
        write_by_arm(runs, scenario, path)
        print(f"[csv] {path}")

    ops_path = os.path.join(out_root, "llm_ops.csv")
    write_llm_ops(runs, ops_path)
    print(f"[csv] {ops_path}")


if __name__ == "__main__":
    main()
