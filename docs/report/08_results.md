# 8. Results

All numbers come from the core experiment matrix (`configs/experiments/core.yaml`, 790 runs,
none failed). Each cell is evaluated on test seeds 0-4; a learned variant contributes its 3
training runs x 5 test seeds = 15 runs, a baseline 5 runs. Means are given with a 95%
bootstrap confidence interval that resamples training runs and test seeds (two-way
bootstrap, ADR-005). Differences are written method minus reference: a positive
difference means slower, or more CO2. "Paired" differences compare a method and the
reference on the same test seed, which removes the variation of the traffic itself. Holm
p-values come from Mann-Whitney U tests over the family "learned variant vs best baseline
of the cell"; that test treats the 15 runs of a learned variant as independent, so its
p-values are optimistic, and we rely on the intervals as much as on p. Full tables:
`results/summary/REPORT_TABLES.md`.

**In short.**

- On these networks, Max-Pressure plus simple rules remains the best controller.
  Max-Pressure is the best baseline in 4 of the 6 main cells and within 2.4% of the best
  in all of them; the learned agents are 0.2-4.0% (IND) and 0.4-6.9% (COOP) slower than
  the best baseline of each cell and never faster, so a learned policy is not a better
  generalist than Max-Pressure. For emergency vehicles, a preemption rule on top of
  Max-Pressure cuts their delay by 64% for +0.4% of travel time and beats the learned
  COOP-FULL (74 s vs 38 s; FAILURES F-013).
- The learned agents clearly beat fixed-time control (10-20% shorter travel times, 3% at
  medium demand on the district) and actuated control where it breaks down (-21% at grid
  peak, -5% on the rush profile); actuated control remains 2-4% better at low and medium
  demand on the grid.
- They are more robust to sensor faults than Max-Pressure (IND +1.4% against +21.5%;
  +7.8% without one collapsed episode), partly because our shield cannot see a movement
  whose detectors failed, so this advantage is probably overstated. They transfer
  unchanged from 16 to 64 junctions, 4% from Max-Pressure and 14% faster than fixed-time
  control.
- With pedestrian and emergency-vehicle terms, COOP-FULL lowers the mean pedestrian wait
  by 24% compared with a pedestrian rule on Max-Pressure, at +2.6% of vehicle travel
  time, while the rule caps the longest waits as well at no vehicle cost: two points of
  the same trade-off, neither dominated. For emergency vehicles the rule on Max-Pressure
  does better (F-013). CO2 follows travel time (correlation 0.93-0.99): there is no
  trade-off to trace.
- Neither communication between neighbours (F-009), a different reward (F-007) nor a
  forecast of arrivals (RQ6) closed the gap; the learned agents also handle an accident
  worse than Max-Pressure.
- Our contribution is therefore a fair, reproducible benchmark - the same shield, seeds,
  statistics and base controllers for every method, each mechanism compared with the same
  mechanism on the strongest base - and the diagnosis of why learning does not beat
  Max-Pressure here (F-007, F-009, F-013).

## 8.1 RQ1 - Do cooperative agents outperform independent agents and classical controllers?

Mean travel time (s), normal scenario (Figure 2):

| Cell | FT | ACT | MP | IND | COOP | COOP-FULL |
|---|---|---|---|---|---|---|
| grid4x4, low | 171.4 | **145.0** | 148.5 | 150.8 | 150.8 | 151.9 |
| grid4x4, medium | 179.8 | **157.3** | 157.9 | 161.1 | 161.0 | 161.1 |
| grid4x4, peak | 261.2 | 275.3 | **210.2** | 217.5 | 224.6 | 219.7 |
| grid4x4, rush profile | 209.2 | 195.0 | **179.9** | 184.5 | 186.7 | 184.5 |
| district, medium | 112.7 | 109.9 | **109.4** | 109.7 | 109.9 | 109.9 |
| district, peak | 196.8 | 158.3 | **153.4** | 158.4 | 159.5 | 156.5 |

Learned variants against the best baseline of each cell:

| Cell | Best baseline [CI] | IND [CI] | IND, paired difference | COOP [CI] | COOP, paired difference | Holm p (IND / COOP) |
|---|---|---|---|---|---|---|
| grid4x4, low | ACT 145.0 [144.6, 145.5] | 150.8 [150.0, 151.7] | +4.0% [+3.4, +4.6] | 150.8 [150.1, 151.5] | +4.0% [+3.6, +4.3] | 0.005 / 0.005 |
| grid4x4, medium | ACT 157.3 [156.7, 158.1] | 161.1 [160.3, 162.2] | +2.4% [+2.1, +2.8] | 161.0 [160.0, 161.9] | +2.3% [+2.0, +2.7] | 0.005 / 0.005 |
| grid4x4, peak | MP 210.2 [203.1, 217.2] | 217.5 [209.8, 225.6] | +3.5% [+2.0, +5.4] | 224.6 [213.3, 236.3] | +6.9% [+3.4, +11.1] | 1 / 0.88 |
| grid4x4, rush profile | MP 179.9 [176.1, 183.8] | 184.5 [180.9, 187.9] | +2.6% [+1.6, +3.5] | 186.7 [181.9, 191.9] | +3.8% [+2.6, +5.4] | 1 / 1 |
| district, medium | MP 109.4 [109.1, 109.8] | 109.7 [109.2, 110.3] | +0.2% [-0.2, +0.8] | 109.9 [109.4, 110.3] | +0.4% [+0.0, +0.8] | 1 / 1 |
| district, peak | MP 153.4 [143.2, 164.0] | 158.4 [145.9, 170.1] | +3.2% [-4.0, +9.8] | 159.5 [143.8, 176.1] | +3.9% [-4.7, +15.8] | 1 / 1 |

- **Max-Pressure is the best single controller.** It is the best baseline in 4 of the 6
  cells and within 2.4% of the best in all of them: actuated control is 2.4% and 0.4%
  faster at low and medium demand but breaks down at peak (31% slower than Max-Pressure).
  A single learned policy also covers every demand level and never breaks down on the
  grid, but at 0.2-4.0% (IND) from the best baseline of each cell it is not a better
  generalist than Max-Pressure.
- **The gap is small but systematic.** With Holm correction only the low and medium grid
  cells are significant (every learned run slower than every actuated run). Paired by
  test seed, the intervals also exclude zero at peak and on the rush profile: on the same
  traffic, the learned agents are 2.6-6.9% slower than Max-Pressure.
- **On the district the test seed dominates.** At peak the same policy ranges from 128 to
  197 s depending on the seed. COOP has congested episodes on seeds 2 and 3 (187-197 s,
  against 147-152 s for Max-Pressure); pairing cannot remove this interaction, and the
  peak comparison stays inconclusive.
- **Cooperation.** COOP is never better than IND by more than 0.1% (section 9).
- **Against fixed-time control** the learned variants gain 10.4-16.7% on the grid, 19.0-20.5%
  at district peak and 2.5-2.7% at district medium.

Queues and equity (Figure 10). At grid peak the 95th-percentile wait is 137 s for MP,
143 s for IND and 153 s for COOP, against 331 s for ACT and 263 s for FT; the Gini
coefficient of waiting times is 0.4 for all methods. On the district at peak the learned
agents have longer tails than MP (P95 219-265 s vs 147 s, with wide intervals).

Safety. The signal sequence is safe by construction (shield, ADR-003). Surrogate measures
favour the classical controllers: at grid medium demand the learned agents produce
2 038-2 054 conflicts with a time-to-collision below 1.5 s per 1 000 vehicles against
1 768 for MP and 1 857 for ACT (FT: 2 365), and 3.4-3.5 stops per vehicle against 3.0.
They switch phases more often (4 700-5 500 switches per episode against 4 300-4 400 for
MP). Hard-braking events stay at 0-2.2 per episode for every controller. Collisions occur
almost only on the district, with every controller (0.2-1.0 per 90-minute run, fixed-time
included), and 6 times in all grid runs; we have not diagnosed them (section 10).

Cost. One decision of the shared policy takes 0.1-0.5 ms on the laptop CPU; training
takes 16-47 min per run of 500 000 agent steps, with up to three runs sharing the laptop
(`REPORT_TABLES.md`, training runs).

## 8.2 RQ2 - Can emergency vehicles be prioritised without degrading overall traffic?

A preemption mechanism has to be judged against its own base controller: EV-RULE runs on
actuated control, which breaks down at peak on its own. We therefore also evaluate
EV-RULE-MP, the same 200 m preemption rule on top of Max-Pressure (requests at the 5-s
decision interval, through the same shield as the learned agents).

Grid4x4 at peak with emergency vehicles (Figure 5). Paired differences are against the
controller the mechanism is built on:

| Method | Built on | EV delay (s) [CI] | Travel time, all vehicles (s) | EV delay vs base | Travel time vs base |
|---|---|---|---|---|---|
| FT | | 154.7 | 261.6 | | |
| ACT | | 149.8 | 278.0 | | |
| MP | | 106.3 | **211.6** | | |
| COOP | | 115.9 | 225.3 | | |
| EV-RULE | ACT | 58.2 [44.9, 69.8] | 288.1 | -61.1% [-68.8, -50.2] | +3.6% [+1.4, +5.8] |
| EV-RULE-MP | MP | **38.1** [34.7, 41.2] | 212.4 | -64.2% [-69.7, -55.3] | +0.4% [-0.5, +1.0] |
| COOP-FULL | COOP | 73.5 [58.8, 96.5] | 219.2 | -36.6% [-49.4, -16.6] | -2.7% [-3.7, -1.4] |

- Rule-based preemption cuts the emergency-vehicle delay by 61-64% compared with its base
  controller, for +3.6% of travel time on actuated control and +0.4% (not significant)
  on Max-Pressure. The 36% gap between EV-RULE and Max-Pressure is the breakdown of
  actuated control at peak, not the cost of preemption (FAILURES F-013).
- COOP-FULL learns part of this behaviour: -37% EV delay compared with COOP, with no cost
  to the other traffic. COOP-FULL differs from COOP in more than the emergency-vehicle
  block (all observation blocks, person-weighted reward), so COOP is only an approximate
  base.
- Head-to-head, the rule on Max-Pressure is better on both criteria: EV delay 38.1 s
  against 73.5 s (COOP-FULL +93%, paired [+58, +138], every COOP-FULL run slower) and
  travel time 212.4 s against 219.2 s (COOP-FULL +3.2%, paired [+1.6, +5.0]).
- **Answer to RQ2:** yes - emergency vehicles can be prioritised almost without degrading
  the other traffic, and the most effective way we found is a simple preemption rule on
  the best base controller. The learned policy achieves part of it.
- The learned mechanism is the observation block and the reward term, not an override
  (Figure 12): an emergency vehicle is in detection range for 0.7% of COOP-FULL's
  decisions, but shuffling that block changes 40% of those decisions and raises the EV
  delay from 64 to 112 s (+75%), back to COOP's level, while travel time moves by 0.7%.
- On the district the question stays open: 3-5 emergency vehicles per run, whose routes
  cross 1-2 of the 7 signals (EV-RULE-MP preempts 7 times per run, against 24 on the
  grid), give intervals of +-60 to +-120 s. The mean EV delays are COOP-FULL 85.2, COOP
  94.5, ACT 95.1, EV-RULE 99.1, EV-RULE-MP 112.6, MP 119.4 and FT 133.6 s, with no
  significant difference; preemption costs +1.3% (EV-RULE vs ACT) and +1.4% (EV-RULE-MP
  vs MP) of travel time, both not significant.

## 8.3 RQ3 - What is the trade-off between travel time and CO2?

CO2 over the measured hour (kg), grid4x4 (Figure 4):

| Method | medium | vs MP, paired | peak | vs MP, paired |
|---|---|---|---|---|
| MP | **2 205** | reference | **3 959** | reference |
| IND | 2 273 | | 4 090 | |
| COOP | 2 270 | +3.0% [+2.6, +3.4] | 4 190 | +5.8% [+3.2, +9.1] |
| COOP-ECO, lambda = 0.5 | 2 257 | +2.4% [+2.1, +2.7] | 4 050 | +2.3% [+1.6, +3.2] |
| COOP-ECO, lambda = 1.0 | 2 255 | +2.3% [+1.9, +2.7] | 4 091 | +3.3% [+2.0, +4.6] |

- Across the 90 runs of each demand level, network CO2 and mean travel time are correlated
  at 0.93 (medium) and 0.99 (peak). The CO2 difference between controllers is the time
  vehicles spend stopped and idling, so every method that is faster also emits less: the
  Pareto front reduces to a point, and Max-Pressure is best on both axes.
- The CO2 penalty lowers COOP's CO2 and travel time together; it narrows COOP's gap to MP
  from 5.8% to 2.3% at peak, and brings COOP-ECO to about 1% of IND. It acts as one more
  congestion signal.
- A real trade-off would need emissions that depend on the speed profile more than on
  time (heavy goods vehicles, gradients), which our demand does not contain (section 10).

## 8.4 RQ4 - How robust is the system to accidents, sensor faults and communication failures?

**Accident** (a vehicle stopped 31 m before the stop line of a main approach, minutes
35-55, peak; Figure 6). Travel time of all vehicles and of the 384 vehicles per run whose
route crosses the blocked approach:

| Method | all vehicles (s) | affected vehicles (s) | affected vs MP, paired |
|---|---|---|---|
| FT | 261.3 | 332.7 | +24.6% [+20.8, +27.2] |
| ACT | 287.9 | 331.0 | +24.0% [+9.1, +34.5] |
| MP | **212.5** | **267.0** | reference |
| IND | 219.2 | 292.8 | +9.6% [+5.4, +14.3] |
| COOP | 227.3 | 299.1 | +12.0% [+1.6, +25.4] |
| COOP-FULL | 221.8 | 275.7 | +3.3% [-1.9, +9.7] |

Network-wide the accident costs about 1% of travel time to MP and the learned agents (5%
to ACT); locally, Max-Pressure serves the affected vehicles best. The learned agents never
saw an accident during training; COOP-FULL, trained with the most varied episodes, is
closest to MP.

**Sensor faults** (every count off by a Gaussian error of 2 vehicles, 20% of the lane
detectors reporting 0 for the whole episode; Figure 8). Change of each controller's travel
time compared with its own runs without faults, paired:

| Method | without faults (s) | with faults (s) | change |
|---|---|---|---|
| MP | 210.2 | 255.4 | +21.5% [+5.2, +51.2] |
| IND | 217.5 | 220.4 | **+1.4% [-0.3, +2.6]** |
| COOP | 224.6 | 247.7 | +10.3% [+2.4, +25.4] |

Under faults IND is 13.7% faster than MP (paired [-30.6, -0.4]). Max-Pressure chooses
phases from the counts alone. On one test seed it collapses (359 s, 18 teleports,
189 unfinished vehicles, a maximum wait of 1 762 s); on the other four it loses 4-15%
(7.8% on average), against 0.7-1.9% for IND on every seed. Part of this loss, and most
likely the collapse, comes from our shield rather than from Max-Pressure itself: its
anti-starvation and maximum-green rules only see detected demand, so a movement whose
detectors all read 0 can wait indefinitely (FAILURES F-012). Field controllers place failed
detectors on recall and serve their movement every cycle; with such a fallback
Max-Pressure would lose less, and the robustness advantage of the learned agents is
probably overstated here. IND keeps a steady switching rhythm and does not depend on any
single count. COOP's loss comes from one training run (t2: +23%; t1, t3: +2-3%).

**Communication failures.** Losing 10%, 30% or 50% of the neighbour messages (the receiver
keeps the last message received) changes COOP's travel time by +0.5% each time (paired on
training run and test seed: [-0.9, +2.0], [-0.6, +1.7], [-0.9, +1.9]). The system is
robust to message loss because COOP makes little use of the messages (section 8.9).

## 8.5 RQ5 - Does the approach scale without retraining?

Policies trained on grid4x4 (16 signals) run unchanged on grid8x8 (64 signals), peak
(Figure 9):

| Method | Travel time (s) | vs MP, paired | vs FT, paired |
|---|---|---|---|
| FT | 365.5 [364.9, 366.5] | | |
| MP | **300.7** [300.2, 301.2] | | |
| IND | 312.7 [311.8, 314.1] | +4.0% [+3.6, +4.5] | -14.5% |
| COOP | 313.1 [312.0, 314.6] | +4.1% [+3.7, +4.6] | -14.3% [-14.7, -13.9] |

The gap to Max-Pressure does not grow with the network (IND: 3.5% on grid4x4 at peak, 4.0%
on grid8x8). Parameter sharing and fixed-size, padded observations make the transfer
possible: every junction runs the same policy on the same observation layout.

## 8.6 RQ6 (Tier 3) - Does short-term forecasting help?

Forecast accuracy (next-5-minute arrivals per approach) is reported in
`REPORT_TABLES.md`: learned models improve on persistence by about 10% and come within 25%
of the Poisson noise floor, while a 10-minute moving average does almost as well
(journal, 2026-09-24). `coop_forecast` adds the Ridge prediction per approach to COOP's
observation (3 training runs). Mean travel time, grid4x4, normal traffic; differences
paired by test seed, with training runs of both variants resampled:

| Demand | COOP + forecast (s) | vs COOP | vs IND | vs MP |
|---|---|---|---|---|
| medium | 160.8 | -0.1% [-0.5, +0.3] | -0.2% [-0.6, +0.2] | +1.8% [+1.6, +2.0] |
| peak | 218.0 | -2.9% [-6.5, +0.2] | +0.3% [-1.4, +1.8] | +3.7% [+2.6, +5.0] |
| rush profile | 183.7 | -1.6% [-3.1, -0.4] | -0.4% [-1.4, +0.4] | +2.1% [+1.4, +2.8] |

The forecast brings no measurable gain: the agent is indistinguishable from IND at every
level and remains slower than Max-Pressure. Its small advantage over COOP at peak and on
the rush profile matches COOP's weak training run (t2), not a forecasting effect: its
three runs are as close to each other (217-219 s at peak) as IND's. With arrivals close
to Poisson, a 5-minute forecast carries little information the current queues do not
already give. **Answer to RQ6:** no, not on these networks.

## 8.7 People: pedestrians and buses (grid4x4, medium; Figure 11)

| Method | Mean pedestrian wait (s) | Longest pedestrian wait (s) | Vehicle travel time (s) | Bus delay (s) | Person-weighted delay, bus scenario (s) |
|---|---|---|---|---|---|
| FT | 14.1 | **85.2** | 186.9 | 84.4 | 77.1 |
| ACT | 15.8 | 159.2 | 174.2 | **46.4** | **52.3** |
| MP | 17.7 | 176.8 | **164.7** | 49.0 | 52.7 |
| PED-RULE-MP | 16.4 | 109.0 | 164.8 | - | - |
| COOP | 15.4 | 164.1 | 168.0 | 51.9 | 56.0 |
| COOP-FULL | **12.5** | 114.9 | 169.1 | 49.8 | 55.8 |

The classical baselines choose phases from vehicle counts only (fixed-time serves every
crossing once per cycle; for Max-Pressure, as for the learned agents, the shield serves a
crossing that has stayed red for 90 s while pedestrians wait). As for emergency vehicles
(section 8.2), we therefore compare COOP-FULL with a rule on Max-Pressure: PED-RULE-MP
serves a crossing once a pedestrian has waited 30 s, the delay above which the Highway
Capacity Manual expects pedestrians to become impatient (threshold fixed before any run).

- PED-RULE-MP shortens the longest waits by 38% compared with MP (paired [-50.4, -22.4])
  and the mean wait by 7% ([-12.4, -1.4]), at no cost to vehicles (+0.1% [-0.7, +0.9]).
- COOP-FULL, which observes waiting pedestrians and includes their wait in its reward,
  keeps a lower mean pedestrian wait: -29% compared with MP ([-32.1, -26.4]) and -24%
  compared with PED-RULE-MP ([-28.1, -18.2]), with longest waits similar to the rule's
  (115 s vs 109 s). It costs 2.6% of vehicle travel time compared with PED-RULE-MP
  ([+1.3, +5.1]) and 7.2% of person-weighted vehicle delay ([+3.6, +14.0]).
- The two sit at different points of the pedestrian-vehicle trade-off; neither dominates.
  With a single threshold, fixed in advance, we cannot say whether a rule with a shorter
  threshold would match COOP-FULL's mean wait at a smaller vehicle cost.
- The person-weighted reward (30 persons per bus) lowers COOP-FULL's bus delay by 4%
  compared with COOP (paired [-9.4, +1.5], not significant), but not below the classical
  controllers.

## 8.8 Adaptivity: rush-hour profile (Figure 7)

With demand rising to the peak and falling back within the hour, the learned policies
(trained on a random level per episode) keep up: IND 184.5 s and COOP-FULL 184.5 s against
MP 179.9 s (+2.6% paired), ACT 195.0 s and FT 209.2 s. Their 95th-percentile wait is 99 s,
against 98 s for MP and 143-150 s for FT and ACT.

## 8.9 Explainability (Figure 12)

Each observation block is shuffled between decisions (test seeds 0-4); we count how
often the chosen phase changes, among the decisions where the block is non-zero, and
replay episodes with the block shuffled. The replays use one training run of each
variant (t1, the checkpoint `seed1.zip`): its baseline values differ from the means over
three training runs in sections 8.1-8.2 (COOP-FULL t1: EV delay 64 s, against 73.5 s for
the three runs; COOP t1: 221 s at peak, against 224.6 s).

| Block | COOP: decisions changed | COOP: travel time | COOP-FULL: decisions changed | COOP-FULL: travel time | COOP-FULL: EV delay |
|---|---|---|---|---|---|
| local lanes | 40% | +53.2% | 24% | +9.8% | +11% |
| phase and timers | 14% | +0.3% | 34% | +11.3% | +14% |
| neighbour messages | 7% | -1.4% | 8% | +0.7% | +4% |
| emergency vehicles | - | - | 40% (block non-zero in 0.7% of decisions) | +0.7% | +75% |

- COOP decides from its own lanes; the neighbour messages change a few decisions and
  nothing in travel time, which explains both the absence of a cooperation gain and the
  robustness to message loss.
- COOP-FULL relies more on the phase timers and uses the emergency-vehicle block exactly
  where it matters. Pedestrian and bus blocks are absent from the emergency scenario and
  are not scored.
- Per-decision explanations ("keeps north-south green: 12 halting on north-south, 4 on
  east-west; emergency vehicle 180 m from the south") are in
  `results/logs/decisions/explained__*.csv` and in the dashboard.
