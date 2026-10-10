#!/usr/bin/env python3
"""
evaluation/run_experiments.py
Batch experiment runner: scenario x arm x seeds, one SUMO process per run.

Example:
    python evaluation/run_experiments.py \
        --scenario grid_3x3 --arms sumo_default,fixed,max_pressure \
        --seeds 0 --steps 3600 --jobs 3

Scenarios come from evaluation/scenarios.py (S0 base, S1 peak, S2 EV, S3
incident). Arms:
    sumo_default : SUMO's built-in pre-timed program (no controller)
    fixed        : baselines.fixed_time.FixedTimeAgent
    max_pressure : agents.max_pressure.MaxPressureAgent (topology lane groups)
    ev_priority  : max_pressure + agents.ev_preemption (rule-based A3)

Seeds: `--seeds 0` runs without an explicit --seed (SUMO default RNG); pass
e.g. `--seeds 1,2,3` for reproducible multi-seed runs. Each run writes
results/<scenario>/<arm>/seed_<n>/ with the step CSV, tripinfo and summary.
"""

import argparse
import csv
import json
import multiprocessing
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from typing import Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agents.ev_preemption import RuleBasedEVPreemption
from agents.max_pressure import MaxPressureAgent
from baselines.fixed_time import FixedTimeAgent
from environment.ev import get_active_evs
from environment.incidents import IncidentInjector
from environment.multi_agent_env import MultiAgentEnv
from evaluation.metrics import parse_tripinfo, summarize_evs, summarize_step_csv
from evaluation.scenarios import SCENARIOS
import traci
from traci.exceptions import FatalTraCIError

ARMS = ("sumo_default", "fixed", "max_pressure", "ev_priority")

SUMMARY_COLUMNS = [
    "scenario", "arm", "seed", "steps",
    "mean_step_waiting_time_s", "mean_speed_m_s", "arrived_vehicles",
    "mean_duration_s", "mean_tripinfo_waiting_s", "mean_time_loss_s",
    "ev_count", "ev_mean_duration_s", "ev_mean_waiting_s",
    "ev_mean_waiting_count", "ev_max_duration_s",
]

AGG_METRICS = [
    "mean_step_waiting_time_s", "mean_speed_m_s",
    "arrived_vehicles", "mean_tripinfo_waiting_s",
    "ev_mean_duration_s", "ev_mean_waiting_s",
]


def _build_policies(arm: str, tls_ids: List[str]) -> Dict[str, object]:
    if arm == "fixed":
        return {tls_id: FixedTimeAgent(tls_id) for tls_id in tls_ids}
    if arm in ("max_pressure", "ev_priority"):
        return {tls_id: MaxPressureAgent(tls_id) for tls_id in tls_ids}
    return {}


def run_one(scenario: str, arm: str, seed: Optional[int], steps: int,
            out_root: str, port: int,
            incident_start: Optional[float] = None,
            incident_duration: Optional[float] = None) -> Dict:
    """Run one (scenario, arm, seed) simulation in its own process."""
    spec = SCENARIOS[scenario]
    sumocfg = os.path.join(REPO_ROOT, "scenarios", spec.folder, spec.cfg)

    seed_label = "none" if seed is None else str(seed)
    run_dir = os.path.join(out_root, scenario, arm, f"seed_{seed_label}")
    os.makedirs(run_dir, exist_ok=True)
    step_csv = os.path.join(run_dir, "simulation_metrics.csv")
    tripinfo = os.path.join(run_dir, "tripinfo.xml")

    env = MultiAgentEnv(sumocfg, seed=seed, tripinfo_output=tripinfo, port=port)
    tls_ids = env.start()
    policies = _build_policies(arm, tls_ids)
    if policies:
        env.build_agents()

    preemption = None
    if arm == "ev_priority":
        topologies = {tls_id: env.agents[tls_id].topology for tls_id in tls_ids}
        preemption = RuleBasedEVPreemption(topologies)

    incident_spec = spec.incident
    if incident_spec is not None:
        overrides = {}
        if incident_start is not None:
            overrides["start_s"] = incident_start
        if incident_duration is not None:
            overrides["duration_s"] = incident_duration
        if overrides:
            incident_spec = replace(incident_spec, **overrides)
    injector = IncidentInjector(incident_spec) if incident_spec is not None else None

    try:
        for _ in range(steps):
            if injector is not None:
                injector.apply(traci.simulation.getTime())
            if policies:
                states = env.get_states()
                evs = get_active_evs() if preemption is not None else []
                if preemption is not None:
                    preemption.begin_step(evs)
                actions = {}
                for tls_id in tls_ids:
                    action = policies[tls_id].select_action(states[tls_id])
                    if preemption is not None:
                        action = preemption.select_action(tls_id, action, evs)
                    actions[tls_id] = action
                env.apply_actions(actions)
            env.step()
    except FatalTraCIError:
        pass
    finally:
        env.close(output_csv=step_csv)

    tripinfo_result = parse_tripinfo(tripinfo)
    summary: Dict = {"scenario": scenario, "arm": arm, "seed": seed_label}
    summary.update(summarize_step_csv(step_csv))
    summary.update(tripinfo_result["summary"])
    summary.update(summarize_evs(tripinfo_result["vehicles"]))
    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return summary


def write_summary_csv(out_root: str, scenario: str, results: List[Dict]) -> str:
    path = os.path.join(out_root, scenario, "summary.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(results, key=lambda r: (r["arm"], str(r["seed"]))):
            writer.writerow(row)
    return path


def write_by_arm_csv(out_root: str, scenario: str, results: List[Dict]) -> str:
    path = os.path.join(out_root, scenario, "summary_by_arm.csv")
    by_arm: Dict[str, List[Dict]] = {}
    for row in results:
        by_arm.setdefault(row["arm"], []).append(row)

    columns = ["scenario", "arm", "runs"]
    for metric in AGG_METRICS:
        columns += [f"{metric}_mean", f"{metric}_std"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for arm in sorted(by_arm):
            rows = by_arm[arm]
            record = {"scenario": scenario, "arm": arm, "runs": len(rows)}
            for metric in AGG_METRICS:
                values = [float(row[metric]) for row in rows]
                record[f"{metric}_mean"] = statistics.mean(values)
                record[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
            writer.writerow(record)
    return path


def _format_metric(rows: List[Dict], metric: str) -> str:
    values = [float(row[metric]) for row in rows]
    if len(values) == 1:
        return f"{values[0]:.2f}"
    return f"{statistics.mean(values):.2f} ± {statistics.stdev(values):.2f}"


def print_summary(scenario: str, results: List[Dict]):
    by_arm: Dict[str, List[Dict]] = {}
    for row in results:
        by_arm.setdefault(row["arm"], []).append(row)

    has_ev = any(row.get("ev_count", 0) for row in results)

    print("=" * 72)
    print(f" {scenario} — results (mean ± std over seeds)")
    print("=" * 72)
    header = (f"{'arm':<14}{'runs':>5}  {'step-wait(s)':>15}  "
              f"{'speed(m/s)':>15}  {'arrived':>10}")
    if has_ev:
        header += f"  {'ev-dur(s)':>10}"
    print(header)
    for arm in sorted(by_arm):
        rows = by_arm[arm]
        line = (f"{arm:<14}{len(rows):>5}  "
                f"{_format_metric(rows, 'mean_step_waiting_time_s'):>15}  "
                f"{_format_metric(rows, 'mean_speed_m_s'):>15}  "
                f"{_format_metric(rows, 'arrived_vehicles'):>10}")
        if has_ev:
            line += f"  {_format_metric(rows, 'ev_mean_duration_s'):>10}"
        print(line)
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(
        description="Batch SUMO experiments (scenario x arm x seeds)")
    parser.add_argument("--scenario", default="grid_3x3",
                        help=f"comma-separated scenario names from evaluation/scenarios.py "
                             f"({', '.join(sorted(SCENARIOS))})")
    parser.add_argument("--arms", default=",".join(ARMS),
                        help=f"comma-separated arms ({', '.join(ARMS)})")
    parser.add_argument("--seeds", default="0",
                        help="comma-separated seeds; 0 means no explicit --seed")
    parser.add_argument("--steps", type=int, default=3600,
                        help="simulation steps per run")
    parser.add_argument("--jobs", type=int, default=1,
                        help="parallel SUMO processes")
    parser.add_argument("--out", default="results",
                        help="output root directory (gitignored)")
    parser.add_argument("--incident-start", type=float, default=None,
                        help="override incident start time (incident scenarios only)")
    parser.add_argument("--incident-duration", type=float, default=None,
                        help="override incident duration (incident scenarios only)")
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenario.split(",") if s.strip()]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown_scenarios = [s for s in scenarios if s not in SCENARIOS]
    if unknown_scenarios:
        parser.error(f"unknown scenario(s): {unknown_scenarios}; "
                     f"available: {sorted(SCENARIOS)}")
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        parser.error(f"unknown arm(s): {unknown}; available: {list(ARMS)}")
    seeds = [None if s.strip() in ("0", "none") else int(s)
             for s in args.seeds.split(",") if s.strip()]

    out_root = os.path.abspath(args.out)
    jobs = [(scenario, arm, seed)
            for scenario in scenarios for arm in arms for seed in seeds]
    print(f"Running {len(jobs)} run(s): {len(scenarios)} scenario(s) x "
          f"{len(arms)} arm(s) x {len(seeds)} seed(s), jobs={args.jobs}")

    results_by_scenario: Dict[str, List[Dict]] = {scenario: [] for scenario in scenarios}
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=args.jobs, mp_context=context) as pool:
        futures = {
            pool.submit(run_one, *job, args.steps, out_root, 8813 + index,
                        args.incident_start, args.incident_duration): job
            for index, job in enumerate(jobs)
        }
        for future in as_completed(futures):
            scenario, arm, seed = futures[future]
            try:
                results_by_scenario[scenario].append(future.result())
                print(f"[done] {scenario} | {arm} | seed={seed}")
            except Exception as exc:
                print(f"[fail] {scenario} | {arm} | seed={seed}: {exc!r}")

    for scenario, results in results_by_scenario.items():
        if not results:
            continue
        print(f"[csv] {write_summary_csv(out_root, scenario, results)}")
        print(f"[csv] {write_by_arm_csv(out_root, scenario, results)}")
        print_summary(scenario, results)


if __name__ == "__main__":
    main()
