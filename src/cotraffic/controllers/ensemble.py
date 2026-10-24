"""PPO + DQN ensemble: IND (PPO) and DQN share the observation and the reward, so their
decisions can be combined at every step without retraining.

PPO gives a probability per phase; DQN gives a Q-value per phase, turned into
probabilities with a softmax whose temperature is the mean spread of the Q-values over all
intersections at that step (Q-values have no fixed scale; a per-state scale would erase
how much more confident DQN is at one junction than at another). The phase with the
highest weighted average of the two
distributions is requested; it then goes through the safety shield like every action.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cotraffic.controllers.base import Controller
from cotraffic.controllers.rl_policy import LearnedPolicy


class PpoDqnEnsemble(Controller):
    needs_observations = True

    def __init__(self, ppo_checkpoint: Path, dqn_checkpoint: Path, weight: float = 0.5) -> None:
        super().__init__()
        self.name = "ens"
        self.ppo = LearnedPolicy("ind", ppo_checkpoint)
        self.dqn = LearnedPolicy("dqn", dqn_checkpoint)
        self.weight = float(weight)  # share of PPO in the vote
        self.agent_cfg = self.ppo.agent_cfg

    def reset(self, env) -> None:
        self.ppo.reset(env)
        self.dqn.reset(env)

    def probabilities(self, batch: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        import torch

        with torch.no_grad():
            ppo_obs = self.ppo.model.policy.obs_to_tensor(batch)[0]
            p_ppo = self.ppo.model.policy.get_distribution(ppo_obs).distribution.probs.numpy()
            dqn_obs = self.dqn.model.policy.obs_to_tensor(batch)[0]
            q = self.dqn.model.q_net(dqn_obs).numpy()
        tau = float(np.abs(q - q.mean(axis=1, keepdims=True)).mean()) + 1e-6
        z = (q - q.max(axis=1, keepdims=True)) / tau
        p_dqn = np.exp(z) / np.exp(z).sum(axis=1, keepdims=True)
        return p_ppo, p_dqn

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        agents = list(obs)
        p_ppo, p_dqn = self.probabilities(np.stack([obs[a] for a in agents]))
        vote = self.weight * p_ppo + (1.0 - self.weight) * p_dqn
        return {a: int(x) for a, x in zip(agents, vote.argmax(axis=1), strict=True)}
