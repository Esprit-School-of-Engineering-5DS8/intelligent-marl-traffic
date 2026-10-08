"""
evaluation/benchmark_baselines.py
Automated benchmark evaluator for reference baseline controllers (F2 & F5).

Compares:
1. Fixed-Time (pre-timed cycles)
2. Actuated (gap-out / max-out)
3. Green Wave (arterial progression)
4. Max-Pressure (queue-pressure heuristic)

Collects system KPIs and prints a comparative performance scoreboard.
"""

import os
import sys
import argparse
import pandas as pd
from typing import Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from environment.multi_agent_env import SumoMARLEnv
from baselines import FixedTimeAgent, ActuatedAgent, GreenWaveAgent, MaxPressureAgent


def get_agent_factory(controller_name: str):
    """Returns a function that instantiates the requested controller for a given tls_id."""
    name = controller_name.lower()
    if name == "fixed_time":
        return lambda tls: FixedTimeAgent(tls, cycle_length=60)
    elif name == "actuated":
        return lambda tls: ActuatedAgent(tls, min_green=10, max_green=50)
    elif name == "green_wave":
        return lambda tls: GreenWaveAgent(tls, cycle_length=60, corridor="EW")
    elif name == "max_pressure":
        return lambda tls: MaxPressureAgent(tls)
    else:
        raise ValueError(f"Unknown controller: {controller_name}")


def run_benchmark_trial(
    controller_name: str,
    sumocfg_path: str,
    steps: int = 300,
    seed: int = 42,
) -> Dict[str, Any]:
    """Runs a single simulation trial with the given controller and computes summary KPIs."""
    print(f"  --> Running trial: {controller_name} ({steps} steps)...")
    env = SumoMARLEnv(sumocfg_path=sumocfg_path, max_steps=steps, use_gui=False)

    try:
        obs, infos = env.reset(seed=seed)
        factory = get_agent_factory(controller_name)
        agents = {tls: factory(tls) for tls in env.possible_agents}

        for step in range(steps):
            actions = {}
            for tls in env.agents:
                # Provide state dictionary to the agent
                agent_state = infos.get(tls, {})
                agent_state["sim_step"] = step
                actions[tls] = agents[tls].select_action(agent_state)

            next_obs, rewards, terminations, truncations, infos = env.step(actions)
            if not env.agents:
                break

        # Extract KPIs from simulation history
        history = env.history
        if not history:
            return {}

        df = pd.DataFrame(history)
        last_step = df.iloc[-1]

        avg_speed = df["avg_speed_m_s"].mean()
        total_delay = last_step["total_waiting_time_s"]
        arrived = last_step["arrived_vehicles"]
        total_co2_kg = df["co2_mg_s"].sum() / 1e6
        total_fuel_l = df["fuel_ml_s"].sum() / 1e3
        ev_delay = last_step.get("ev_waiting_time_s", 0.0)
        ped_delay = last_step.get("pedestrian_waiting_time_s", 0.0)

        return {
            "Controller": controller_name,
            "Mean Speed (m/s)": round(avg_speed, 2),
            "Total Delay (s)": round(total_delay, 1),
            "Throughput": int(arrived),
            "CO2 (kg)": round(total_co2_kg, 2),
            "Fuel (L)": round(total_fuel_l, 2),
            "EV Delay (s)": round(ev_delay, 1),
            "Ped Delay (s)": round(ped_delay, 1),
        }
    finally:
        env.close()


def run_full_benchmark(scenario: str = "3x3", steps: int = 300):
    scenario_dir = f"grid_{scenario}"
    sumocfg = os.path.join(PROJECT_ROOT, "scenarios", scenario_dir, f"grid{scenario}.sumocfg")

    controllers = ["fixed_time", "actuated", "green_wave", "max_pressure"]

    print(f"\n=======================================================")
    print(f"  SUMO MARL BASELINE BENCHMARK — {scenario.upper()} GRID")
    print(f"=======================================================\n")

    results = []
    for ctrl in controllers:
        res = run_benchmark_trial(ctrl, sumocfg_path=sumocfg, steps=steps)
        if res:
            results.append(res)

    results_df = pd.DataFrame(results)

    print("\n" + "=" * 70)
    print("                    BENCHMARK SCOREBOARD")
    print("=" * 70)
    print(results_df.to_string(index=False))
    print("=" * 70)

    # Save to CSV
    output_dir = os.path.join(PROJECT_ROOT, "results")
    os.makedirs(output_dir, exist_ok=True)
    out_csv = os.path.join(output_dir, f"baseline_benchmark_{scenario}.csv")
    results_df.to_csv(out_csv, index=False)
    print(f"\nScoreboard saved to: {out_csv}\n")
    return results_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark reference baseline controllers")
    parser.add_argument("--scenario", choices=["2x2", "3x3"], default="3x3", help="Grid scenario to benchmark")
    parser.add_argument("--steps", type=int, default=300, help="Simulation steps per controller trial")
    args = parser.parse_args()

    run_full_benchmark(scenario=args.scenario, steps=args.steps)
