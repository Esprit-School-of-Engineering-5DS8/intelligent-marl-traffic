# ADR-001: Traffic simulator

- Status: accepted
- Date: 2026-09-24

## Context

The project needs a traffic simulator that reproduces signalised intersections at the
vehicle level, can be controlled step by step from Python, and measures more than flow:
emissions, pedestrians, buses, emergency vehicles, near-misses. It must run on student
laptops and free notebook services, CPU only, and import real streets for the city
district.

## Options considered

| Option | For | Against |
|---|---|---|
| SUMO (Eclipse) | Open source, microscopic; TraCI/libsumo control; HBEFA emission model; pedestrian model with crossings; SSM device (time-to-collision); OpenStreetMap import; `pip install eclipse-sumo` on Windows, Linux, Kaggle, Colab | Slower than CityFlow; several tools and options to learn |
| CityFlow | Very fast, used in many RL papers | No pedestrians, emissions or safety measures; OSM import limited; project less maintained |
| Aimsun / VISSIM | Industry standard | Commercial licences, Windows-only GUI tools, no free CPU cloud use |
| Our own simulator | Full control | Months of work and no credibility for the results |

## Decision

We use SUMO 1.27 through `libsumo` (in-process, fast) for training and evaluation, and
TraCI with `sumo-gui` only for demonstrations. SUMO is installed from the
`eclipse-sumo` wheel, so no system install is needed.

## Consequences

- One simulation per Python process with libsumo; we parallelise with processes.
- The HBEFA4 emission classes, the SSM device and the pedestrian model come for free,
  which lets us answer the "beyond traffic flow" question with measured data.
- Measured speed on the grid4x4 network (random policy, 16 agents, 1 simulated hour,
  all observation blocks): about 6-7 s of wall time on the team laptop (i5-1135G7).
  Training budgets of several hundred thousand agent steps are therefore affordable.
