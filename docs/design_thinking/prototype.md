# 4. Prototype - what we built

## Architecture

```
configs/*.yaml ──> networks (grid, OpenStreetMap) ──> demand generator (cars, buses,
                                                       emergency vehicles, pedestrians, incidents)
                                                                   │
                                                                   ▼
            ┌──────────────── SUMO (libsumo) ───────────────────────────┐
            │  signalised intersections, vehicles, pedestrians, emissions │
            └──────────────▲──────────────────────────┬───────────────────┘
          executed phase   │                          │ lane measurements, EV/bus/pedestrian data
                 ┌─────────┴────────┐        ┌────────▼─────────┐
                 │  safety shield   │◄───────│   observations   │◄── neighbour messages (COOP)
                 └─────────▲────────┘        └────────┬─────────┘
          proposed phase   │                          │
                 ┌─────────┴──────────────────────────▼─────────┐
                 │ controller: shared PPO policy | Max-Pressure  │
                 │ (fixed-time and actuated run inside SUMO)     │
                 └───────────────────────────────────────────────┘
                                   │
                                   ▼
             evaluation runner ──> metrics (SUMO outputs) ──> statistics ──> figures, tables, dashboard
```

## Components

| Component | Code | Role |
|---|---|---|
| Networks | `src/cotraffic/networks` | grid networks with netgenerate, district from OpenStreetMap |
| Demand | `src/cotraffic/demand` | seeded demand per level and profile, buses, emergency vehicles, pedestrians, incidents |
| Environment | `src/cotraffic/envs` | PettingZoo environment, intersection model, shield, observations, rewards |
| Controllers | `src/cotraffic/controllers` | fixed-time (Webster), actuated, Max-Pressure, emergency preemption, learned policies |
| Training | `src/cotraffic/training` | PPO with parameter sharing, checkpoints, resume |
| Evaluation | `src/cotraffic/evaluation` | episode runner, metrics, experiment matrix |
| Analysis | `src/cotraffic/analysis` | statistics, figures, report tables |
| Dashboard | `dashboard/app.py` | interactive exploration of the results |

## What the prototype does not do

- It runs in simulation only. Demand on the district is synthetic unless real counts are
  provided (see `docs/traceability.md`).
- Emergency vehicles obey signals in our model (no blue-light behaviour), so their delay
  is a direct measure of how well the signals clear their way.
- Pedestrian clearance is simplified: crossings turn red at the start of the vehicle
  yellow.

## TEAM - prototype iterations

Record here each iteration shown to users or supervisors, what they said, and what we
changed.
