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
