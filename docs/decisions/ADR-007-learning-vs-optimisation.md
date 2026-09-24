# ADR-007: Reinforcement learning rather than online optimisation

- Status: accepted
- Date: 2026-09-24

## Context

Adaptive signal control can be built by optimising a traffic model online (model
predictive control, rolling-horizon optimisation), with hand-written rules (actuated,
SOTL, Max-Pressure), or by learning a policy from simulated experience.

## Options considered

| Option | For | Against |
|---|---|---|
| Rule-based (actuated, Max-Pressure) | simple, explainable, proven | fixed logic: cannot weigh CO2, pedestrians, emergency vehicles or neighbours' state unless a new rule is written for each |
| Online optimisation (MPC) | explicit objective and constraints | needs a calibrated traffic model and short-term forecasts, and solving an optimisation every few seconds per intersection; model errors dominate on real streets |
| Reinforcement learning | learns from the simulator what the objective rewards; one policy handles many signals (parameter sharing); inference is a tiny forward pass | needs a simulator and training time; no guarantees by itself; less explainable |

## Decision

Multi-agent reinforcement learning (ADR-008) for the agents, with:

- the safety shield (ADR-003) providing the guarantees that learning does not give;
- Max-Pressure as the strongest rule-based baseline, so we can see whether learning
  brings anything over a simple provably-stabilising rule;
- explainability work (decision logs, permutation importance) to reduce the black-box
  concern.

## Consequences

- The project's value depends on an honest comparison. If the agents do not beat
  Max-Pressure, the fallback of the project plan applies: we deliver Max-Pressure with the
  rule-based emergency priority and the eco-aware extensions, and document the learning
  attempts in FAILURES.md.
