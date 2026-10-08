"""
tests/test_multimodal.py
Validates multi-modal traffic demand generation and environment metrics:
- Vehicle classes (Passenger, Bus, Emergency)
- Pedestrian flows and crossings
- Scenario presets (balanced, rush_hour, emergency_surge, pedestrian_heavy)
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scenarios.grid_2x2.generate_routes import generate_multimodal_routes as gen_2x2
from scenarios.grid_3x3.generate_routes import generate_multimodal_routes as gen_3x3
from environment.multi_agent_env import SumoMARLEnv


def test_scenario_generation():
    scenarios = ["balanced", "rush_hour", "emergency_surge", "pedestrian_heavy"]
    for sc in scenarios:
        gen_2x2(output_file=f"test_2x2_{sc}.rou.xml", scenario=sc, duration=300, total_vehicles=100, total_pedestrians=20)
        file_path = os.path.join(PROJECT_ROOT, "scenarios", "grid_2x2", f"test_2x2_{sc}.rou.xml")
        assert os.path.exists(file_path), f"Failed to generate {file_path}"
        os.remove(file_path)
    print("[Test Scenarios] All 4 scenario presets generated successfully!")


def test_multimodal_metrics_tracking():
    sumocfg = os.path.join(PROJECT_ROOT, "scenarios", "grid_3x3", "grid3x3.sumocfg")
    env = SumoMARLEnv(sumocfg_path=sumocfg, max_steps=75)
    try:
        obs, infos = env.reset(seed=42)
        tracked_ev = False
        tracked_ped = False

        for step in range(70):
            actions = {agent: 0 for agent in env.agents}
            obs, rewards, terminations, truncations, infos = env.step(actions)
            sys_info = infos.get("__system__", {})

            if sys_info.get("active_evs", 0) > 0:
                tracked_ev = True
            if sys_info.get("active_pedestrians", 0) > 0:
                tracked_ped = True

            # Verify info dictionary has multi-modal keys
            for agent in env.possible_agents:
                assert "pedestrian_count" in infos[agent]
                assert "emergency_approaching_count" in infos[agent]

        print(f"[Test Multi-modal] Active EV detected: {tracked_ev}, Active Pedestrians detected: {tracked_ped}")
    finally:
        env.close()


if __name__ == "__main__":
    print("Testing multi-modal scenario generation...")
    test_scenario_generation()
    print("Testing multi-modal metrics tracking in SumoMARLEnv...")
    test_multimodal_metrics_tracking()
    print("[SUCCESS] Multi-modal integration tests passed successfully!")
