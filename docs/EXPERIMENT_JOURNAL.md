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
