# 3. Ideate - possible solutions

## Families of approaches

| Approach | Examples | Adaptivity | Cooperation | Data needed | Compute | Explainability | Safety guarantees | Maturity |
|---|---|---|---|---|---|---|---|---|
| Fixed-time plans | Webster, TRANSYT | none within a plan | offsets only | historical counts | none | high | by design | deployed everywhere |
| Actuated control | gap-based, SCOOT-like | local | none | loop detectors | none | high | by design | widely deployed |
| Self-organising rules | SOTL | local | implicit | detectors | none | high | needs rules | research / pilots |
| Pressure-based optimisation | Max-Pressure (Varaiya 2013) | local, provably stabilising | implicit through downstream queues | queues in and out | tiny | high | needs a shield | research / pilots |
| Model-predictive control | MPC on a traffic model | network-wide | explicit | accurate model and forecasts | high, online | medium | constraints in the optimiser | niche |
| Single-agent (centralised) RL | one policy for the district | network-wide | full | full state | explodes with network size | low | needs a shield | research |
| Independent multi-agent RL | IntelliLight, PressLight | local | none | local detectors | moderate training, tiny inference | low-medium | needs a shield | research |
| Cooperative multi-agent RL | MA2C, CoLight | network-wide through messages | explicit | local + neighbours | moderate training, tiny inference | low-medium | needs a shield | research |

## Beyond traffic lights (brief extensions)

| Idea | What it changes | Kept? |
|---|---|---|
| Emergency-vehicle priority | EV position in the observation, EV waiting in the reward; rule-based preemption as baseline | yes (Tier 1) |
| Pollution-aware control | CO2 penalty in the reward; travel time vs CO2 Pareto front | yes (Tier 1) |
| Incident handling | evaluation scenario with a blocked lane | yes (Tier 1) |
| Public transport | person-weighted delay (bus = 30 persons) | yes (Tier 2) |
| Pedestrians | waiting pedestrians in the observation and reward | yes (Tier 2) |
| Communication failures | lost neighbour messages at evaluation | yes (Tier 2) |
| Sensor faults | noise and dead detectors at evaluation | yes (Tier 2) |
| Large networks | zero-shot transfer from 16 to 64 intersections | yes (Tier 2) |
| Demand prediction | short-term inflow forecast, alone and as an extra observation | yes (Tier 2-3) |
| Rerouting / route guidance | changes drivers' routes | no - different actor, out of scope for signal control |
| Variable speed limits | changes the road, not the signals | no - out of scope |

## Selection

We keep cooperative multi-agent RL with parameter sharing (CoTraffic) because:

- it adapts to demand and events without a traffic model, unlike fixed plans and MPC;
- parameter sharing gives one small policy for all intersections, so training stays
  affordable on a laptop and the policy can be applied to a larger network unchanged;
- neighbour messages make cooperation explicit and measurable (IND vs COOP ablation);
- the shield gives the safety guarantees that learning alone cannot give.

We keep Max-Pressure as the strongest classical baseline: if learning does not beat it,
we say so (fallback rule of the project plan).

## TEAM - ideas from the brainstorming session

Record here the ideas the team produced (including rejected ones) and the reason for
each decision.
