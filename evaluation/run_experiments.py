#!/usr/bin/env python3
"""
evaluation/run_experiments.py
Batch experiment runner: scenario x arm x seeds, one SUMO process per run.

Example:
    python evaluation/run_experiments.py \
        --scenario grid_3x3 --arms sumo_default,fixed,max_pressure \
        --seeds 0 --steps 3600 --jobs 3

Arms:
    sumo_default : SUMO's built-in pre-timed program (no controller)
    fixed        : baselines.fixed_time.FixedTimeAgent
    max_pressure : agents.max_pressure.MaxPressureAgent (topology lane groups)

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
from typing import Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agents.max_pressure import MaxPressureAgent
from baselines.fixed_time import FixedTimeAgent
from environment.multi_agent_env import MultiAgentEnv
from evaluation.metrics import parse_tripinfo, summarize_step_csv
from traci.exceptions import FatalTraCIError

ARMS = ("sumo_default", "fixed", "max_pressure")

SUMMARY_COLUMNS = [
    "scenario", "arm", "seed", "steps",
    "mean_step_waiting_time_s", "mean_speed_m_s", "arrived_vehicles",
    "mean_duration_s", "mean_tripinfo_waiting_s", "mean_time_loss_s",
]

AGG_METRICS = [
    "mean_step_waiting_time_s", "mean_speed_m_s",
    "arrived_vehicles", "mean_tripinfo_waiting_s",
]


def find_sumocfg(scenario_dir: str) -> str:
    candidates = sorted(f for f in os.listdir(scenario_dir) if f.endswith(".sumocfg"))
    if not candidates:
        raise FileNotFoundError(f"no .sumocfg found in {scenario_dir}")
    return os.path.join(scenario_dir, candidates[0])


def _build_policies(arm: str, tls_ids: List[str]) -> Dict[str, object]:
    if arm == "fixed":
        return {tls_id: FixedTimeAgent(tls_id) for tls_id in tls_ids}
    if arm == "max_pressure":
        return {tls_id: MaxPressureAgent(tls_id) for tls_id in tls_ids}
    return {}


def run_one(scenario: str, arm: str, seed: Optional[int], steps: int,
            out_root: str, port: int) -> Dict:
    """Run one (scenario, arm, seed) simulation in its own process."""
    scenario_dir = os.path.join(REPO_ROOT, "scenarios", scenario)
    sumocfg = find_sumocfg(scenario_dir)

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

    try:
        for _ in range(steps):
            if policies:
                states = env.get_states()
                env.apply_actions({
                    tls_id: policies[tls_id].select_action(states[tls_id])
                    for tls_id in tls_ids
                })
            env.step()
    except FatalTraCIError:
        pass
    finally:
        env.close(output_csv=step_csv)

    summary: Dict = {"scenario": scenario, "arm": arm, "seed": seed_label}
    summary.update(summarize_step_csv(step_csv))
    summary.update(parse_tripinfo(tripinfo)["summary"])
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

    print("=" * 72)
    print(f" {scenario} — results (mean ± std over seeds)")
    print("=" * 72)
    print(f"{'arm':<14}{'runs':>5}  {'step-wait(s)':>15}  {'speed(m/s)':>15}  {'arrived':>10}")
    for arm in sorted(by_arm):
        rows = by_arm[arm]
        print(f"{arm:<14}{len(rows):>5}  "
              f"{_format_metric(rows, 'mean_step_waiting_time_s'):>15}  "
              f"{_format_metric(rows, 'mean_speed_m_s'):>15}  "
              f"{_format_metric(rows, 'arrived_vehicles'):>10}")
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(
        description="Batch SUMO experiments (scenario x arm x seeds)")
    parser.add_argument("--scenario", default="grid_3x3",
                        help="comma-separated scenario folder(s) under scenarios/")
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
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenario.split(",") if s.strip()]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
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
            pool.submit(run_one, *job, args.steps, out_root, 8813 + index): job
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
