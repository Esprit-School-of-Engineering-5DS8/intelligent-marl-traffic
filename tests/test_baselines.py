"""
tests/test_baselines.py
Unit and integration tests for classical & heuristic reference baselines:
- FixedTimeAgent
- ActuatedAgent
- GreenWaveAgent
- MaxPressureAgent
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from baselines import FixedTimeAgent, ActuatedAgent, GreenWaveAgent, MaxPressureAgent
from environment.multi_agent_env import SumoMARLEnv


def test_agent_action_outputs():
    dummy_state = {
        "lane_queues": {"bottom0A0_0": 5, "left0A0_0": 2},
        "lane_counts": {"bottom0A0_0": 6, "left0A0_0": 3},
        "time_in_phase": 15,
        "sim_step": 20,
    }

    controllers = [
        FixedTimeAgent("A0", cycle_length=60),
        ActuatedAgent("A0", min_green=10, max_green=50),
        GreenWaveAgent("A0", cycle_length=60),
        MaxPressureAgent("A0"),
    ]

    for ctrl in controllers:
        action = ctrl.select_action(dummy_state)
        assert action in [0, 1], f"Controller {ctrl} returned invalid action {action}"

    print("[Test Actions] All baselines returned valid discrete actions!")


def test_baselines_in_simulation():
    sumocfg = os.path.join(PROJECT_ROOT, "scenarios", "grid_2x2", "grid2x2.sumocfg")
    controllers = {
        "fixed_time": lambda tls: FixedTimeAgent(tls, cycle_length=40),
        "actuated": lambda tls: ActuatedAgent(tls, min_green=5, max_green=30),
        "green_wave": lambda tls: GreenWaveAgent(tls, cycle_length=40),
        "max_pressure": lambda tls: MaxPressureAgent(tls),
    }

    for name, factory in controllers.items():
        env = SumoMARLEnv(sumocfg_path=sumocfg, max_steps=25, use_gui=False)
        try:
            obs, infos = env.reset(seed=42)
            agents = {tls: factory(tls) for tls in env.possible_agents}

            for step in range(20):
                actions = {tls: agents[tls].select_action(infos.get(tls, {})) for tls in env.agents}
                obs, rewards, terminations, truncations, infos = env.step(actions)
                if not env.agents:
                    break

            print(f"[Test Simulation] Controller '{name}' ran 20 steps successfully!")
        finally:
            env.close()


if __name__ == "__main__":
    print("Testing baseline action generation...")
    test_agent_action_outputs()
    print("Testing baselines inside SumoMARLEnv simulation...")
    test_baselines_in_simulation()
    print("[SUCCESS] All baseline controller tests passed successfully!")
