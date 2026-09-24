# ADR-005: Evaluation protocol and metrics

- Status: accepted
- Date: 2026-09-24

## Context

Results must be comparable between methods, reproducible, and robust to the ways a
simulation can flatter a controller (teleports, vehicles that never enter, noise of a
single seed).

## Decision

**Episode.** 15 min warm-up (simulated, not measured) + 60 min measured + 15 min
cool-down without new demand, so that most vehicles of the measured hour finish their
trip. Controllers run during all three periods. Values in `configs/protocol.yaml`.

**Population.** Vehicles whose intended departure lies in the measured window. Travel
time counts from the intended departure, so waiting to enter the network counts.

**Failures are penalised, never hidden.**

| Case | Treatment |
|---|---|
| vehicle still driving at the end | travel time censored at the end of the simulation, counted as unfinished |
| vehicle never inserted | same, counted as never inserted |
| teleport (SUMO removes a vehicle stuck for 300 s and puts it further) | +300 s added to its travel time, teleports reported |

**Metrics** (definitions in `src/cotraffic/evaluation/metrics.py`, tested on hand-written
SUMO outputs in `tests/test_metrics.py`): efficiency, sustainability, safety, equity,
people, priority and engineering groups, as listed in the project plan.

**Demand.** Levels are fractions (0.45 / 0.7 / 1.0) of a peak rate calibrated per network
so that fixed-time control is clearly congested without gridlock (journal, M1). Each
traffic component uses its own random stream: two scenarios with the same seed share the
same car demand, so differences between scenarios are paired.

**Seeds.** Disjoint ranges: evaluation 0-999 (5 per cell: 0-4), validation 1000-1999
(checkpoint selection), Webster tuning and demand calibration 5000-5999, training from
100000. No method is ever tuned on an evaluation seed.

**Statistics.** Mean and bootstrap 95% CI over the 5 seeds; each learning method against
the best baseline of the cell with a Mann-Whitney U test, Holm correction over the
family of comparisons, and Cliff's delta as effect size; relative improvement against FT
and MP.

**Traceability.** Every result row stores method, variant, network, scenario, demand,
seed, checkpoint and git commit (with `-dirty` when uncommitted changes were present).

## Consequences

- An evaluation episode is 90 simulated minutes. Measured during calibration (without
  the SSM device): 15-60 s on grid4x4 depending on demand, 2.5-4 min on grid8x8. Every
  result row stores its wall time (`sim_wall_time_s`).
- Five seeds give limited statistical power: with 5 runs against 5 the smallest two-sided
  Mann-Whitney p-value is 0.008, so after Holm correction over more than 6 tests no
  baseline-vs-baseline difference can be declared significant, however large (journal, M2).
  The confirmatory family is therefore learned variants (3 training seeds x 5 evaluation
  seeds = 15 runs) against the best baseline of each cell (5 runs), where the smallest
  p-value is about 1.3e-4. For every comparison we report the effect size (Cliff's delta)
  and the confidence intervals, and we do not claim a difference the test does not support.
