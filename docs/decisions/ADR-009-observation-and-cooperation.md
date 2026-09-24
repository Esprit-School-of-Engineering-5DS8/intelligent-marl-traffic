# ADR-009: What an agent observes, and how agents cooperate

- Status: accepted
- Date: 2026-09-24

## Context

Brief questions 1 and 3: what information should an agent use, and should agents work
independently or cooperate?

## Decision - observation (all values scaled to about [0, 1])

| Block | Content | Why |
|---|---|---|
| lanes | per incoming lane slot: queue / capacity, vehicles / capacity, mean speed / limit | what a loop or camera detector measures |
| phase | current phase (one-hot), for each phase the queue it would serve and its pressure (density upstream - downstream), time in phase / max green, min green satisfied | makes the meaning of each action explicit; the pressure is Max-Pressure's own signal |
| neighbours (COOP) | from the upstream neighbour on each side: its queue heading to us, whether it is releasing traffic toward us, its largest phase pressure | anticipate platoons and spillback |
| emergency (COOP-FULL) | per side: emergency vehicle approaching and its proximity; per phase: proximity of an emergency vehicle it would serve | priority requires knowing where the vehicle is and which phase clears it |
| pedestrians (COOP-FULL) | waiting pedestrians per crossing | pedestrian delay is a stated need |
| buses (COOP-FULL) | occupancy-weighted buses per side | person-based priority |
| forecast (Tier 3) | predicted inflow per side for the next 5 min | test whether prediction helps |

Only aggregate counts are used, never vehicle identities (privacy, deployability).

## Decision - cooperation

Cooperation is explicit communication between neighbours: every 5 s each intersection
sends each downstream neighbour a 3-value message (queue toward it, releasing toward it,
own pressure). IND agents receive nothing; COOP agents receive the messages. This makes
cooperation measurable (IND vs COOP ablation) and testable under failure (messages lost
with probability 0.1-0.5, stale or zeroed). Messages go only to direct neighbours, so the
cost does not grow with the size of the network.

Alternatives not kept: a centralised critic (MADDPG, MAPPO with global state) would
make training depend on the network size and remove the zero-shot transfer; attention
over neighbours (CoLight) is more expressive but heavier to train on a CPU in our time.

## Consequences

- Observation sizes: grid (IND/COOP/FULL) 32 / 44 / 62 values; district 47 / 59 / 78.
- Evidence: RQ1 (IND vs COOP), permutation importance of the blocks (figure 12),
  robustness to message loss (figure 8).
