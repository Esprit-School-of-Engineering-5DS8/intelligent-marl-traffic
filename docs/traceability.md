# Traceability: brief -> implementation -> evidence

Status: **done** = implemented and evidenced, **impl.** = implemented, evidence pending, **planned** = not implemented yet.

| Brief item | Where it is implemented | Evidence (figure / table / file) | Status |
|---|---|---|---|
| Design Thinking methodology | `docs/design_thinking/` | stage documents (interviews by the team) | impl. |
| Q1 What information should an agent use? | `src/cotraffic/envs/observations.py` (blocks) | ablations IND vs COOP, permutation importance (Fig. 12) | impl. |
| Q2 What decisions should it make? | next green phase every 5 s, `envs/traffic_env.py`, shield `envs/shield.py` | ADR-003, shield intervention counts | impl. |
| Q3 Independent or cooperative? | `observation.neighbours` (COOP) vs IND | RQ1, Fig. 1-3 | planned |
| Q4 How to evaluate performance? | `evaluation/metrics.py`, `analysis/stats.py` | metric definitions, CIs, tests | planned |
| Q5 Which DS/AI approaches? | PPO + parameter sharing, Max-Pressure, forecasting, statistics, explainability | ADRs, forecasting table, Fig. 12 | planned |
| Q6 Factors beyond traffic flow | EVs, CO2, pedestrians, buses, incidents, failures, scale | RQ2-RQ5, Fig. 4-9, 11 | planned |
| Working prototype | whole repository; `make smoke`, `make demo`, dashboard | smoke log, demo video | impl. |
| Experiments under different traffic conditions | `configs/demand`, `configs/scenarios`, `configs/experiments` | REPORT_TABLES.md | planned |
| Comparison with baselines | `src/cotraffic/controllers` (FT, ACT, MP, EV-RULE) | main table, Fig. 2-3 | planned |
| Evidence of strengths and limitations | `analysis/`, `docs/FAILURES.md` | significance tests, limitations section | planned |
| Extension: emergency vehicles | demand generator, EV observation/reward, EV-RULE | Fig. 5 | impl. |
| Extension: pedestrians | sidewalks/crossings, pedestrian observation/reward | Fig. 11 | impl. |
| Extension: public transport | bus lines, person-weighted reward and delay | Fig. 11 | impl. |
| Extension: sustainability / pollution | CO2 reward term, emission metrics | Fig. 4 | impl. |
| Extension: accident scenarios | incident scenario (blocked lane) | Fig. 6 | impl. |
| Extension: communication between agents | neighbour messages, dropout scenario | RQ1, Fig. 8 | impl. |
| Extension: prediction | `src/cotraffic/forecasting` | forecasting table | planned |
| Extension: large-scale networks | grid8x8 zero-shot | Fig. 9 | planned |
| Real city district | `configs/networks/real_district.yaml` (OpenStreetMap) | district results | planned |
| Real traffic counts (GEH) | only if counts are provided | GEH table | planned |
