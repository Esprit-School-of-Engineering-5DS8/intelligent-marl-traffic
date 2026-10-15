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
    ev_priority  : max_pressure + agents.ev_preemption (rule-based A3, through
                   the arbiter/DirectiveLayer)
    ped_priority : max_pressure + agents.ped_priority (rule-based pedestrian
                   windows through the arbiter/DirectiveLayer; the H4 baseline)
    llm_team     : max_pressure + arbiter/DirectiveLayer + Supervisor (A4) with
                   the Operator, Emergency and (on pedestrian scenarios)
                   Pedestrian agents. `--llm` selects the backend:
                     mock   : deterministic stand-in, empty directives
                              (a run is bit-identical to max_pressure)
                     openai : OpenAICompatClient from .env/LLM_* variables,
                              wrapped in a ReplayLLM cache (records)
                     replay : ReplayLLM in strict mode; cache misses raise,
                              so replays never spend tokens

The code queue detector feeds `queue_growth` alerts to the Operator and
triggers an immediate run when a new alert fires (S3 incident path).

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
from agents.llm.agent import LLMAgent
from agents.llm.client import CallLogger, LLMClient, MockLLM, OpenAICompatClient, ReplayLLM
from agents.llm.emergency_agent import EmergencyAgent
from agents.llm.env import load_repo_env
from agents.llm.pedestrian_agent import PedestrianAgent
from agents.max_pressure import MaxPressureAgent
from agents.ped_priority import RuleBasedPedestrianPriority
from agents.supervisor.arbiter import Arbiter
from agents.supervisor.directive_layer import DirectiveLayer
from agents.supervisor.supervisor import Supervisor, SupervisorConfig
from baselines.fixed_time import FixedTimeAgent
from environment.detectors import QueueAlertDetector
from environment.ev import get_active_evs
from environment.incidents import IncidentInjector
from environment.multi_agent_env import MultiAgentEnv
from environment.pedestrians import crossing_axis_map, get_pedestrian_states
from evaluation.metrics import parse_tripinfo, summarize_evs, summarize_pedestrians, summarize_step_csv
from evaluation.scenarios import SCENARIOS
import traci
from traci.exceptions import FatalTraCIError

ARMS = ("sumo_default", "fixed", "max_pressure", "ev_priority", "ped_priority", "llm_team")

SUMMARY_COLUMNS = [
    "scenario", "arm", "seed", "steps",
    "mean_step_waiting_time_s", "mean_speed_m_s", "arrived_vehicles",
    "mean_duration_s", "mean_tripinfo_waiting_s", "mean_time_loss_s",
    "ev_count", "ev_mean_duration_s", "ev_mean_waiting_s",
    "ev_mean_waiting_count", "ev_max_duration_s",
    "ped_count", "ped_mean_waiting_s", "ped_p95_waiting_s", "ped_mean_duration_s",
    "llm_calls", "llm_operator_calls", "llm_emergency_calls", "llm_pedestrian_calls",
    "llm_fallbacks", "llm_retries", "detector_alerts",
]

AGG_METRICS = [
    "mean_step_waiting_time_s", "mean_speed_m_s",
    "arrived_vehicles", "mean_tripinfo_waiting_s",
    "ev_mean_duration_s", "ev_mean_waiting_s",
    "ped_mean_waiting_s",
]


def _build_policies(arm: str, tls_ids: List[str]) -> Dict[str, object]:
    if arm == "fixed":
        return {tls_id: FixedTimeAgent(tls_id) for tls_id in tls_ids}
    if arm in ("max_pressure", "ev_priority", "ped_priority", "llm_team"):
        return {tls_id: MaxPressureAgent(tls_id) for tls_id in tls_ids}
    return {}


def _build_llm_client(backend: str, run_dir: str) -> LLMClient:
    """LLM backend shared by the Operator and Emergency agents."""
    if backend == "mock":
        return MockLLM()
    cache_path = os.path.join(run_dir, "llm_cache.jsonl")
    if backend == "replay":
        return ReplayLLM(OpenAICompatClient(), cache_path, strict=True)
    return ReplayLLM(OpenAICompatClient(), cache_path)


def run_one(scenario: str, arm: str, seed: Optional[int], steps: int,
            out_root: str, port: int,
            incident_start: Optional[float] = None,
            incident_duration: Optional[float] = None,
            llm_backend: str = "mock") -> Dict:
    """Run one (scenario, arm, seed) simulation in its own process."""
    spec = SCENARIOS[scenario]
    sumocfg = os.path.join(REPO_ROOT, "scenarios", spec.folder, spec.cfg)

    seed_label = "none" if seed is None else str(seed)
    run_dir = os.path.join(out_root, scenario, arm, f"seed_{seed_label}")
    os.makedirs(run_dir, exist_ok=True)
    step_csv = os.path.join(run_dir, "simulation_metrics.csv")
    tripinfo = os.path.join(run_dir, "tripinfo.xml")
    # Per-run log is rebuilt every run; the replay cache persists (keyed).
    decisions_path = os.path.join(run_dir, "decisions.jsonl")
    if os.path.exists(decisions_path):
        os.remove(decisions_path)

    env = MultiAgentEnv(sumocfg, seed=seed, tripinfo_output=tripinfo, port=port)
    tls_ids = env.start()
    policies = _build_policies(arm, tls_ids)
    if policies:
        env.build_agents()

    ped_topologies: Dict[str, object] = {}
    ped_axis_map: Dict[str, tuple] = {}
    if policies and spec.pedestrians and arm in ("ped_priority", "llm_team"):
        ped_topologies = {tls_id: env.agents[tls_id].topology for tls_id in tls_ids}
        ped_axis_map = crossing_axis_map(ped_topologies)

    arbiter = None
    layer = None
    ev_source = None
    ped_source = None
    supervisor = None
    detector = None
    if arm in ("ev_priority", "ped_priority"):
        topologies = {tls_id: env.agents[tls_id].topology for tls_id in tls_ids}
        arbiter = Arbiter(tls_ids)
        layer = DirectiveLayer()
        if arm == "ev_priority":
            ev_source = RuleBasedEVPreemption(topologies)
        else:
            ped_source = RuleBasedPedestrianPriority()
    elif arm == "llm_team":
        arbiter = Arbiter(tls_ids)
        layer = DirectiveLayer()
        detector = QueueAlertDetector()
        max_calls = int(os.environ.get("LLM_MAX_CALLS", "400") or "400")
        base_effort = os.environ.get("LLM_REASONING_EFFORT", "")
        escalate_effort = os.environ.get("LLM_ESCALATE_EFFORT", "medium")
        topologies = {tls_id: env.agents[tls_id].topology for tls_id in tls_ids}
        if llm_backend == "mock":
            # Offline stand-ins only: no unguided preemptions, so the arm is
            # bit-identical to max_pressure when the grid has no events.
            agents = {
                "operator": LLMAgent("operator", MockLLM()),
                "emergency": LLMAgent("emergency", MockLLM()),
            }
            if spec.pedestrians:
                agents["pedestrian"] = LLMAgent("pedestrian", MockLLM())
        else:
            client = _build_llm_client(llm_backend, run_dir)
            if spec.emergency_lead_s is not None:
                emergency_lead = spec.emergency_lead_s
            else:
                # Pedestrian nets have 6-phase programs (clearance + yellow =
                # ~8 s of transition); give the emergency reviewer more lead.
                emergency_lead = 20.0 if spec.pedestrians else 15.0
            agents = {
                "operator": LLMAgent("operator", client),
                # Real LLM corridor planning + reviewer + rule-based fallback.
                "emergency": EmergencyAgent(
                    client, topologies=topologies,
                    lead_time_s=emergency_lead),
            }
            if spec.pedestrians:
                agents["pedestrian"] = PedestrianAgent(client)
        supervisor = Supervisor(
            agents=agents,
            arbiter=arbiter,
            logger=CallLogger(decisions_path),
            neighbors=env.neighbors,
            pedestrian_trigger=spec.pedestrians,
            config=SupervisorConfig(max_calls=max_calls, base_effort=base_effort,
                                    escalate_effort=escalate_effort),
        )

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
            sim_time = traci.simulation.getTime()
            if injector is not None:
                injector.apply(sim_time)
            if policies:
                states = env.get_states()
                evs = get_active_evs() if (ev_source is not None or supervisor is not None) else []
                pedestrians = (get_pedestrian_states(ped_topologies, crossing_axis=ped_axis_map)
                               if ped_topologies else [])
                if ev_source is not None:
                    for envelope in ev_source.propose(evs, sim_time):
                        result = arbiter.submit("emergency", envelope, sim_time, states)
                        layer.install(result.accepted, sim_time)
                if ped_source is not None:
                    for envelope in ped_source.propose(pedestrians, sim_time):
                        result = arbiter.submit("pedestrian", envelope, sim_time, states)
                        layer.install(result.accepted, sim_time)
                new_alerts = detector.update(states, sim_time) if detector is not None else []
                if supervisor is not None:
                    periodic = supervisor.should_run(sim_time, states, evs, new_alerts,
                                                     pedestrians)
                    if periodic or new_alerts:
                        active_alerts = [a.to_dict() for a in detector.active(sim_time)]
                        force_roles = ("operator",) if new_alerts else ()
                        for result in supervisor.run(sim_time, states, evs, active_alerts,
                                                     force_roles, pedestrians):
                            layer.install(result.accepted, sim_time)
                actions = {}
                for tls_id in tls_ids:
                    action = policies[tls_id].select_action(states[tls_id])
                    if layer is not None:
                        action = layer.apply(tls_id, states[tls_id], action, sim_time)
                    actions[tls_id] = action
                env.apply_actions(actions)
            env.step()
    except FatalTraCIError:
        pass
    finally:
        if layer is not None and supervisor is not None:
            for event in layer.drain_events():
                supervisor.logger.log(event)
        env.close(output_csv=step_csv)

    tripinfo_result = parse_tripinfo(tripinfo, exclude_vtypes=spec.ev_vtypes)
    summary: Dict = {"scenario": scenario, "arm": arm, "seed": seed_label}
    summary.update(summarize_step_csv(step_csv))
    summary.update(tripinfo_result["summary"])
    summary.update(summarize_evs(tripinfo_result["vehicles"], vtypes=spec.ev_vtypes))
    summary.update(summarize_pedestrians(tripinfo))
    if supervisor is not None:
        summary["llm_calls"] = supervisor.stats["calls"]
        summary["llm_operator_calls"] = supervisor.stats.get("operator_calls", 0)
        summary["llm_emergency_calls"] = supervisor.stats.get("emergency_calls", 0)
        summary["llm_pedestrian_calls"] = supervisor.stats.get("pedestrian_calls", 0)
        summary["llm_fallbacks"] = supervisor.stats["fallbacks"]
        summary["llm_retries"] = supervisor.stats["retries"]
        summary["llm_escalated"] = supervisor.stats["escalated"]
        summary["llm_tokens_in"] = supervisor.stats["tokens_in"]
        summary["llm_tokens_out"] = supervisor.stats["tokens_out"]
        summary["llm_tokens_cached"] = supervisor.stats["tokens_cached"]
    if detector is not None:
        summary["detector_alerts"] = detector.count
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
    parser.add_argument("--llm", default="mock", choices=("mock", "openai", "replay"),
                        help="LLM backend for the llm_team arm's Operator + "
                             "Emergency agents (mock: offline stand-ins; openai: "
                             ".env/LLM_* endpoint, recording a replay cache; "
                             "replay: strict cache only)")
    args = parser.parse_args()

    env_path = load_repo_env()
    if env_path:
        print(f"[env] loaded {env_path}")
    if args.llm != "mock" and "llm_team" not in args.arms:
        print(f"[warn] --llm {args.llm} has no effect without the llm_team arm")

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
                        args.incident_start, args.incident_duration,
                        args.llm): job
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
