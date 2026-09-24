# Progress

| # | Milestone | Status |
|---|---|---|
| M0 | Repo skeleton, environment, SUMO running, tests | done (2026-09-24) |
| M1 | Networks, demand levels, rush profile, vehicle types, scenarios | done (2026-09-24) |
| M2 | Evaluation pipeline, metrics, baselines FT / ACT / MP / EV-RULE | done (2026-09-24) |
| M3 | PPO training with parameter sharing, checkpoint/resume, IND | done (2026-09-24) |
| M4 | COOP (neighbour communication), reward normalisation | in progress (training) |
| M5 | COOP-ECO, COOP-FULL, incident evaluation, real district training | planned |
| M6 | Pedestrians, buses, sensor noise, comm dropout, grid8x8, forecasting, explainability - feature freeze | planned |
| M7 | Full experiment matrix, statistics, figures, tables | planned |
| M8 | Dashboard, demo script, docs, README results | planned |

## M0 - summary (2026-09-24)

- Works: SUMO 1.27.1 via libsumo; our PettingZoo environment (`src/cotraffic/envs`)
  with intersection model, safety shield, observation blocks (local, phase, neighbours,
  emergency, pedestrians, buses), reward terms; seeded demand generator with cars,
  buses, emergency vehicles, pedestrians and incidents; grid networks.
- Tests: 62 passing (`pytest`), including PettingZoo's `parallel_api_test` and a replay
  of SUMO's real signal states checking yellow transitions and minimum greens.
- Measured: a random-policy hour on grid4x4 costs 6-7 s of wall time (16 agents).
- Problems: sumo-rl 1.4.5 did not fit the design (ADR-002); pinned versions re-chosen
  for Python 3.10 compatibility (F-002).
- Next: M1 - OpenStreetMap district, demand calibration against fixed-time control,
  all scenarios end-to-end in quick mode.

## M1 - summary (2026-09-24)

- Works: grid2x2/4x4/8x8 and the OSM district (7 signals, placeholder in central Tunis,
  ADR-006); demand levels and rush-hour profile; buses, emergency vehicles, pedestrians,
  incidents; sensor noise and communication dropout; Webster FT, actuated, Max-Pressure
  and EV-RULE baselines; metrics and episode runner (built early to calibrate demand).
- Measured: peak rates calibrated against fixed-time control - grid4x4 8 800 veh/h,
  district 5 200 veh/h, grid8x8 14 000 veh/h (journal M1); Webster plan checked against
  longer-cycle plans (it is the best of them).
- Tests: 79 passing; smoke covers every scenario and baseline in quick mode.
- Problems: sparse OSM signal tags (F-003), tlsCycleAdaptation unusable with pedestrian
  clearance phases (F-004), unreachable OD pairs on the real network (F-005).
- Next: M2 - experiment runner over a matrix of cells, baseline results on grid4x4 with
  5 seeds, statistics and the first comparison table.

## M2 - summary (2026-09-24)

- Works: experiment matrix runner (resumable, parallel, per-cell SSM switch), bootstrap CIs,
  Mann-Whitney U with Holm correction, Cliff's delta, report tables, figures, dashboard.
- Measured (grid4x4, 5 seeds): ACT best at low/medium demand, MP best at peak and on the rush
  profile; FT 12-20% behind MP; EV-RULE cuts emergency-vehicle delay by 61% vs ACT for +3.6%
  travel time of the others (journal M2).
- Problems: 5-vs-5 comparisons cannot reach significance after Holm (documented, ADR-005);
  a route cache corrupted by a killed process (now rebuilt automatically).
- Next: M3 training.

## M3 - summary (2026-09-24)

- Works: PPO with parameter sharing through SuperSuit, reward normalisation from baseline
  runs, checkpoints every 50k steps with resume, checkpoint selection on validation seeds,
  Kaggle and Colab notebooks, training smoke check.
- Measured: 500k agent steps in 18 min on the laptop. IND beats FT by 11-18% at every demand
  level and matches MP's waiting time, but is 2-5% slower than the best baseline in travel
  time (journal M3). Reward and entropy variants do not change this (F-007).
- Problems: SuperSuit / SB3 API mismatches (F-006).
- Next: M4 - COOP (3 seeds), then all variants and the district (training batch running).
