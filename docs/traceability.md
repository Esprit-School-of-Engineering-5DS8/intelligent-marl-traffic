# Traceability: brief -> implementation -> evidence

Status: **done** = implemented and evidenced, **impl.** = implemented, evidence pending, **planned** = not implemented yet.

| Brief item | Where it is implemented | Evidence (figure / table / file) | Status |
|---|---|---|---|
| Design Thinking methodology | `docs/design_thinking/` | stage documents (interviews by the team) | impl. |
| Q1 What information should an agent use? | `src/cotraffic/envs/observations.py` (blocks) | ablations IND vs COOP, permutation importance (Fig. 12), report 8.9 and 9.1 | done |
| Q2 What decisions should it make? | next green phase every 5 s, `envs/traffic_env.py`, shield `envs/shield.py` | ADR-003, shield intervention counts | impl. |
| Q3 Independent or cooperative? | `observation.neighbours` (COOP) vs IND | RQ1, Fig. 1-3, 8, 12; report 9.1; F-009 | done |
| Q4 How to evaluate performance? | `evaluation/metrics.py` (tested on hand-written SUMO outputs), `analysis/stats.py`, ADR-005 | REPORT_TABLES.md (CIs, Mann-Whitney + Holm, Cliff's delta) | done |
| Q5 Which DS/AI approaches? | PPO + parameter sharing (ADR-008), Max-Pressure, forecasting (`src/cotraffic/forecasting`), statistics, explainability (`src/cotraffic/explainability`) | ADRs, reward study (F-007), forecasting table, Fig. 12 | impl. |
| Q6 Factors beyond traffic flow | EVs, CO2, pedestrians, buses, incidents, failures, scale | RQ2-RQ5, Fig. 4-9, 11; report 8.2-8.7 | done |
| Working prototype | whole repository; `make smoke` (12 checks), `make demo`, `dashboard/app.py` | smoke log, dashboard, demo video (team) | done (demo video: team) |
| Experiments under different traffic conditions | `configs/demand`, `configs/scenarios`, `configs/experiments/full_matrix.yaml` | REPORT_TABLES.md, Fig. 2, 7 | impl. |
| Comparison with baselines | `src/cotraffic/controllers` (FT Webster, ACT, MP, EV-RULE), ADR-004 | journal M2, REPORT_TABLES.md, Fig. 2-3 | done |
| Evidence of strengths and limitations | `analysis/`, `docs/FAILURES.md` (F-001..F-007) | significance tests, paired analysis, negative results (F-001..F-012), report section 10 | done |
| Extension: emergency vehicles | demand generator, EV observation/reward, EV-RULE | Fig. 5, 12; report 8.2 | done |
| Extension: pedestrians | sidewalks/crossings, pedestrian observation/reward | Fig. 11 (grid only, F-011) | done |
| Extension: public transport | bus lines, person-weighted reward and delay | Fig. 11 | done |
| Extension: sustainability / pollution | CO2 reward term, emission metrics | Fig. 4; report 8.3 | done |
| Extension: accident scenarios | incident scenario (blocked lane) | Fig. 6; report 8.4 | done |
| Extension: communication between agents | neighbour messages, dropout scenario | RQ1, RQ4, Fig. 8; report 8.4, 9.1 | done |
| Extension: prediction | `src/cotraffic/forecasting` (persistence, moving average, Ridge, gradient boosting) | forecasting table in REPORT_TABLES.md; forecast agent evaluated (report 8.6, 9.5) | done |
| Extension: large-scale networks | grid8x8 (64 signals), zero-shot cell of `full_matrix` | Fig. 9; report 8.5 | done |
| Real city district | `configs/networks/real_district.yaml` (OpenStreetMap, placeholder Tunis, ADR-006) | district results, report 8.1-8.2 | done |
| Real traffic counts (GEH) | only if counts are provided; demand is synthetic (documented) | - | not available |
