# ADR-008: PPO with parameter sharing

- Status: accepted
- Date: 2026-09-24

## Context

Sixteen (grid) or seven (district) agents must be trained on a CPU laptop in minutes to
tens of minutes per run, and a policy trained on 16 intersections should run on 64.

## Options considered

| Option | For | Against |
|---|---|---|
| One network per intersection | can specialise | 16x the parameters and 1/16 of the data each; no transfer to a new intersection |
| Centralised policy (joint action) | sees everything | action space grows exponentially with the number of signals |
| Shared policy, local decisions (parameter sharing) | every decision of every intersection trains the same network; fixed input size -> transfers to any network with the same padding | intersections cannot specialise except through their observation |
| DQN | sample-efficient on discrete actions | replay buffer and target network tuning; less stable with non-stationary multi-agent data |
| PPO | robust defaults, on-policy data fits the non-stationarity of learning agents, discrete actions supported | less sample-efficient than DQN |

## Decision

PPO (Stable-Baselines3) with one shared MLP policy (2 x 64, tanh), each intersection
being one slot of the vectorised environment (SuperSuit). SB3 defaults except `n_steps`:
256 steps x 16 agents = 4 096 samples per update (the default 2 048 would give 32 768 and
only a handful of updates in our budget). Training episodes are 60 min with a demand level
and demand seed drawn at every reset (domain randomisation over low, medium, peak and the
rush-hour profile), from a fixed pool of training seeds shared by all variants.

Implementation notes:

- SuperSuit ends an episode with `terminal_observation` but does not mark time limits;
  the environment adds `TimeLimit.truncated` so that PPO bootstraps the value at the end
  of an episode instead of treating it as terminal.
- SuperSuit's `ConcatVecEnv` has no `seed()`, which SB3 calls when given a seed; we seed
  Python, NumPy, PyTorch and the environment's episode generator explicitly (F-006).

## Consequences

- Measured speed on the team laptop: see journal (M3).
- Parameter sharing is what allows the zero-shot evaluation on grid8x8 (RQ5).
