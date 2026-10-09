# Experiment journal

Dated log of runs, measurements and observations. Numbers are copied from the files
or console output of the runs they describe.

## 2026-09-24 - M0: environment and toolchain

**Machine:** team laptop, Intel i5-1135G7 (4 cores / 8 threads), 11.7 GB RAM, Windows 10,
Python 3.12.6, CPU only.

**Stack:** SUMO 1.27.1 (`eclipse-sumo` wheel, libsumo), PettingZoo 1.27.0,
SuperSuit 3.11.0, Stable-Baselines3 2.9.0, Gymnasium 1.3.0, PyTorch 2.14.0 (CPU).

**Checks**

- `netgenerate` grid junctions with sidewalks: each 4-arm junction has 20 signals
  (16 vehicle links + 4 crossings); default program = 2 vehicle greens, each with a
  pedestrian-clearance variant, plus 2 yellows. After merging (F-001) an agent has 2
  actions.
- SUMO 1.27 assigns HBEFA4 emission classes per vehicle class by default (car
  `PC_petrol_Euro-4`, bus `UBus_Std_gt15-18t_Euro-VI_A-C`, emergency `LCV_diesel_N1-III_Euro-6ab`).
- `vehicle.getNextTLS` returns the next signal, the link index the vehicle will use and
  the distance - used for emergency-vehicle features and the preemption baseline.
- A controlled link of a pedestrian crossing is reported as walking area -> crossing.

**Random-policy episodes** (shield active, all observation blocks, `python -m cotraffic episode`):

| Network | Demand | Simulated | Decisions | Switches | Min-green overrides | Mean halting vehicles | Teleports | Wall time |
|---|---|---|---|---|---|---|---|---|
| grid2x2 | medium + EV, peds, buses | 600 s | 480 | 121 | 120 | - | 0 | 0.4 s |
| grid4x4 | medium | 3600 s | 11 520 | 2 863 | 2 907 | 12.0 | 0 | 5.9 s |
| grid4x4 | peak | 3600 s | 11 520 | 2 863 | 2 907 | 17.5 | 0 | 6.9 s |

Observations:

- A full simulated hour on grid4x4 costs about 6-7 s: roughly 1 700 agent decisions per
  second of wall time. Training budgets far above 300k agent steps are affordable.
- With the first guess for the peak rate (2 600 veh/h) even a random policy keeps the
  network far from saturation (17.5 halting vehicles on average over 16 junctions). The
  peak rate must be recalibrated against the fixed-time baseline in M1.

## 2026-09-24 - M1: networks, demand calibration, scenarios

**Networks**

| Network | Signals | Notes |
|---|---|---|
| grid4x4 | 16 | 250 m links, 2 lanes per approach, sidewalks and crossings; 2 phases per junction |
| grid8x8 | 64 | same junction layout (evaluation only) |
| real_district | 7 | central Tunis (placeholder, see ADR-006): arterial network of 112 edges, 2-3 phases, up to 6 lanes on one side |

**Demand calibration** (`python -m cotraffic calibrate-demand`, tuning seeds 5001-5003, full
protocol 15 + 60 + 15 min; raw rows in `results/calibration/`). The `vehicles` column of the
sweep files is the number of vehicles of the measured hour, i.e. the hourly demand.

grid4x4, fixed-time (Webster) vs Max-Pressure, seed 5001:

| veh/h | FT wait (s) | FT p95 wait (s) | FT queue | ACT wait | MP wait | teleports (FT) |
|---|---|---|---|---|---|---|
| 3 900 | 37.7 | 69 | 40 | 16.0 | 20.4 | 0 |
| 6 500 | 43.3 | 83 | 78 | 25.6 | 26.3 | 0 |
| 7 800 | 55.2 | 114 | 121 | 45.9 | 36.1 | 0 |
| 8 840 (seeds 5002/5003) | 82.5 / 86.4 | 214 / 253 | 201 / 202 | - | 53.7 / 50.7 | 0 / 1 |
| 9 100 | 111.5 | 330 | 269 | 140.0 | 68.7 | 3 |

Chosen peak rates (demand levels low / medium / peak = 0.45 / 0.7 / 1.0 of it):

- grid4x4: **8 800 veh/h** - clear congestion under FT (mean wait > 80 s, p95 > 200 s, queue ~200
  vehicles) while every vehicle still finishes and teleports stay at 0-1. At 9 100 veh/h
  teleports and insertion backlog appear.
- real_district: **5 200 veh/h** - FT mean wait 25-40 s, p95 114-202 s, small entry backlog;
  at 5 500 veh/h the entrances jam for every controller (backlog 37-60 vehicles), which is
  a capacity problem of unsignalised entry roads that no signal controller can fix.
- grid8x8: **14 000 veh/h** - Max-Pressure delay comparable to grid4x4 at peak (52 s); with
  twice the rate of grid4x4 (17 600) FT reaches 147 s and 31 vehicles never finish.

Observations:

- Actuated control is the best controller at low demand and collapses first when the
  network saturates (grid4x4 at 9 100 veh/h: 140 s vs 112 s for FT and 69 s for MP).
- Max-Pressure is the strongest classical controller at high demand on both networks.

**Is the fixed-time baseline fair?** Webster's critical flow ratios at grid4x4 peak are only
0.43-0.52 (saturation flow 1 800 veh/h/lane), so it chooses 40-42 s cycles, although the
network is congested (shared lanes with permissive left turns have less capacity than
Webster assumes). We re-ran FT with lower assumed saturation flows, which lengthen the
cycle (`results/calibration/grid4x4_webster_saturation_check.csv`):

| assumed saturation flow | cycle (s) | FT mean wait, seeds 5001 / 5002 (s) |
|---|---|---|
| 1 800 (used) | 40-42 | 80.7 / 74.9 |
| 1 200 | 55-94 | 137.4 / 110.6 |
| 900 or less | 120 | 178.1 / 174.2 |

Longer cycles are clearly worse on 250 m links (queues spill back into the upstream
junction), so the Webster plan we use is the best of these fixed-time plans, not a strawman.

**Scenarios end to end** (`make smoke`, quick mode, 300 + 600 + 300 s): normal, incident,
emergency, pedestrians, buses, sensor noise, communication dropout on grid4x4; incident +
emergency + buses + pedestrians together on the district; FT, ACT, MP and EV-RULE on the
emergency scenario. All runs produce complete result rows without NaN.

## 2026-09-24 - M2: baselines on grid4x4 (5 evaluation seeds)

Command: `python -m cotraffic evaluate --experiment baselines_grid4x4`. Tables:
`results/summary/REPORT_TABLES.md`. Mean travel time (s), mean [95% CI]:

| Method | low | medium | peak | rush profile |
|---|---|---|---|---|
| FT | 171 [171, 172] | 180 [179, 181] | 261 [247, 276] | 209 |
| ACT | 145 [145, 146] | 157 [157, 158] | 275 [257, 290] | 195 |
| MP | 148 [148, 149] | 158 [157, 159] | 210 [203, 217] | 180 |

- Actuated control is best at low and medium demand and collapses at peak (worse than FT).
  Max-Pressure is the best baseline at peak and on the rush profile.
- Emergency scenario at peak: EV delay FT 155 s, ACT 150 s, MP 106 s, EV-RULE 58 s. EV-RULE
  cuts the EV delay by 61% against ACT at a cost of +3.6% travel time for the other vehicles
  (288 vs 278 s).
- SSM: 3 200 to 3 600 encounters with TTC < 1.5 s per 1 000 vehicles at peak, mostly vehicles
  closing on standing queues. We keep TTC only (DRAC was not reported and cost about 20% more
  simulation time in a quick test; conflict counts are identical).
- **Statistical power.** With 5 runs against 5, the smallest two-sided Mann-Whitney p-value is
  2/252 = 0.008. After Holm correction over the 11 baseline-vs-FT tests, even a complete
  separation (MP vs FT at peak, Cliff's delta = -1) gives p = 0.087. Learned variants are
  evaluated with 3 training seeds x 5 evaluation seeds = 15 runs against 5 (smallest p about
  1.3e-4), so their comparisons are the confirmatory family; baseline-vs-baseline differences
  are reported with effect sizes and confidence intervals.
- Engineering (wall time per evaluation episode, 2-5 processes sharing the laptop): peak with
  SSM 3-7 min, peak without SSM 1-2 min, low and medium 0.5-2 min.

## 2026-09-24 - M3: PPO training, IND

- Training speed (grid4x4, 16 agents, single torch thread): 500 000 agent steps in 1 082 s
  (18 min) with two evaluation processes running in parallel; about 500 steps/s. Resume from
  checkpoints tested (quick run interrupted and continued, both sessions logged).
- Reward scales from Max-Pressure runs on training demand (`configs/reward_norm/`):
  waiting std 151 veh-s per decision; first episodes then have a mean reward of about -0.003
  per decision (no clipping).
- Learning curves (`figures/fig01_training_curves.png`): halting vehicles fall at every demand
  level during the first 150-300k steps (peak 141 -> about 105-115, low 22 -> 17), then plateau.
- Checkpoint selection on validation seeds: the last four checkpoints are within 2 s of each
  other (184.5-186.7 s); 400k steps selected.
- Test seeds (5 runs per cell), IND vs baselines, mean travel time:

| Demand | IND | best baseline | IND vs best baseline | IND vs FT |
|---|---|---|---|---|
| low | 151.6 | ACT 145.0 | -4.6% (p Holm 0.032) | +11.5% |
| medium | 160.8 | ACT 157.3 | -2.2% (p 0.032) | +10.6% |
| peak | 214.5 | MP 210.2 | -2.1% (p 0.69) | +17.9% |
| rush profile | 184.0 | MP 179.9 | -2.2% (p 0.44) | +12.1% |

  IND matches Max-Pressure on mean waiting time at peak (55.5 vs 55.3 s) and has a slightly
  lower P95 wait and Gini (135 vs 137 s; 0.385 vs 0.393), but not a lower travel time.
- Behaviour: IND switches phase about as often as Max-Pressure (4 250-4 700 vs 3 900-4 400
  switches per 90-min episode on 16 junctions). With 250 m links, frequent switching is right
  here - consistent with Webster's short optimal cycle (M1).

### Reward and exploration study (validation seeds 1000-1001 only)

Could a different reward or more exploration close the gap with Max-Pressure? Same seed and
budget (300k steps), mean travel time on validation episodes (`results/exploration/`):

| Variant | medium | peak |
|---|---|---|
| IND, waiting-difference reward (specification) | 162.7 | 211.5 |
| IND, queue-length reward | 161.9 | 212.6 |
| IND, pressure reward (PressLight) | 162.0 | 214.9 |
| IND, entropy bonus 0.01 | 161.8 | 211.9 |
| Max-Pressure | 159.3 | 207.7 |

No variant differs by more than 1.6%: the reward definition is not the bottleneck. We keep
the specified reward and SB3's defaults (FAILURES F-007).

## 2026-09-24 - Inflow forecasting (Tier 2)

Dataset: induction loops at the start of every approach of grid4x4, 1-minute counts, 16
episodes under Max-Pressure (4 demand levels x seeds 6000-6003), 4 sides x 16 junctions.
Task: arrivals of the next 5 minutes per approach from the last 10 minutes and the time in
the demand hour. `python -m cotraffic forecast`; `results/summary/forecast_grid4x4.csv`.

First evaluation was wrong: the chronological test window contained the cool-down, where
the simulation stops all new demand. Persistence "won" (MAE 11.0 vs 14.9 for Ridge) because
the time feature had never seen the end of demand. Targets are now restricted to the demand
period (FAILURES F-008). MAE in vehicles per 5 min (mean target about 40):

| Model | chronological (last third of the demand period) | held-out seeds |
|---|---|---|
| persistence (last 5 min) | 7.53 | 7.19 |
| moving average (last 10 min) | 6.87 | 6.62 |
| ridge regression | 7.52 | 6.46 |
| gradient boosting | 6.91 | 6.40 |

- Learned models improve on persistence by about 10%, but a moving average does almost as
  well. Arrivals are close to Poisson: with the true rate known, the expected absolute error
  of a count with mean 41 is sqrt(2 x 41 / pi) = 5.1 vehicles, so the best models are within
  about 25% of the noise floor. Short-term arrival counts carry little predictable signal
  beyond their recent average.
- The Ridge coefficients are exported (`results/forecasting/ridge_grid4x4.json`) for the
  Tier 3 test (forecast as an observation block, `configs/agents/coop_forecast.yaml`).

## 2026-09-25 - M4: COOP vs IND vs baselines (grid4x4, normal scenario)

14 grid4x4 training runs (IND, COOP, COOP-FULL, COOP-ECO x 2, three seeds each; 500k agent
steps, 25-35 min each with three runs sharing the laptop). Checkpoints selected on
validation seed 1000. Test: 3 training seeds x 5 evaluation seeds = 15 runs per learned
variant and cell, 5 runs per baseline.

Mean travel time (s):

| Method | low | medium | peak | rush profile |
|---|---|---|---|---|
| FT | 171.4 | 179.8 | 261.2 | 209.2 |
| ACT | **145.0** | **157.3** | 275.3 | 195.0 |
| MP | 148.5 | 157.9 | **210.2** | **179.9** |
| IND | 150.8 | 161.1 | 217.5 | 184.5 |
| COOP | 150.8 | 161.0 | 224.6 | 186.7 |

Tests (Mann-Whitney U, Holm; Cliff's delta):

- IND vs best baseline: -4.0% (low, vs ACT) and -2.4% (medium, vs ACT), both p = 0.001, large
  effect; -3.5% (peak, vs MP, p = 0.23) and -2.6% (rush, vs MP, p = 0.16). Mean waiting time at
  peak and rush is equivalent to MP (negligible effect). At medium demand IND's 95th-percentile
  wait is lower than ACT's (55 vs 57 s, p = 0.003).
- COOP vs IND: no difference at low and medium demand (negligible effect); -3.3% at peak
  (p = 0.50, medium effect), -1.2% on the rush profile. The peak gap comes mostly from one
  training seed (COOP t2: 234 s; t1 and t3: 222 and 218 s; IND 215-220 s): the difference
  between IND and COOP is of the order of the spread between training runs.
- Both learned variants beat FT by 10-18% in every cell (p = 0.001).

**RQ1 answer so far:** on the grid, the cooperative agents do not outperform the independent
agents, and neither outperforms the best classical controller of each demand level. They are
consistently better than fixed-time control and never collapse the way actuated control does
at peak. See FAILURES F-009 for the diagnosis.

## 2026-09-25 - Incident scenario redesign and district emergency vehicles

**Incident.** With the stopped vehicle at 40% of the link, the incident barely changed the
network: halting vehicles during the incident window (minutes 35-50) rose by 6.8 (ACT),
5.1 (MP) and -0.5 (FT) vehicles on the 5 test seeds, i.e. 2-4%, and travel times did not
move (MP 212 vs 210 s). Vehicles merge past the obstacle and use both lanes again at the stop
line; the one-lane section (about 1 800 veh/h) never limits the signal. We moved the stopped
vehicle next to the stop line (85% of the link, 31 m before it on grid4x4), where a crash
removes the lane's queue storage and discharge. Checked on validation seed 1000 before
changing the configs: MP +8 halting (+6%), FT +5 (+3%) - still small network-wide, because
the blocked approach carries only part of the traffic and is not at capacity. We therefore
also measure the incident locally: travel time and time loss of the vehicles whose route
crosses the blocked approach (from 10 min before the incident to its end), and the queue
on that approach over time (`incident_affected_*` columns, figure 6). The 30 incident runs
made with the first design were deleted and are re-run (FAILURES F-010).

**Emergency vehicles on the district.** EV-RULE did not reduce the EV delay on the district
test runs (99 s vs 95 s for ACT) while it cut it by 61% on the grid. Diagnosis on validation
seed 1000: the rule works (5 preemptions; delays 9.8 / 16.1 / 53.7 s vs 27.3 / 60.3 / 42.2 s
with ACT), but the district's emergency routes (1.7-3.5 km) cross only 1-2 of the 7 signals,
so most of their delay comes from congestion and unsignalised junctions that signal
preemption cannot remove; with 3-5 EVs per run the difference is within noise. Result rows
now include the number of preemptions.

## 2026-09-25 - Pedestrians on the district: scenario excluded, district runs retrained

While checking the first district training runs we saw COOP-FULL (trained with pedestrians,
buses and emergency vehicles in every episode) stay at about 52 halting vehicles at peak,
against about 7 for IND and COOP. Measured on validation seed 1000 with Max-Pressure at peak:
without pedestrians 134 s mean travel time and 1 teleport; with the pedestrian flow 1 026 s
and 108 teleports. Only 4 of the district's 112 edges have a sidewalk (netconvert guesses
sidewalks on roads up to 50 km/h only), so pedestrians walk on the carriageway of 92 edges.

Consequences and decisions:

- Pedestrian scenarios are not run on the district (`unsupported_scenarios` in its config;
  training leaves them out, evaluation refuses them). The project plan asked for pedestrians
  on the district only "if performance allows"; this is a data limitation of the OSM import.
- The district reward scales had been estimated from runs that included the collapse
  (waiting-term scale 247 veh-s); re-estimated without pedestrians: 31 veh-s.
- The 7 district training runs made so far were discarded and all 9 are retrained with the
  corrected scales, so IND, COOP and COOP-FULL are comparable. The grids are unaffected
  (sidewalks and crossings on every edge).

## 2026-09-26 - Interrupted jobs resumed

The laptop shut down on 2026-09-25 at about 13:00 while two batches were running. Both were
restarted on 2026-09-26 at 17:09 with the same commands, which resume by design.

- **Core evaluation** (`evaluate --experiment core`) had finished 197 of its 310 runs. A
  result file is written only when a run completes, so the restart skipped the finished
  runs and redid the 3 runs that were in progress (their working folders in `results/tmp`
  were incomplete and unused).
- **District training**: COOP-FULL seed 2 had reached 483 840 agent steps, IND seed 3
  85 680, COOP seed 3 75 600; COOP-FULL seed 3 had not started. Each run resumed from its
  latest checkpoint (449 946 steps for COOP-FULL seed 2, 49 994 for IND and COOP seed 3)
  with the saved policy and optimiser state; the resumed session draws its training
  episodes from the same demand pool (seeds 100000-100049).

Checks before evaluating these runs (`results/training/*/real_district/`):

| Run | Resumed from | Final agent steps | PPO rollouts | Log rows |
|---|---|---|---|---|
| IND / COOP / COOP-FULL, seeds 1-2 | - | 501 760 | 280 | 99 |
| COOP-FULL seed 2 | 449 946 | 500 122 | 279 | 98 |
| IND seed 3, COOP seed 3 | 49 994 | 501 578 | 279 | 98 |

- Every run reached the 500 000-step budget. A run stops at the first complete rollout
  (256 steps x 7 agents = 1 792 agent steps) beyond the budget. The rollout that was being
  collected when the laptop stopped was lost (1 610 agent steps for the seed-3 runs, 154 for
  COOP-FULL seed 2), so each resumed run trained on one rollout less than an uninterrupted
  one: 499 968 against 501 760 agent steps, 0.4% of the budget.
- The training logs (`episodes.csv`) of the resumed runs contained the episodes of the
  interrupted session after the checkpoint (8, 6 and 7 rows), produced by a policy that was
  never saved. We removed them; `train` now does this itself when it resumes. Every log now
  has strictly increasing steps, no duplicate, and one row per 5 040-step episode, except
  one wider gap at the resume point: the episode in progress when the checkpoint was
  written finished under the lost policy, so neither session has a row for it.
- Checkpoint selection used validation seed 1000 at medium and peak demand; the test runs
  use seeds 0-4 and training seeds 100000-100049, so no demand realisation is shared. The
  ranges were a convention; `select` and `evaluate` now refuse seeds outside their range
  (`cotraffic/seeds.py`).
- Selection may pick a checkpoint written before the interruption: COOP-FULL seed 2 kept its
  449 946-step checkpoint, the one it resumed from.

## 2026-09-26 - Grid4x4: COOP-FULL, CO2 reward, emergency vehicles, incident, sensor noise

These grid4x4 cells of the core matrix are complete (learned variants: 3 training seeds x 5
evaluation seeds; baselines: 5 runs). p-values below are Mann-Whitney U before the Holm
correction; the corrected values are in `results/summary/comparisons_*.csv`.

**COOP-FULL on normal traffic.** 151.9 / 161.1 / 219.7 / 184.5 s at low / medium / peak /
rush, against 150.8 / 161.1 / 217.5 / 184.5 s for IND. Its extra observation blocks and
reward terms neither cost nor gain anything without emergency vehicles (at low demand it is
1 s slower, p = 0.01).

**RQ2 - emergency vehicles (peak).** Mean emergency-vehicle delay and mean travel time of
all vehicles (s):

| Method | EV delay | Travel time |
|---|---|---|
| FT | 154.7 | 261.6 |
| ACT | 149.8 | 278.0 |
| MP | 106.3 | 211.6 |
| EV-RULE (preemption on top of ACT) | **58.2** | 288.1 |
| COOP | 115.9 | 225.3 |
| COOP-FULL | 73.5 | **219.2** |

- COOP-FULL halves the EV delay compared with ACT (-51%, p = 0.003) and cuts it by 37%
  compared with COOP (p = 0.0001), on each of its training seeds (64 / 88 / 68 s against
  111-123 s for COOP).
- EV-RULE remains the fastest for the emergency vehicle (COOP-FULL +26%, p = 0.23), but it
  is built on the actuated controller, which breaks down at peak. COOP-FULL gets most of the
  preemption benefit while the other vehicles travel 24% faster than with EV-RULE. It does
  so with no override rule: only the EV observation block and the EV term of its reward.
- The weight of that term (lambda_ev = 2) is checked with lambda_ev = 1 and 4 (training).

**RQ3 - CO2.** COOP with a CO2 penalty in the reward (lambda_co2 = 0.5 and 1.0):

| Method | CO2 medium (kg) | travel medium (s) | CO2 peak (kg) | travel peak (s) |
|---|---|---|---|---|
| COOP | 2 270 | 161.0 | 4 190 | 224.6 |
| COOP-ECO, lambda 0.5 | 2 257 | 160.2 | 4 050 | 215.2 |
| COOP-ECO, lambda 1.0 | 2 255 | 160.0 | 4 091 | 218.2 |
| IND | 2 273 | 161.1 | 4 090 | 217.5 |
| MP | **2 205** | **157.9** | **3 959** | **210.2** |

- The CO2 penalty lowers CO2 and travel time together. Over the 90 runs of each demand
  level, network CO2 and mean travel time are correlated at 0.93 (medium) and 0.99 (peak):
  on this network the CO2 difference between controllers is the time vehicles spend
  stopped and idling. There is no trade-off to trace - the Pareto front of RQ3 reduces to
  one point, and Max-Pressure is best on both axes.
- The gain of COOP-ECO (lambda 0.5) over COOP at peak (-4.2% travel time, -3.3% CO2,
  p = 0.04) comes largely from COOP's weak training seed t2; against IND the difference is
  1%. The CO2 term acts as one more congestion signal.
- We report RQ3 as a negative result with this explanation. A real trade-off would need
  vehicles whose emissions depend more on the speed profile than on time (heavy goods
  vehicles, gradients), which our demand does not contain.

**RQ4 - incident (vehicle stopped 31 m before the stop line, minutes 35-50, peak).** Mean
travel time of all vehicles and of the 384 vehicles per run whose route crosses the blocked
approach (s):

| Method | all vehicles | affected vehicles | affected time loss |
|---|---|---|---|
| FT | 261.3 | 332.7 | 218.0 |
| ACT | 287.9 | 331.0 | 216.3 |
| MP | **212.5** | **267.0** | **152.4** |
| IND | 219.2 | 292.8 | 178.1 |
| COOP | 227.3 | 299.1 | 184.5 |
| COOP-FULL | 221.8 | 275.7 | 161.1 |

- Network-wide the incident costs 1% of travel time for MP and the learned agents (e.g. MP
  210.2 -> 212.5 s), 5% for ACT; locally it is large for every controller.
- Max-Pressure serves the affected vehicles best. IND (+9.6%, p = 0.04) and COOP (+12%,
  p = 0.08) are behind; COOP-FULL is closest (+3.3%, p = 0.44). None of the learned agents
  saw an incident during training.

**RQ4 - sensor faults (peak; Gaussian noise of 2 vehicles on every count, 20% of the lane
detectors reporting 0 for the whole episode).** Mean travel time (s):

| Method | normal | sensor faults | change |
|---|---|---|---|
| MP | 210.2 | 255.4 | +21.5% |
| IND | 217.5 | 220.4 | +1.4% |
| COOP | 224.6 | 247.7 | +10.3% |

- IND is the most robust controller and is 13.7% faster than MP under sensor faults
  (p = 0.03). MP loses 5-10% on four evaluation seeds and collapses on seed 3 (359 s,
  18 teleports, 189 vehicles unfinished, a maximum wait of 1 762 s). MP chooses phases from
  the detector counts only; a movement whose detectors read 0 exerts no pressure, and the
  shield's anti-starvation rule, which acts on detected demand, never fired (FAILURES F-012).
- IND keeps switching as often as without faults (4 938 vs 4 979 switches per episode), so
  it serves lanes by rhythm as much as by counts - a likely reason for its robustness.
- COOP's loss comes from one training seed: t2 goes from 234 to 288 s (+23%) while t1 and t3
  lose 3% and 2%. Messages carry the neighbours' noisy counts, so a faulty detector reaches
  two agents; with three training seeds we cannot tell whether this makes COOP systematically
  more fragile or whether t2 is simply a weaker policy (it is also the slowest without
  faults).

## 2026-09-26 - Core matrix complete; statistics and importance revised

The core matrix is complete: 790 runs, none failed (`evaluate --experiment core`, the
learned district cells last, after the district checkpoints were selected). The results
per research question are written up in `docs/report/08_results.md`; the main numbers:

- RQ1: IND is 0.2-4.0% and COOP 0.4-6.9% slower than the best baseline of each cell
  (actuated control at low and medium demand, Max-Pressure at peak, on the rush profile and
  on the district); 10-20% faster than FT, except district medium (2.5-2.7%).
- RQ2: COOP-FULL EV delay 73.5 s vs 149.8 s (ACT) and 58.2 s (EV-RULE); cost to the traffic
  as a whole vs MP +3.6% [+2.1, +5.1], EV-RULE +36.2% [+30.0, +42.2] (paired).
- RQ5: on grid8x8 (zero-shot) IND and COOP are 4.0-4.1% slower than MP and 14.3-14.5%
  faster than FT.
- District: all controllers but FT within 153-160 s at peak; the test seed dominates (the
  same policy ranges from 128 to 197 s).

**Statistics revised (ADR-005).** With the ordinary bootstrap, the 15 runs of a learned
variant were treated as independent although they come from 3 training runs; COOP's
interval at grid peak was [218.4, 230.9] while its training runs average 218, 222 and
234 s. Intervals of learned variants now resample training runs and test seeds (two-way
bootstrap): [213.3, 236.3]. We also compare methods paired on the test seed. Both change
the reading of the results in one direction: at grid peak and on the rush profile, where
the Holm-corrected Mann-Whitney test finds no difference, the paired intervals show that
the learned agents are consistently slower than Max-Pressure (IND +3.5% [+2.0, +5.4]
and +2.6% [+1.6, +3.5]). The p-values of learned variants remain optimistic; we say so in
the report.

**Feature importance revised (fig. 12).** The first version reported that shuffling the
emergency-vehicle block changes 0.4% of COOP-FULL's decisions, which read as "unused",
while COOP-FULL halves the EV delay. An emergency vehicle is in range for 0.7% of
decisions, so a rate over all decisions dilutes the block. The block is now scored on the
decisions where it is non-zero (40% change), the online replays record the EV delay (+75%
when the block is shuffled, 64 -> 112 s), blocks that are constant in the scenario are
left out (pedestrians and buses in the emergency scenario), and 5 test seeds are used
instead of 2. One replay took 90 min instead of 1: the laptop was in standby from 19:35 to
21:04 (Windows power events).

**Training times.** Six runs include laptop standby (e.g. the seed-1 district runs:
552-561 min measured) and three were resumed. The report tables now give episodes x median
time per episode (16-47 min per run, three runs sharing the laptop) with a note on those
runs.

## 2026-09-26 - EV-RULE-MP: preemption judged against its own base controller

Reviewing the RQ2 draft, we noticed that EV-RULE runs on actuated control, which breaks
down at grid peak on its own (278.0 s vs 211.6 s for MP): the "+36% cost of preemption"
was mostly the cost of actuated control (FAILURES F-013). We added EV-RULE-MP, the same
200 m preemption rule on top of Max-Pressure, requested at each 5-s decision through the
shield (`controllers/ev_preemption.py`), and evaluated it on the two emergency cells of
the core matrix (5 test seeds each, part of the `sensitivity` experiment; 10 runs, none
failed).

Grid4x4 at peak, each mechanism against its own base (paired by test seed):

| Mechanism | EV delay (s) | vs base | Travel time (s) | vs base |
|---|---|---|---|---|
| EV-RULE on ACT | 58.2 | -61.1% [-68.8, -50.2] | 288.1 | +3.6% [+1.4, +5.8] |
| EV-RULE-MP on MP | 38.1 | -64.2% [-69.7, -55.3] | 212.4 | +0.4% [-0.5, +1.0] |
| COOP-FULL vs COOP | 73.5 | -36.6% [-49.4, -16.6] | 219.2 | -2.7% [-3.7, -1.4] |

EV-RULE-MP beats COOP-FULL on both criteria (EV delay: COOP-FULL +93%, paired
[+58, +138], every COOP-FULL run slower; travel time: +3.2% [+1.6, +5.0]). On the district
nothing is significant (EV delays 85-134 s for all methods, intervals of +-60 to +-120 s;
EV-RULE-MP preempts 7 times per run there, 24 on the grid). The RQ2 statements of the
earlier entries today ("most of the benefit of preemption without its collateral cost")
are superseded: report sections 8.2 and 9.3 were rewritten.

**Holm family.** EV-RULE-MP is a baseline, and the sensitivity and extended results add
cells and variants; with a single family, adding results would have changed the corrected
p-values of the report. The confirmatory family is now fixed to the core matrix and its
variants; everything else is corrected in a separate, exploratory family (ADR-005).

## 2026-09-27 - PED-RULE-MP: a pedestrian-aware reference

COOP-FULL's pedestrian result (-29% mean wait against MP) was measured against baselines
that choose phases from vehicle counts only. We added PED-RULE-MP: Max-Pressure, plus a
crossing whose longest-waiting pedestrian has waited more than 30 s requests its green at
the next decision (threshold from the Highway Capacity Manual's impatience delay, set in
`configs/protocol.yaml` before any run; `controllers/pedestrian_rule.py`). 5 runs on the
pedestrian cell of the core matrix, none failed.

| Method | mean ped. wait (s) | longest ped. wait (s) | vehicle travel time (s) |
|---|---|---|---|
| MP | 17.7 | 176.8 | 164.7 |
| PED-RULE-MP | 16.4 | 109.0 | 164.8 |
| COOP-FULL | 12.5 | 114.9 | 169.1 |

Paired: PED-RULE-MP vs MP -7.3% mean wait [-12.4, -1.4], -38.3% longest wait
[-50.4, -22.4], +0.1% travel time [-0.7, +0.9]; COOP-FULL vs PED-RULE-MP -23.8% mean
wait [-28.1, -18.2], +2.6% travel time [+1.3, +5.1], +7.2% person-weighted vehicle delay
[+3.6, +14.0]. The rule caps the long waits for free; COOP-FULL shortens the typical wait
and pays in vehicle time. With one threshold we cannot say whether a shorter one would
dominate COOP-FULL. Report section 8.7 rewritten.

## 2026-09-27 - Sensitivity experiment: forecast agent and EV weight

`evaluate --experiment sensitivity` (checkpoints of the new variants selected on validation
seed 1000 first): 55 runs of the learned variants, none failed, plus the EV-RULE-MP and
PED-RULE-MP runs above.

**Forecast agent (RQ6, Tier 3).** COOP with the Ridge forecast in its observation, 3
training runs, grid4x4 normal: 160.8 / 218.0 / 183.7 s at medium / peak / rush profile.
Against IND -0.2% / +0.3% / -0.4% (intervals include zero), against COOP -0.1% / -2.9% /
-1.6%, against MP +1.8% / +3.7% / +2.1%. Its three runs are as close to each other as
IND's (217-219 s at peak), so the gap to COOP is COOP's weak run t2, not the forecast.
No measurable gain from forecasting, consistent with the forecast accuracy near the
Poisson noise floor.

**EV weight.** COOP-FULL with lambda_ev = 1 and 4 (one training run each, seed 1),
emergency cell at peak, against COOP-FULL t1 (lambda_ev = 2): EV delay 109.7 s (+70%) and
63.3 s (-2%, not significant); travel time +4.4% and +1.7%. This suggests that
lambda_ev >= 2 is needed and that a larger weight adds nothing, but each value rests on a
single training run and the spread between runs is large (COOP t2): indicative only.

## 2026-09-27 - Extended matrix complete

`evaluate --experiment extended` (430 runs, 4 workers, 00:08-01:55). Two fixed-time runs
failed at the start: four workers wrote the same fixed-time plan at once and Windows
refused the rename (fixed in `controllers/programs.py`, test with six concurrent writers)
and were rerun. Full matrix: 1 220 runs, sensitivity: 70 runs, none missing. Results in
report section 8.10 (exploratory family). New findings:

- COOP-FULL gridlocks in 4 of 15 runs at peak with pedestrians (FAILURES F-014); the other
  11 runs are close to Max-Pressure.
- Accident on the district: Max-Pressure serves the affected vehicles worst (+13.8% vs
  ACT); IND is 11.3% better than Max-Pressure there - the opposite of the grid.
- Emergency vehicles at medium demand repeat the peak result: preemption -60% EV delay on
  either base at +0.1-0.2% travel time; COOP-FULL -31% vs COOP, behind EV-RULE-MP.
- Buses at peak: COOP-FULL -7.9% bus delay vs Max-Pressure, +4.0% person-weighted delay.
- Elsewhere the learned agents stay 2.4-3.7% behind the best baseline (medium demand,
  grid8x8) or within the noise (district low and rush profile).

## 2026-10-03 - Incident duration in short episodes; accident in the demo

The stopped vehicle's stop lasted `duration_s` (900 s) unscaled, while its start and the
incident window recorded in the bundle were scaled to the episode length. In evaluation
episodes (60-min measured hour, scale 1) both agree, so no reported result changes. In
quick episodes (10-min hour) the vehicle stayed until the end of the episode instead of
150 s; validation and training episodes never contain the incident. The stop now uses the
scaled duration, and `GENERATOR_VERSION` is 4 so that cached bundles are rebuilt. We
regenerated the evaluation bundles of the incident cell (grid4x4 and district, seed 0) and
of the grid emergency cell: the route files are identical to the previous ones apart from
duarouter's header comment.

The side-by-side demo gained `--follow-incident`: it adds the incident scenario, fast-forwards
to one minute before it, puts the camera on the stopped vehicle once it is on the road
(a vehicle loaded but not yet inserted reports an invalid position), and charts the
vehicles stopped on the blocked street and the trip time of the vehicles routed through it.
On the district the blocked street is a two-lane avenue and drivers pass the stopped
vehicle on the other lane: over the five evaluation runs of Max-Pressure the number of
halted vehicles on that street, the stopped vehicle included, averaged 0.6 during minutes
35-60 (3.0 on grid4x4), so the accident is far more visible on the grid.

## 2026-10-04 - Accident and pedestrians in the demo

**Accident display.** In the demo the stopped vehicle was a small magenta car among many;
viewers did not see it. It now has its hazard lights on, a flashing red zone around it and
an ACCIDENT sign beside the road, drawn with SUMO polygons and points of interest, which do
not interact with traffic. The camera aims at it once it is on the road and checks the
width of the view it obtained (a window not redrawn yet is measured wrong), retrying at the
next decision.

**Pedestrians in the district (demonstration variant).** The district import has sidewalks
on 4 of its 112 edges because netconvert guesses sidewalks, and crossings at junctions,
only on roads up to 50 km/h, and 106 of the imported edges are faster (70-142 km/h;
FAILURES F-011). A first variant with sidewalks everywhere but default crossings (21
crossings) failed: SUMO found no walking route between two streets and stopped. With
crossings guessed at every junction
too, `real_district_ped` (same extract, same signals and demand) has sidewalks on 106 edges,
57 crossings and one connected walking network of 107 edges. Its signals keep at most 3
vehicle green phases, as the district, so the agents trained on real_district drive it;
the junction at Place du 14 Janvier 2011 has 5 crossings where the padding has 4, and the
network config accepts that the fifth is signalled but not observed
(`extra_crossings_unobserved`, refused everywhere else).

One quick episode at peak, seed 3, emergency vehicles and buses (with pedestrians on the
variant): Max-Pressure 133 s mean travel time on real_district, 160 s on the variant with
137 pedestrians (mean wait 21 s); COOP-FULL (district run 1, never trained with
pedestrians there) 136 s and 168 s (pedestrian wait 22 s). Single short episodes, for the
demonstration only; the variant is not part of the evaluation.

## 2026-10-04 - Demo look and live chart

Display only; no simulation or result changes.

**Windows.** Three levels of lightness now separate the street from the blocks: dark
asphalt for roads and junctions, light paving for sidewalks and crossings, mid-light green
for the blocks (sumo-gui lane and junction colour schemes). Road users stand out on what
they move on: light blue cars on the asphalt, deep blue pedestrians on the paving, drawn at
a constant size on the screen; vehicles use sumo-gui's detailed shapes. The legend carries
the colour of the window's line in the live chart and is drawn at twice the screen size.
Turning on sumo-gui's antialiasing made the windows lag: screenshots showed frames from
minutes earlier, so it stays off.

**Live chart.** Rewritten in `scripts/demo_chart.py`: headline tiles give each measure for
both controllers and the difference between them (within 1%: "about the same", the noise of
one episode), followed by the measures over time on a fixed time axis. The report's method
colours are not distinct in every pair: MP orange against COOP-FULL yellow fails the
normal-vision separation check (Delta E 13.7, floor 15), so the demo marks the windows
instead, left blue and right orange (Delta E 33.6, colour-blind separation 24.7). New
measure: pedestrians standing still, counted each decision, with their accumulated waiting.

## 2026-10-09 - Assistant with a local language model

Questions about the results and demo requests in plain French, answered from the result
files (ADR-011): Ollama 0.40.2 serving `qwen2.5:3b` on the laptop (i5-1135G7, 12 GB, CPU
only). Measured with `scripts/check_assistant.py` on 15 questions and 6 demo requests whose
correct reading is fixed in the script:

| reading | questions | demo requests |
|---|---|---|
| keywords | 14 / 15 | 6 / 6 |
| model alone | 5 / 15 | 4 / 6 |
| assistant (final design) | 14 / 15 | 6 / 6 |

The model alone fills fields the request does not mention: a network ("le quartier" for a
question naming none), "normal" traffic, another measure. In the first design, where the
model's reading was kept for every field the user had not written, two of six full answers
were wrong for that reason (the emergency-vehicle delay of EV-RULE-MP taken from the
district instead of the grid). Keywords now read first; the model reads only a question the
keywords cannot classify, and a network or demand level the question does not mention is
left to the defaults. The one request missed by all readings is a paraphrase ("l'agent qui
gère aussi les piétons et les urgences" for COOP-FULL). One reading by the model takes 6-18 s.

Writing: the model phrases the answer from the facts found by code. Of six full answers in
the first run, four passed the number guard; one had dropped the minus sign of an interval
bound ("de 4,7 à 15,8 %" for [-4.7, 15.8]) and passed, and one wrote "quatre contrôleurs"
for three. The guard now keeps the sign of interval bounds and reads numbers written in
words, and "4×4" or "IC 95 %" no longer count as values. Final run: five of six answers
written by the model, the sixth (the COOP-MP comparison on the district) rejected by the
guard and replaced by the sentence written by code; 9-24 s per answer. Run again alone, the
same question was answered by the model and accepted: outputs are not strictly identical
between runs on this CPU despite temperature 0 and a fixed seed, which the guard and the
fallback absorb. Wording remains imperfect at times (Max-Pressure called an "agent"), never
with a number outside the facts.
