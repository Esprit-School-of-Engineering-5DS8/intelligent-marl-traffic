# ADR-004: Baselines

- Status: accepted
- Date: 2026-09-24

## Context

The brief asks for a comparison with "an appropriate baseline or existing approach". A
learning method compared only with a badly tuned fixed-time plan proves nothing. We
need baselines that a traffic engineer would recognise and that are as good as we can
reasonably make them.

## Decision

Four baselines, all using exactly the phases the agents choose from (one green per group
of compatible vehicle movements, crossings red during the 3 s yellow), so they differ
from the agents only in *when* they switch.

| Id | Controller | Implementation |
|---|---|---|
| FT | Fixed-time, Webster (1958) cycle and splits, recomputed for every demand level | `controllers/programs.py::webster_program` |
| ACT | SUMO gap-based actuated control, min green 10 s, max green 60 s, max gap 3 s | `controllers/programs.py::actuated_program` |
| MP | Max-Pressure (Varaiya 2013): request the phase maximising the sum of (upstream - downstream) vehicles over its movements; ties keep the phase; same safety shield as the agents | `controllers/classical.py::MaxPressure` |
| EV-RULE | ACT + rule-based preemption: when an emergency vehicle is within 200 m of its next signal, hold or claim its green, respecting min green and yellow | `controllers/ev_preemption.py` |
| EV-RULE-MP | the same preemption on top of Max-Pressure, requested at each 5-s decision through the shield (added 2026-09-26, FAILURES F-013) | `controllers/ev_preemption.py` |
| PED-RULE-MP | Max-Pressure; a crossing whose longest-waiting pedestrian has waited more than 30 s (the Highway Capacity Manual's impatience threshold, fixed before any run) requests its green at the next decision, through the shield (added 2026-09-26, the pedestrian-aware reference for COOP-FULL) | `controllers/pedestrian_rule.py` |

Choices that make the baselines fair:

- **Webster is tuned on demand it will face.** Flows come from a realisation reserved for
  tuning (seed 5000), at the same demand level as the evaluation, never from the
  evaluation seeds. FT thus knows the average demand of the hour in advance, an
  advantage a real plan does not always have.
- **We checked that Webster's plan is not a strawman.** Lower assumed saturation flows
  give longer cycles; on grid4x4 at peak those plans are much worse (mean wait 111-178 s
  vs 75-81 s, journal M1, `results/calibration/grid4x4_webster_saturation_check.csv`).
- **We compute Webster ourselves** because SUMO's `tlsCycleAdaptation.py` splits the cycle
  between each green and its pedestrian-clearance variant (FAILURES F-004).
- **Max-Pressure goes through the shield**, so its advantage or disadvantage against the
  agents cannot come from different safety rules.
- Offsets are 0 (no green wave). Coordinated fixed-time plans would be a stronger
  baseline on arterials; this is noted as a limitation.

## Consequences

- MP is expected to be the strongest classical baseline at high demand, ACT at low
  demand; the demand calibration already shows this (journal, M1). Statistical tests of
  the agents are made against the best baseline of each condition, not against FT only.
