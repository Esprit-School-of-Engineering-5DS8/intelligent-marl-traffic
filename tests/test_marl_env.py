"""
tests/test_marl_env.py
Tests for SumoMARLEnv PettingZoo / Gymnasium standard compliance.
"""

import os
import sys
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from environment.multi_agent_env import SumoMARLEnv


def test_grid_2x2_env():
    sumocfg = os.path.join(PROJECT_ROOT, "scenarios", "grid_2x2", "grid2x2.sumocfg")
    assert os.path.exists(sumocfg), f"Missing {sumocfg}"

    env = SumoMARLEnv(sumocfg_path=sumocfg, max_steps=25)
    try:
        assert len(env.possible_agents) == 4, f"Expected 4 agents, got {len(env.possible_agents)}"
        print(f"[Test 2x2] Discovered agents: {env.possible_agents}")

        for agent in env.possible_agents:
            obs_space = env.observation_space(agent)
            act_space = env.action_space(agent)
            assert obs_space.shape[0] > 0
            assert act_space.n >= 2
            print(f"[Test 2x2] Agent {agent} -> Obs Shape: {obs_space.shape}, Action Dim: {act_space.n}")

        obs, infos = env.reset(seed=42)
        assert len(obs) == len(env.possible_agents)

        for step in range(15):
            actions = {agent: env.action_space(agent).sample() for agent in env.agents}
            next_obs, rewards, terminations, truncations, next_infos = env.step(actions)

            for agent in env.agents:
                assert agent in next_obs
                assert isinstance(rewards[agent], float)
                assert isinstance(terminations[agent], bool)
                assert isinstance(truncations[agent], bool)
                assert "lane_queues" in next_infos[agent]

        print("[Test 2x2] Simulation steps executed successfully!")
    finally:
        env.close()


def test_grid_3x3_env():
    sumocfg = os.path.join(PROJECT_ROOT, "scenarios", "grid_3x3", "grid3x3.sumocfg")
    assert os.path.exists(sumocfg), f"Missing {sumocfg}"

    env = SumoMARLEnv(sumocfg_path=sumocfg, max_steps=25)
    try:
        assert len(env.possible_agents) == 9, f"Expected 9 agents, got {len(env.possible_agents)}"
        print(f"[Test 3x3] Discovered agents: {env.possible_agents}")

        for agent in env.possible_agents:
            obs_space = env.observation_space(agent)
            act_space = env.action_space(agent)
            assert obs_space.shape[0] > 0
            assert act_space.n >= 2

        obs, infos = env.reset(seed=42)
        assert len(obs) == len(env.possible_agents)

        for step in range(15):
            actions = {agent: env.action_space(agent).sample() for agent in env.agents}
            next_obs, rewards, terminations, truncations, next_infos = env.step(actions)
            assert "__system__" in next_infos

        print("[Test 3x3] Simulation steps executed successfully!")
    finally:
        env.close()


if __name__ == "__main__":
    print("Running test_grid_2x2_env...")
    test_grid_2x2_env()
    print("Running test_grid_3x3_env...")
    test_grid_3x3_env()
    print("[SUCCESS] All MARL Environment tests passed!")
