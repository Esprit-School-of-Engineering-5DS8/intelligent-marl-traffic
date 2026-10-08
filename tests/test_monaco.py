"""
tests/test_monaco.py
Integration tests for Phase 3: Monaco SUMO Traffic (MoST) Scenario with SumoMARLEnv.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from environment.multi_agent_env import SumoMARLEnv


def test_monaco_env():
    sumocfg = os.path.join(PROJECT_ROOT, "scenarios", "monaco", "most.sumocfg")
    assert os.path.exists(sumocfg), f"Missing {sumocfg}"

    print("[Test Monaco] Initializing SumoMARLEnv on MoST scenario...")
    env = SumoMARLEnv(sumocfg_path=sumocfg, max_steps=20, use_gui=False)
    try:
        assert len(env.possible_agents) == 12, f"Expected 12 Monaco agents, got {len(env.possible_agents)}"
        print(f"[Test Monaco] Discovered {len(env.possible_agents)} traffic lights: {env.possible_agents}")

        obs, infos = env.reset(seed=42)
        assert len(obs) == 12

        for agent in env.possible_agents:
            obs_space = env.observation_space(agent)
            act_space = env.action_space(agent)
            assert obs_space.shape[0] > 0
            assert act_space.n >= 2

        for step in range(10):
            actions = {agent: env.action_space(agent).sample() for agent in env.agents}
            next_obs, rewards, terminations, truncations, next_infos = env.step(actions)
            for agent in env.agents:
                assert agent in next_obs
                assert isinstance(rewards[agent], float)

        print("[Test Monaco] 10 simulation steps executed successfully!")
    finally:
        env.close()


if __name__ == "__main__":
    test_monaco_env()
    print("[SUCCESS] Monaco integration tests passed successfully!")
