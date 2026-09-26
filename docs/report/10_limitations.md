# 10. Limitations

The negative results below are part of the findings; each one is traced in
`docs/FAILURES.md` or the experiment journal.

**Where the learned agents lose.**

- They never beat the best classical controller of a cell. The gap is small (IND within
  4%, COOP within 7%) but systematic: paired on the same traffic, it excludes zero in most
  grid cells (section 8.1).
- Cooperation through neighbour messages brought no gain (section 9.1, F-009).
- For emergency vehicles, a preemption rule on top of Max-Pressure beats COOP-FULL on
  both the emergency-vehicle delay (38 s vs 74 s) and the travel time of the other
  traffic (section 8.2).
- Max-Pressure, not the learned policy, is the best single controller across demand
  levels (best in 4 of 6 cells, within 2.4% in all).
- The pedestrian rule on Max-Pressure (PED-RULE-MP) was evaluated with a single
  threshold (30 s, fixed in advance): it caps the longest pedestrian waits at no vehicle
  cost, COOP-FULL has the lower mean wait at +2.6% of vehicle travel time. Whether a
  shorter threshold would dominate COOP-FULL is not established (section 8.7).
- They handle an accident worse than Max-Pressure (+3 to +12% for the affected vehicles),
  having never seen one in training (section 8.4).
- Surrogate safety measures favour Max-Pressure and actuated control: the learned agents
  switch more often and produce 6-16% more conflicts with a time-to-collision below 1.5 s
  than Max-Pressure, depending on the demand, and more stops per vehicle (section 8.1).
  The signal sequence itself is safe by construction (shield), but the driving pattern it
  induces is more stop-and-go.
- On the district at peak they have longer waiting-time tails than Max-Pressure and
  occasional congested episodes on particular seeds.

**Design limitations found by the experiments.**

- The shield's anti-starvation and maximum-green rules act on detected demand only; a
  movement whose detectors have all failed can be starved (F-012). Field controllers put
  failed detectors on recall; our shield does not. This penalises Max-Pressure, which
  relies on the counts alone, in the sensor-fault scenario, so the robustness advantage
  of the learned agents there is probably overstated (section 8.4).
- Pedestrians cannot be simulated on the district: the OpenStreetMap import has sidewalks on
  4 of 112 edges (F-011).
- Collisions occur on the district with every controller (0.2-1.0 per 90-minute run,
  fixed-time included) and almost never on the grid (6 in all grid runs). We have not
  diagnosed them; because they appear with every controller on the imported network
  only, we suspect its junction geometry, but this is not verified.

**Scope of the evidence.**

- Simulation only (SUMO), with synthetic demand calibrated against fixed-time control; no
  real counts were available, so no GEH validation was possible. The district is a
  placeholder in central Tunis (7 signals) chosen for its OpenStreetMap data (ADR-006).
- CO2 comes from SUMO's HBEFA4 classes for cars, buses and emergency vehicles. With these
  classes emissions follow the time spent in the network, so the travel-time vs CO2
  trade-off of RQ3 could not appear; heavier vehicles or gradients might change that.
- Emergency-vehicle results on the district are inconclusive: 3-5 vehicles per run whose
  routes cross 1-2 of the 7 signals.
- The sensitivity to the emergency-vehicle weight rests on one training run per weight;
  the forecast-augmented agent (Tier 3) was evaluated on the grid only.

**Statistics.**

- 5 test seeds per cell and 3 training runs per learned variant. The Mann-Whitney test
  treats the 15 runs of a learned variant as independent, so its p-values are optimistic;
  conclusions with Cliff's delta = +-1 (complete separation) are unaffected, and for the
  others we rely on two-way bootstrap intervals and paired differences (ADR-005). With
  Holm's correction over the whole family, only near-complete separations (|delta| of 0.89
  or more) are significant.
- Three training runs cannot tell a weak run from a fragile method (COOP t2 is the slowest
  run in several cells).
- Three district runs were interrupted and resumed from a checkpoint; each trained on one
  PPO rollout less than the others (0.4% of the budget; journal, 2026-09-26).
