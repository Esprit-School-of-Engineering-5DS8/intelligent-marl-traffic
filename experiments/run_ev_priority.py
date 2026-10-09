#!/usr/bin/env python3
"""
run_ev_priority.py
Experiment driver for emergency vehicle priority (E1).

Runs a SUMO grid scenario with the EV demand file, applies a controller
(fixed-time, max-pressure, or the emergency-priority policy), tracks ambulance
and civilian metrics, and saves results under results/ev/.
"""

import os
import sys
import csv
import argparse
import xml.etree.ElementTree as ET

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from forecasting.ev_arrival_predictor import (FEATURE_COLUMNS, extract_ev_features,
                                               link_signal_char)

RESULTS_DIR = os.path.join(PROJECT_ROOT, "results", "ev")

ETA_HORIZON_M = 400.0


def build_environment(scenario, use_gui=False, seed=42):
    scenario_dir = os.path.join(PROJECT_ROOT, "scenarios", f"grid_{scenario}")
    if scenario_dir not in sys.path:
        sys.path.insert(0, scenario_dir)

    import runner

    class SeededMultiAgentEnvironment(runner.MultiAgentEnvironment):
        def start(self):
            binary_name = "sumo-gui" if self.use_gui else "sumo"
            try:
                import sumolib
                binary = sumolib.checkBinary(binary_name)
            except Exception:
                binary = binary_name

            cmd = [
                binary,
                "-c", self.sumocfg_path,
                "--step-length", str(self.step_length),
                "--no-warnings", "true",
                "--quit-on-end", "true",
                "--seed", str(seed),
            ]
            if self.use_gui:
                cmd.extend(["--start", "true", "--delay", str(self.delay_ms)])

            runner.traci.start(cmd)
            tls_ids = runner.traci.trafficlight.getIDList()
            print(f"[driver] {len(tls_ids)} traffic lights: {sorted(tls_ids)}")
            for tls_id in sorted(tls_ids):
                self.agents[tls_id] = runner.TrafficLightAgent(tls_id)

    cfg_name = f"grid{scenario}.ev.sumocfg"
    cfg_path = os.path.join(scenario_dir, cfg_name)
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"EV config not found: {cfg_path}")

    return SeededMultiAgentEnvironment(cfg_path, use_gui=use_gui), runner


def load_priority_policy():
    try:
        from agents.emergency_priority import select_action_priority
        return select_action_priority
    except ImportError:
        print("[driver] agents.emergency_priority not ready yet - using max_pressure placeholder.")
        return None


def parse_tripinfo(path):
    trips = []
    for t in ET.parse(path).getroot():
        attrs = dict(t.attrib)
        attrs["duration"] = float(attrs["duration"])
        attrs["waitingTime"] = float(attrs["waitingTime"])
        attrs["waitingCount"] = int(attrs["waitingCount"])
        attrs["timeLoss"] = float(attrs["timeLoss"])
        attrs["routeLength"] = float(attrs["routeLength"])
        trips.append(attrs)
    return trips


def run_trial(scenario, mode, steps, seed, collect_eta=False, rl_policy_path=None,
              rl_epsilon=1.0, collect_rl=False, skip_summary=False):
    env, runner = build_environment(scenario, seed=seed)
    scenario_dir = os.path.join(PROJECT_ROOT, "scenarios", f"grid_{scenario}")
    tripinfo_path = os.path.join(scenario_dir, "tripinfo_ev.xml")
    if os.path.exists(tripinfo_path):
        os.remove(tripinfo_path)

    priority_policy = load_priority_policy() if mode == "priority" else None

    os.makedirs(RESULTS_DIR, exist_ok=True)
    ev_distance = os.environ.get("EV_ACTIVATION_DISTANCE_M")
    eta_trigger = os.environ.get("EV_ETA_TRIGGER_S")
    tag = f"{scenario}_{mode}_seed{seed}"
    if mode == "priority" and ev_distance:
        tag += f"_evdist{ev_distance}"
    if mode == "priority" and eta_trigger and float(eta_trigger) > 0:
        tag += f"_etatrig{eta_trigger}"
    if mode == "rl" and rl_epsilon < 1.0:
        tag += f"_eps{rl_epsilon}"
    step_log_path = os.path.join(RESULTS_DIR, f"{tag}_steps.csv")

    rl_controller = None
    if mode == "rl":
        from agents.emergency_rl import EVRLController, EVRLPolicy
        from agents.emergency_priority import select_action_max_pressure as ev_fallback
        rl_policy = EVRLPolicy().load(rl_policy_path) if rl_policy_path else None
        predictor = None
        try:
            from forecasting.ev_arrival_predictor import EVArrivalPredictor
            predictor = EVArrivalPredictor().load()
        except Exception:
            pass
        rl_controller = EVRLController(
            fallback_policy=ev_fallback,
            predictor=predictor, policy=rl_policy, epsilon=rl_epsilon, run_tag=tag)

    env.start()
    step_rows = []
    ev_red_stops = {}
    ev_in_stop = {}
    eta_completed = []
    eta_pending = {}
    eta_last_char = {}
    prev_targets = {}
    ev_prev_first = {}
    ev_prev_char = {}
    pass_green = 0
    pass_total = 0

    try:
        for step in range(steps):
            states = env.get_states()
            if mode != "sumo_default":
                if mode == "rl":
                    actions = rl_controller.act(runner.traci, states)
                else:
                    actions = {}
                    for tls_id, state in states.items():
                        if mode == "fixed":
                            actions[tls_id] = runner.select_action_fixed(tls_id, step)
                        elif mode == "max_pressure":
                            actions[tls_id] = runner.select_action_max_pressure(state)
                        else:
                            if priority_policy is not None:
                                actions[tls_id] = priority_policy(tls_id, state)
                            else:
                                actions[tls_id] = runner.select_action_max_pressure(state)
                env.apply_actions(actions)

            env.step()

            traci = runner.traci
            veh_ids = traci.vehicle.getIDList()
            ev_ids = [v for v in veh_ids if traci.vehicle.getVehicleClass(v) == "emergency"]
            civ_ids = [v for v in veh_ids if v not in ev_ids]

            for v in ev_ids:
                speed = traci.vehicle.getSpeed(v)
                next_tls = traci.vehicle.getNextTLS(v)
                at_red = False
                if next_tls:
                    _, link_index, _, signal_field = next_tls[0]
                    at_red = link_signal_char(link_index, signal_field) in ("r", "R", "y")
                stopped = speed < 0.1
                if stopped and at_red and not ev_in_stop.get(v):
                    ev_red_stops[v] = ev_red_stops.get(v, 0) + 1
                    ev_in_stop[v] = True
                elif not (stopped and at_red):
                    ev_in_stop[v] = False

            for v in ev_ids:
                next_tls = traci.vehicle.getNextTLS(v)
                if next_tls:
                    light_id, link_index, _, signal_field = next_tls[0]
                    char = link_signal_char(link_index, signal_field)
                    prev_light = ev_prev_first.get(v)
                    if prev_light is not None and prev_light != light_id:
                        pass_green += 1 if ev_prev_char.get(v) in ("G", "g") else 0
                        pass_total += 1
                    ev_prev_first[v] = light_id
                    ev_prev_char[v] = char
            for v in [x for x in ev_prev_first if x not in ev_ids]:
                pass_green += 1 if ev_prev_char.get(v) in ("G", "g") else 0
                pass_total += 1
                ev_prev_first.pop(v, None)
                ev_prev_char.pop(v, None)

            if collect_eta:
                sim_time = traci.simulation.getTime()
                for v in ev_ids:
                    upcoming = traci.vehicle.getNextTLS(v)
                    current_targets = set()
                    for rank, (light_id, link_index, dist, signal_field) in enumerate(upcoming, start=1):
                        current_targets.add(light_id)
                        if rank > 2 or dist > ETA_HORIZON_M:
                            continue
                        features = extract_ev_features(traci, v, light_id, rank)
                        if features is None:
                            continue
                        snapshot = {"run_tag": tag, "ev_id": v, "tls_id": light_id,
                                    "rank": rank, "sim_time": sim_time, **features}
                        eta_pending.setdefault((v, light_id), []).append(snapshot)
                        eta_last_char[(v, light_id)] = link_signal_char(link_index, signal_field)
                    passed = prev_targets.get(v, set()) - current_targets
                    for light_id in passed:
                        for snap in eta_pending.pop((v, light_id), []):
                            row = dict(snap)
                            row["label_s"] = round(sim_time - snap["sim_time"], 2)
                            row["arrive_red"] = 0 if eta_last_char.get((v, light_id)) in ("G", "g") else 1
                            eta_completed.append(row)
                    prev_targets[v] = current_targets
                for v in list(prev_targets):
                    if v not in ev_ids:
                        for light_id in prev_targets.pop(v):
                            for snap in eta_pending.pop((v, light_id), []):
                                row = dict(snap)
                                row["label_s"] = round(sim_time - snap["sim_time"], 2)
                                row["arrive_red"] = 0 if eta_last_char.get((v, light_id)) in ("G", "g") else 1
                                eta_completed.append(row)

            civ_wait = sum(traci.vehicle.getWaitingTime(v) for v in civ_ids)
            step_rows.append({
                "step": step + 1,
                "active_evs": len(ev_ids),
                "active_civilians": len(civ_ids),
                "civilian_wait_total_s": round(civ_wait, 2),
            })

            if (step + 1) % 600 == 0:
                print(f"[driver] step {step + 1}/{steps} | EVs active: {len(ev_ids)}")
    finally:
        env.close(output_csv=os.path.join(RESULTS_DIR, f"{tag}_metrics.csv"))

    with open(step_log_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(step_rows[0].keys()))
        writer.writeheader()
        writer.writerows(step_rows)

    if collect_eta and eta_completed:
        eta_path = os.path.join(RESULTS_DIR, f"{tag}_eta.csv")
        fieldnames = (["run_tag", "ev_id", "tls_id", "rank", "sim_time"]
                      + FEATURE_COLUMNS + ["label_s", "arrive_red"])
        with open(eta_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(eta_completed)
        print(f"[driver] ETA dataset: {len(eta_completed)} rows -> {eta_path}")

    if rl_controller is not None:
        episodes = rl_controller.finish(sim_time=step_rows[-1]["step"] if step_rows else 0)
        if collect_rl and episodes:
            ep_path = os.path.join(RESULTS_DIR, f"{tag}_rl_episodes.csv")
            fieldnames = (["run_tag", "ev_id", "tls_id", "action", "strategy", "duration_s",
                           "ev_delay_s", "civilian_wait_mean_s", "reward"] + FEATURE_COLUMNS)
            with open(ep_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(episodes)
            print(f"[driver] RL episodes: {len(episodes)} rows -> {ep_path}")

    trips = parse_tripinfo(tripinfo_path)
    ev_trips = [t for t in trips if t["vType"] == "emergency"]
    total_stops_loop = sum(ev_red_stops.values())

    civ_wait_per_step = [
        r["civilian_wait_total_s"] / r["active_civilians"]
        for r in step_rows if r["active_civilians"] > 0
    ]
    summary = {
        "scenario": scenario,
        "mode": mode,
        "seed": seed,
        "ev_activation_distance_m": float(ev_distance) if (mode == "priority" and ev_distance) else "",
        "ev_eta_trigger_s": float(eta_trigger) if (mode == "priority" and eta_trigger and float(eta_trigger) > 0) else "",
        "steps": steps,
        "ev_trips": len(ev_trips),
        "ev_mean_duration_s": round(sum(t["duration"] for t in ev_trips) / len(ev_trips), 2) if ev_trips else 0.0,
        "ev_mean_waiting_s": round(sum(t["waitingTime"] for t in ev_trips) / len(ev_trips), 2) if ev_trips else 0.0,
        "ev_red_stops_loop": total_stops_loop,
        "ev_arrivals_on_green_pct": round(100.0 * pass_green / pass_total, 1) if pass_total else 0.0,
        "civilian_mean_wait_per_veh_s": round(sum(civ_wait_per_step) / len(civ_wait_per_step), 3),
        "throughput": int(sum(r["arrived_vehicles"] for r in env.history)),
        "mean_speed_m_s": round(
            sum(r["avg_speed_m_s"] for r in env.history if r["active_vehicles"] > 0)
            / max(1, sum(1 for r in env.history if r["active_vehicles"] > 0)), 2),
    }

    summary_path = os.path.join(RESULTS_DIR, "summary.csv")
    if not skip_summary:
        write_header = not os.path.exists(summary_path)
        with open(summary_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(summary)

    print("\n===== TRIAL SUMMARY =====")
    for key, value in summary.items():
        print(f"  {key:28}: {value}")
    print("=========================\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Emergency vehicle priority experiment driver")
    parser.add_argument("--scenario", choices=["2x2", "3x3"], default="2x2")
    parser.add_argument("--mode", choices=["sumo_default", "fixed", "max_pressure", "priority", "rl"],
                        default="fixed")
    parser.add_argument("--steps", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--collect-eta", action="store_true",
                        help="Record ETA training data (features + actual time to each upcoming light)")
    parser.add_argument("--rl-policy", default=None, help="Path to a trained RL policy artifact")
    parser.add_argument("--rl-epsilon", type=float, default=1.0, help="Exploration rate for RL decisions")
    parser.add_argument("--collect-rl", action="store_true", help="Record RL decision episodes")
    parser.add_argument("--no-summary", action="store_true",
                        help="Do not append this trial to results/ev/summary.csv")
    args = parser.parse_args()

    run_trial(args.scenario, args.mode, args.steps, args.seed, collect_eta=args.collect_eta,
              rl_policy_path=args.rl_policy, rl_epsilon=args.rl_epsilon,
              collect_rl=args.collect_rl, skip_summary=args.no_summary)


if __name__ == "__main__":
    main()
