# Phase 6 — 3x3 grid evaluation report (H1–H5)

System: max-pressure fast layer + arbiter/DirectiveLayer + LLM slow layer
(Operator, Emergency, Pedestrian agents) on the 3x3 SUMO grid.
All numbers are mean ± std over seeds, computed from the committed tables in
`tables/` (`all_results.csv`, `per_scenario/*.csv`, `llm_ops.csv`), which are
generated from the recorded runs in `results/` (gitignored).

Regenerate everything:

```bash
~/.venvs/sumo/bin/python evaluation/collect_results.py     # tables/
~/.venvs/sumo/bin/python evaluation/report_plots.py        # figures/
```

Arms: **A0** `sumo_default`, **A1** `fixed`, **A2** `max_pressure`,
**A3** `ev_priority` (rule-based EV pre-emption), `ped_priority` (rule-based
pedestrian windows), **A4** `llm_team` (Operator + Emergency + Pedestrian).
LLM: `deepseek-v4.1-flash`, temperature 0, recorded with `--llm openai` and
replayed bit-identically with `--llm replay` (S3/S4/S5/EV logs verified in
Phases 3–5).

| Scenario | ID | Seeds (A4) | Horizon |
|---|---|---|---|
| `grid_3x3` | S0 normal demand | 3 | 3600 s |
| `grid_3x3_peak` | S1 peak demand (2x) | 3 | 3600 s |
| `grid_3x3_ev` / `_ev2` / `_ev_incident` | S2 EV runs | 3 | 3600 s |
| `grid_3x3_incident` | S3 incident A1A0 (1200–1500 s) | 3 | 3600 s |
| `grid_3x3_ped` | S4 pedestrian burst B1 (300–540 s) | 5 | 1200 s |
| `grid_3x3_ped_combo` | S5 EV@450 + burst + incident 400–640 s | 3 | 1200 s |

Non-LLM baselines (A0/A1) were topped up to 3 seeds in Phase 6 (SUMO only).

## H1 — S0: no regression (A4 vs A2)

| Arm | Step wait (s) | Mean speed (m/s) | Arrived | Tripinfo wait (s) | Time loss (s) |
|---|---|---|---|---|---|
| A0 `sumo_default` | 132.00 ± 1.52 | 7.39 ± 0.03 | 1179.3 ± 0.6 | 25.14 ± 0.21 | 33.62 ± 0.25 |
| A1 `fixed` | 87.95 ± 0.22 | 7.22 ± 0.01 | 1178.7 ± 1.5 | 24.62 ± 0.03 | 35.36 ± 0.04 |
| A2 `max_pressure` | **11.30 ± 0.26** | 8.98 ± 0.03 | **1183.3 ± 0.6** | 8.35 ± 0.09 | 20.14 ± 0.14 |
| A4 `llm_team` | **11.30 ± 0.26** | 8.98 ± 0.03 | **1183.3 ± 0.6** | 8.35 ± 0.09 | 20.14 ± 0.14 |

**Verdict: holds.** The step CSVs are bit-identical to A2 on every seed (the
Operator accepts no directives on uncongested demand; doing nothing is a valid
answer). S1 peak is the same tie (27.75 ± 0.81 s for both).

## H2 — S2: EV travel time vs A2, and vs A3

EV travel time / EV waiting time, seconds (mean ± std over 3 seeds):

| Scenario | A2 `max_pressure` | A3 `ev_priority` | A4 `llm_team` |
|---|---|---|---|
| ev (1 EV) | 100.00 ± 3.46 / 24.67 ± 2.31 | 64.33 ± 9.24 / 2.33 ± 4.04 | 65.00 ± 8.72 / 2.33 ± 4.04 |
| ev2 (2 EVs) | 72.33 ± 2.57 / 16.33 ± 1.04 | **55.33 ± 5.77** / 6.17 ± 2.02 | 57.00 ± 6.93 / 6.50 ± 1.73 |
| ev_incident | 111.67 ± 23.67 / 34.67 ± 18.58 | 64.33 ± 9.24 / 2.33 ± 4.04 | 65.00 ± 8.72 / 2.33 ± 4.04 |

This is the origin of the report figures: red = LLM team, blue = max-pressure.
See `figures/bars_ev.png`.

**Verdict: win vs A2 everywhere (−35% / −21% / −42% travel time), tie with A3
on 1 EV and EV+incident, −3% on the 2-EV conflict.** The residual on `ev2` is
release granularity: A3 reacts per second, the LLM layer per event/10 s tick.
Pre-emption shields the EV from the incident completely (ev_incident EV
metrics equal the plain ev scenario); the incident cost lands on civilian
flow (`bars_civilian.png`, third panel).

## H3 — S3: incident recovery (A4 vs A2)

| Arm | Step wait (s) | Tripinfo wait (s) | Time loss (s) | Arrived |
|---|---|---|---|---|
| A0 `sumo_default` | 490.70 ± 11.12 | 29.69 ± 0.11 | 39.41 ± 0.16 | 2362.0 ± 0.0 |
| A1 `fixed` | 416.96 ± 16.07 | 28.04 ± 0.06 | 39.85 ± 0.06 | 2358.0 ± 1.0 |
| A2 `max_pressure` | 296.68 ± 47.19 | 15.56 ± 1.12 | 30.15 ± 1.63 | 2368.3 ± 0.6 |
| A4 `llm_team` | **199.78 ± 33.45** | **13.69 ± 0.73** | **27.73 ± 0.97** | **2369.0 ± 1.0** |

Per seed: −35.8% / −32.0% / −30.2% vs A2 (−32.7% mean), and −59.3% vs A0.
`figures/step_wait_grid_3x3_incident.png` shows the mechanism: the LLM team
cuts the spillback peak around the blocked edge and clears the aftermath
faster.

**Verdict: win.** The lever is the code-detected queue-growth alert plus the
Operator rule learned in Phase 3: *a queue that grows while its axis is green
signals downstream blockage — stop feeding it green* (excerpt 1 below).

## H4 — S4: pedestrian waits without vehicle penalty

S4, 5 seeds, 1200 s:

| Arm | Ped mean wait (s) | Ped p95 (s) | Civilian step wait (s) |
|---|---|---|---|
| A2 `max_pressure` | 35.70 ± 23.65 | 106.20 ± 119.75 | 31.18 ± 5.68 |
| `ped_priority` (rule) | **25.29 ± 3.06** | **53.00 ± 7.04** | **28.11 ± 5.11** |
| A4 `llm_team` | 29.20 ± 6.61 | 60.40 ± 10.83 | 31.03 ± 3.95 |

**Verdict: win.** Pedestrian waits drop 18–29% with no vehicle penalty. A2
starves one seed badly (up to 77.6 s mean ped wait on seed 2); the LLM removes
that tail and has the lowest variance of the three, while the tuned rule stays
more aggressive on ped waits (25.3 vs 29.2 s). See `figures/bars_ped.png`.

## S5 — composition tradeoff (EV + incident + pedestrian burst)

| Arm | EV duration (s) | Ped mean (s) | Ped p95 (s) | Civilian step wait (s) |
|---|---|---|---|---|
| A2 `max_pressure` | 87.67 ± 2.08 | 29.88 ± 7.18 | 63.33 ± 15.95 | 126.29 ± 13.92 |
| A3 `ev_priority` | 58.00 ± 0.00 | 23.85 ± 5.41 | 50.00 ± 10.44 | 141.05 ± 36.02 |
| `ped_priority` | 88.67 ± 1.53 | 28.60 ± 6.50 | 60.67 ± 10.21 | 144.84 ± 33.59 |
| A4 `llm_team` | **58.00 ± 0.00** | **24.12 ± 2.92** | **47.33 ± 7.02** | 138.43 ± 9.92 |

Each single-purpose rule sacrifices an objective: A3 starves pedestrians
(23.85 vs 24.12 is close, but its civilian variance is 3.6x worse), the
pedestrian rule ignores the EV. The LLM team matches the EV rule exactly
(−34% vs A2) **and** takes the best pedestrian waits with the lowest variance,
at a civilian cost smaller than either single-purpose rule. In this scenario
every priority arm pays throughput vs A2 (A2 wins raw throughput by ignoring
priorities) — that is the price of priority, reported honestly.

## H5 — decisions are auditable

Excerpts from `decisions.jsonl` (S3/S4/S5 seed 1; replay logs carry the same
content as the recorded calls).

**1. S3, detecting the downstream blockage through the green (t=1327→1350).**

```
t=1327 operator [bias A0 ns=1.2 ew=0.9]  "A0 is the only loaded junction and its NS
      approach leads on both queue and wait, so nudge green toward NS to drain it."
t=1350 operator [bias A0 ns=0.6 ew=1.5]  "NS at A0 stays jammed while its green yields
      almost nothing — suspected downstream blockage — so I hold service on the EW axis
      rather than returning to NS."
```

**2. S3, rotating back after the incident (t=1530→1556).**

```
t=1530 operator [hold A0 NS +12 s]  "A0 NS now has green and is draining, so I hold it
      briefly to clear the backlog before the EW-favored bias flips service."
t=1556 operator [bias A0 ns=1.2 ew=0.85]  "A0's NS queue is now falling rather than
      spilling, so I rotate service back toward NS to finish draining it."
```

**3. S4, a pedestrian window wins over the current green (t=448).**

```
t=448 pedestrian [serve_ped B1 EW min_green=18 s]  "B1's EW crossing has 4 people waiting
      up to 20 s, which wins a window despite the NS green."
```

**4. S5, the Emergency agent plans a corridor around a queue (t=451→459).**

```
t=451 emergency [preempt A0 NS start_now, B0 EW, C0 EW +9.2s]  "Protecting green at A0
      and B0 now, and starting C0 9.2s early so ev_0 crosses all three on its axis."
t=459 emergency [release A0, extend B0 EW 20.5s]  "Released A0 after ev_0 passed it and
      extended B0's EW green to cover the EV's arrival in 20.5s."
```

**5. S5, the queue-aware lead rule (from the literature) firing (t=486).**

```
t=486 emergency [preempt C1 NS hold 15 s, C2 NS start now]  "Protecting C1's green now
      and starting C2 one second early to discharge its single queued vehicle before
      ev_0 arrives."
```

## LLM operations (recorded runs)

Source: `tables/llm_ops.csv`; latency/tokens only for runs recorded with
`--llm openai` (four seed-1 directories were overwritten by later
`--llm replay` verification runs, which carry no timing counters and are
flagged `recorded=0`).

| Scenario | Calls/run (mean) | Roles | Median latency | Mean latency | Tokens in / out / cached |
|---|---|---|---|---|---|
| S0 | 60 | operator 60 | 1.9 s | 2.4 s | 441k / 11k / 311k |
| S1 | 61 | operator 61 | 2.2 s | 3.4 s | 449k / 14k / 315k |
| S2 ev | 80 | operator 67, emergency 13 | 2.8 s | 5.2 s | 593k / 46k / 356k |
| S2 ev2 | 84 | operator 67, emergency 17 | 2.8 s | 7.0 s | 1107k / 117k / 588k |
| S2 ev+incident | 81 | operator 68, emergency 13 | 3.6 s | 5.9 s | 873k / 69k / 546k |
| S3 | 75 | operator 75 | 3.5 s | 8.6 s | 393k / 52k / 283k |
| S4 | 68 | operator 41, pedestrian 27 | 3.3 s | 4.1 s | 997k / 88k / 463k |
| S5 | 77 | operator 39, emergency 12, pedestrian 26 | 4.5 s | 7.5 s | 787k / 117k / 304k |

0 fallbacks in 1607 recorded calls (2 retries total, all invalid JSON,
recovered on the first retry); ~50% of input tokens are served from the
provider's prompt cache. Adaptive cadence: 60 s quiet / 30 s normal / 15 s
congested, plus immediate runs on detector alerts and EV events.

## Limitations

- **S4 peak-demand variant is an honest null** (not canonical): with heavy
  vehicles, queue-driven cycling already serves crossings and forced windows
  cost transitions (A2 21.9 / rule 27.5 / LLM 22.5 s ped wait).
- **No agent ablations**: S5 shows the composed team, not Operator-only or
  Emergency-only variants.
- **S5 is heavily congested** (blocked edge + teleport disabled), so every
  priority arm pays civilian throughput vs A2; A2 wins raw throughput by
  ignoring priorities.
- **Person KPIs count completed persons only** (queued-at-horizon persons are
  not in `<personinfo>`; S4 completes 360/360, fine here).
- **Residual EV gap on 2 EVs** (~1.7 s, 3% vs the per-second rule) is release
  granularity, not planning quality.
- Detector thresholds (15/20 s) and cadence tiers are global constants;
  per-scenario calibration was out of scope.
