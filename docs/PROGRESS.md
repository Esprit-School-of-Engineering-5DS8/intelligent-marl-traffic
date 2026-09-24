# Progress

| # | Milestone | Status |
|---|---|---|
| M0 | Repo skeleton, environment, SUMO running, tests | done (2026-09-24) |
| M1 | Networks, demand levels, rush profile, vehicle types, scenarios | in progress |
| M2 | Evaluation pipeline, metrics, baselines FT / ACT / MP / EV-RULE | planned |
| M3 | PPO training with parameter sharing, checkpoint/resume, IND | planned |
| M4 | COOP (neighbour communication), reward normalisation | planned |
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
