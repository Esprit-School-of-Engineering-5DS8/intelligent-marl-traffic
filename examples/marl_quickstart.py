"""
examples/marl_quickstart.py
Demonstration of using SumoMARLEnv (PettingZoo / Gymnasium compliant)
for multi-agent traffic signal control.

Usage:
    python examples/marl_quickstart.py --scenario 2x2 --steps 120 --gui --delay 150
"""

import os
import sys
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from environment.multi_agent_env import SumoMARLEnv


def main():
    parser = argparse.ArgumentParser(description="Quickstart demonstration for SumoMARLEnv")
    parser.add_argument("--scenario", choices=["2x2", "3x3", "monaco"], default="3x3", help="Scenario to run")
    parser.add_argument("--steps", type=int, default=100, help="Number of simulation steps")
    parser.add_argument("--gui", action="store_true", help="Launch SUMO with graphical interface")
    parser.add_argument(
        "--delay",
        type=int,
        default=150,
        help="Delay in milliseconds per step in GUI mode (default: 150ms for human visualization)",
    )
    args = parser.parse_args()

    if args.scenario == "monaco":
        sumocfg = os.path.join(PROJECT_ROOT, "scenarios", "monaco", "most.sumocfg")
    else:
        scenario_dir = f"grid_{args.scenario}"
        sumocfg = os.path.join(PROJECT_ROOT, "scenarios", scenario_dir, f"grid{args.scenario}.sumocfg")

    print(f"=== Initializing SumoMARLEnv for {args.scenario} scenario ===")
    if args.gui:
        print(f"Running in GUI mode with {args.delay}ms step delay for smooth visualization.")

    env = SumoMARLEnv(
        sumocfg_path=sumocfg,
        use_gui=args.gui,
        max_steps=args.steps,
        min_green=10,
        yellow_time=3,
        delay_ms=args.delay,
        reward_weights={
            "waiting_time": -0.01,
            "queue": -0.2,
            "co2": -0.0001,
            "pedestrian": -0.02,
            "emergency": -1.0,
        },
    )

    try:
        print(f"Discovered {len(env.possible_agents)} agents: {env.possible_agents}")
        for agent in env.possible_agents:
            print(f"  [{agent}] Observation space: {env.observation_space(agent).shape}, Action space: {env.action_space(agent).n}")

        observations, infos = env.reset(seed=42)
        total_rewards = {agent: 0.0 for agent in env.possible_agents}

        for step in range(args.steps):
            # Sample discrete action per agent (0 = Green NS, 1 = Green EW)
            # In training, replace this sample() with agent.select_action(observations[agent])
            actions = {agent: env.action_space(agent).sample() for agent in env.agents}

            next_obs, rewards, terminations, truncations, infos = env.step(actions)

            for agent, r in rewards.items():
                total_rewards[agent] += r

            if (step + 1) % 25 == 0 or (step + 1) == args.steps:
                sys_kpis = infos.get("__system__", {})
                print(
                    f"Step {step+1:3d}/{args.steps} | "
                    f"Active: {sys_kpis.get('active_vehicles', 0):2d} (EVs: {sys_kpis.get('active_evs', 0):1d}) | "
                    f"Peds: {sys_kpis.get('active_pedestrians', 0):2d} | "
                    f"Avg Speed: {sys_kpis.get('avg_speed_m_s', 0):.2f} m/s | "
                    f"Total Delay: {sys_kpis.get('total_waiting_time_s', 0):.1f}s"
                )

            if not env.agents:
                print("Simulation episode finished.")
                break

        print("\nEpisode complete. Cumulative rewards per agent:")
        for agent, tot_r in total_rewards.items():
            print(f"  {agent}: {tot_r:.2f}")

        if args.gui:
            input("\nSimulation complete! Press Enter in this terminal to close the SUMO GUI window...")

    finally:
        env.close(output_csv="quickstart_metrics.csv")
        print("Performance metrics saved to quickstart_metrics.csv")


if __name__ == "__main__":
    main()
