# Benchmark redesign — live lab instead of a static report

> Replaces the four static subtabs (Vue d'ensemble, Agents RL, Carte en direct, Analyse
> comparative) whose data comes from a 2026-10-16 export of networks we no longer run.
> Companion to [ARCHITECTURE.md](ARCHITECTURE.md) §7 and [DESIGN_TOKENS.md](DESIGN_TOKENS.md).

## 1. What is wrong today (measured, not assumed)

| Fact | Evidence |
| --- | --- |
| The benchmark serves a frozen export | `frontend/public/data/meta.json` → `generatedAt: 2026-10-16T08:42:57`, 24 cells, 46 MB of JSON |
| That export covers networks that no longer exist | it lists `grid4x4`, `grid8x8`, `real_district`; all three (plus `real_district_ped`) were deleted, the catalogue is `grid2x2`, `grid3x3`, `monaco`, `tunis` |
| It names controllers the registry cannot build | export lists `coop_forecast`, `coop_full_ev1/ev4`, `ind_ent`, `ind_pressure`, `ind_queue`; `REGISTRY` has `ft, act, mp, ev_rule, ev_rule_mp, ped_rule_mp, ind, coop, coop_eco, coop_eco05, coop_full, dqn, llm` |
| Training has no API at all | the only path is `python -m cotraffic train` |
| Only a few agent/network pairs have checkpoints | `coop`: grid2x2, grid3x3, tunis · `ind`, `dqn`, `coop_full`: tunis · `coop_eco`, `coop_eco05`, `coop_forecast`, `coop_full_ev1/ev4`: none · `monaco`: none for any learned agent |
| Monaco used to be a hand-built OSM approximation | the earlier `netconvert` build (4500 junctions, guessed signals) aborted SSM episodes; it is replaced by the vendored MoSTScenario net, where `run_episode(..., ssm=True)` completes |

Two things that were true before this cleanup are now fixed, and should stay fixed:

- `/api/runs` validated "live" runs against `public/data/meta.json`; it now validates against
  `api.policy.METHODS` / `NETWORKS`, i.e. the controller registry.
- `/api/simulation` accepted only `grid-2x2` / `grid-3x3` and projected every network into an
  Austin lat/lon box. It now serves all four scenarios, drawing the OSM networks in their own
  bbox (`monaco` 7.4080–7.4610 E, `tunis` 10.1760–10.1920 E).

## 2. The four scenarios, as they really are

Full evaluation episode (warm-up + measured window + cool-down, SSM on), controller `mp`,
medium demand, seed 3, measured on this machine (Python 3.14, pure-python TraCI, no libsumo):

| Network | Shape | TLS | Wall time | Verdict |
| --- | --- | --- | --- | --- |
| `grid2x2` | 44 junctions | 4 | 52 s | debug / demo |
| `grid3x3` | 93 junctions | 9 | 136 s | main small benchmark |
| `tunis` | 99 junctions, 372 KB net | 8 | 125 s | real-world case, live-able |
| `monaco` | 3523 junctions, 18 837 edges, 14 MB (MoSTScenario) | 12 | 68 s quick with SSM | real-world case, live-able; peak demand 1300 veh/h calibrated to MoST |

`tunis` is the central Tunis arterial corridor (Avenue Mohamed V → Bourguiba → Rue Jean
Jaurès, 1.4 km × 1.3 km) rebuilt from a saved 383 KB OSM extract, so it rebuilds offline in
seconds. The old 1.1 GB Grand-Tunis build (333k junctions, 452 TLS) contradicted its own
config and was deleted.

Monaco's demand now comes from the scenario too: MoST's own route files peak at
648 commercial + 303 special + 240 highway + 96 bus = **1287 veh/h** arrivals in the 08:00 hour,
so `peak_vehicles_per_hour` is 1300 (medium 910, low 585) instead of the old 3800 placeholder,
which was above the network's ~1450 veh/h capacity and produced a growing queue all episode.
`cotraffic calibrate-demand --net monaco` (fixed-time, seed 5001) confirms the point sits at
"clear congestion without gridlock": 1300 veh/h → 15 s mean waiting, p95 68 s, queue 6.3,
throughput 1308, zero teleports, zero never-inserted vehicles.

`monaco` is no longer built by us: it vendors the published **MoSTScenario** network
([lcodeca/MoSTScenario](https://github.com/lcodeca/MoSTScenario), GPLv3, Codeca & Härri,
SUMO Conference 2018) at `sumo_files/monaco/monaco.net.xml`. `configs/networks/monaco.yaml`
declares `kind: prebuilt`, so `cotraffic networks monaco --force` copies
`scenario/in/most.net.xml` from a checkout at `sumo_files/_most` instead of running
`netconvert`, and says how to clone it when the checkout is absent. Two consequences worth
knowing: the fixed-shape observation padding must allow the net's largest signal plan
(6–10 phases per junction, so `max_phases: 12`), and the route cache key now includes the
`.net.xml` identity — swapping a network while keeping the config identical was reusing
routes whose edge ids no longer existed.

## 3. Target information architecture

Benchmark stays one page with four subtabs, but every tab is a *tool* with a job, not a chart
of the past:

```
Benchmark
├── Scénarios        "what can I run, and what is trained for it?"
├── Entraînement     "train an agent here, watch it learn"
├── Comparaison      "run A vs B now, get a paired verdict"
└── Carte en direct  "watch the chosen controller drive the network"
```

### 3.1 Scénarios (replaces Vue d'ensemble)

A board of scenario cards, one per network — 2×2, 3×3, Monaco, Tunis (disabled + reason).
Each card shows:

- network facts: signals, edges, agents, measured wall time for a 3-minute run;
- a controller strip: `FT · ACT · MP · EV-RULE · IND · COOP · COOP-FULL · DQN · LLM`, each a
  chip with a checkpoint badge (trained / missing) resolved from the filesystem;
- one primary action **Run 3 min** (opens the live tab) and one secondary **Train here**.

No historical tables. The empty state is the call to action: "no checkpoint for COOP on 3×3 —
train one in ~2 min".

### 3.2 Entraînement (replaces Agents RL)

A job queue, not a curve gallery:

- form: agent variant (from `configs/agents`, with a one-line "what changes" note), network,
  seeds, budget preset — `3k quick (~2 min)`, `50k (~35 min)`, `500k full (~5.5 h)`;
- each job card streams live: steps/s, reward/episode sparkline, stopped vehicles, ETA, status
  (`queued → running → done | failed | cancelled`), and the checkpoint path it produced;
- finished job → **Promote**: sets `PUT /api/policy` and makes the controller available in the
  scenario strip and the comparison picker.

Budget arithmetic behind the presets: one agent step every 5 s of sim; 9 agents × 36 decisions
= 324 steps per 180 s episode in 13 s → ≈ 25 steps/s on this machine, so 500k steps ≈ 5.5 h,
3k ≈ 2 min. Show that estimate on the button; never start a full run implicitly.

### 3.3 Comparaison (replaces Analyse comparative)

Pick a network + scenario + seed, then 2–4 controllers; the backend runs the episodes now and
returns paired deltas with bootstrap CI and significance, using the same code path as
`cotraffic evaluate` (no separate implementation). Layout: one delta table, one dot plot per
metric, one sentence verdict ("COOP beats FT by 36 % waiting time, 15 paired runs, significant").

### 3.4 Carte en direct (keeps its job)

Extend beyond the grids: the map must draw the network from its own coordinates. Today
`api/simulation.py` projects every network into `GEO_BOUNDS` around East Austin, which is why
the 2×2 grid appears in Texas — Monaco would be drawn there too. Replace the fixed bounds with
each network's real bbox (from the `.net.xml`), or render raw x/y on a canvas with the network
outline (no basemap) for the grids.

## 4. Components to build

| Component | Purpose |
| --- | --- |
| `ScenarioCard` | network facts, controller strip, run/train actions |
| `ControllerChip` | method label + colour + `trained`/`missing` badge (from `/api/catalog`) |
| `JobCard` + `JobQueue` | training job: progress rail, sparkline, ETA, cancel, promote |
| `CostEstimate` | "≈ 2 min / ≈ 5.5 h" on any action that starts work |
| `DeltaTable` + `DotPlot` | comparison results with CI and significance |
| `EmptyStateCTA` | explains the missing thing and offers the action that creates it |
| `Sparkline` | live reward / stopped vehicles, replaces historical curves |
| `StatusPill` | queued / running / done / failed / cancelled, one vocabulary everywhere |

Design rules: KEMETRA light (green `#5f9c2b` accent, white glass cards, 0 radius) from
[DESIGN_TOKENS.md](DESIGN_TOKENS.md); the live-map canvas remains the only dark surface;
`.select-control` / `.input-control` for every control so no OS widgets leak in.

## 5. Backend work

| Endpoint | Contract |
| --- | --- |
| `GET /api/catalog` | networks (real bbox, agent count, measured seconds/3 min), scenarios per network, agent configs, per-controller checkpoint availability, runnable/disabled + reason |
| `POST /api/train` | `{agent, network, seeds, timesteps}` → job id; refuses >1 concurrent training and unknown variants |
| `GET /api/jobs`, `GET /api/jobs/{id}` | state, metrics ring buffer, checkpoint path, log tail |
| `SSE /api/jobs/{id}/events` | progress frames from an SB3 callback (step, reward, stopped vehicles, eta) |
| `POST /api/compare` | `{network, scenario, demand, seed, methods[]}` → runs `run_episode` per method, returns rows + paired comparisons |
| `POST /api/runs` | extension: any network in the catalog, methods validated against the registry (not `meta.json`) |

Implementation notes:

- one `JobRunner` (single background worker, queue, JSON state in `results/jobs/`) shared by
  training and comparison so the CPU is never oversubscribed;
- training writes the normal `results/checkpoints/<agent>/<network>/seed<n>.zip` layout, so the
  CLI, the policy endpoint and the export script see the same artifacts;
- comparison reuses `cotraffic.evaluation.runner.run_episode` + the existing bootstrap stats;
- cancellation is cooperative (`JobRunner` sets an event, SB3 callback stops the loop).

## 6. Removing the static data

1. Delete `frontend/public/data/` (46 MB) and `scripts/export_dashboard_data.py`'s role as the
   UI's source. Keep the script only for the report figures, not for the app.
2. `dataSource: mock | live` collapses to live-only; mock becomes an explicit
   "no backend" state with the reason and a retry, never fabricated numbers.
3. Remove the `known_methods()` read of `meta.json` in `api/routes/runs.py`.
4. Remove the historical curves (`useTraining`, timeseries endpoints) with the tab they belong to.
5. Migration note for the docs: the only numbers the UI can show after this are ones it just
   produced or that a job wrote; the study report (`results/summary/REPORT_TABLES.md`) stays
   the place for publication figures.

## 7. Phases

| Phase | Scope | Effort | Done when |
| --- | --- | --- | --- |
| P0 | `/api/catalog`, delete `public/data`, live-only UI state (**registry validation and the four live scenarios are already done**) | 0.5 d | app runs with no exported JSON |
| P1 | Scénarios board + ControllerChip (live run for 2×2 / 3×3 / Monaco / Tunis already works) | 1 d | one click on a card starts the right network |
| P2 | `JobRunner` + `POST /api/train` + SSE + Entraînement tab | 1.5 d | a 3k-step job trains and promotes from the UI |
| P3 | `POST /api/compare` + Comparaison tab | 1 d | A vs B shows paired CI from a fresh run |
| P4 | Monaco SSM crash, per-network trained checkpoints, polish | 1–2 d | Monaco evaluates without `ssm=False`, and every card has at least one trained controller |

P0+P1 make the tab honest; P2 is what "everything live" actually means; P3 replaces the last
static table.

## 8. Risks and limits

| Risk | Mitigation |
| --- | --- |
| A 500k-step run occupies the machine for hours | presets + explicit estimate; only one training job at a time; cancel button |
| Training from the browser blocks the API | training runs in a worker process, the API stays responsive; SSE streams progress |
| Monaco's net is GPLv3 and 14 MB | not committed (`sumo_files/` is gitignored); the config documents the one-line clone, and the CLI reports it when the checkout is missing |
| Tunis memory/time | already solved: corridor build, 372 KB |
| Only `coop` is trained on 2×2/3×3 | the scenario strip shows it plainly; Entraînement is the fix, and `coop` remains the default |
| Promoted checkpoints change reported results | job records agent/network/seed/steps + git SHA in `results/jobs/<id>.json` |
| LLM controller costs money per call | keep `max_calls` from `configs/agents/llm.yaml`, show the fallback state in the chip |
