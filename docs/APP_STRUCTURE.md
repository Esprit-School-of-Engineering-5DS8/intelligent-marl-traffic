# APP_STRUCTURE.md — Root of all tabs and sub-tabs

This is the single source of truth for the navigation tree: every top-level tab, every sub-tab, what it contains, where its data comes from, and its implementation status. If you add, rename, or remove any tab, update this file.

## Navigation tree (target state)

```
Sidebar
├── Dashboard                     Overview · Activity log · Settings (topbar tabs)
├── Benchmark                     (was "Labs")
│   ├── Runs                      run registry — every training/eval as a run row (MLflow-style)
│   ├── Compare                   2–8 runs side-by-side: metric deltas, hyper-parameter scatter, curve overlay
│   ├── Models                    model registry — named models, version lineage, promote / benchmark actions
│   └── Train                     (was "Warm-up & Jobs") launch + monitor training jobs; a completed job = a Run
├── Live Map                      3D/Mapbox environment on the selected network
│   ├── Events                    incident / emergency / pedestrian scenario overlay
│   ├── Optimize                  live signal control (RL / baseline controller swap)
│   ├── Predict                   forecasting overlay
│   └── Roam                      free camera inspection of junctions, signals, vehicles
├── Message
├── Roles & Permissions
│   ├── Roles
│   └── Permissions
└── Settings
```

## Current tree vs target — what changes

| Area | Now | Target | Change |
|---|---|---|---|
| Sidebar group 2 name | Old "Labs" | **Benchmark** | ✅ applied |
| Benchmark sub-tabs | Runs · Compare · Models · Warm-up & Jobs | Runs · Compare · Models · Train | ✅ applied |
| Live sub-tabs | Events · Optimize · Predict · Roam | unchanged | — |
| Everything else | — | unchanged | — |

Implementation surface for the two renames is small:
- `frontend/index.html` — nav label (`Labs` → `Benchmark`, `Warm-up &amp; Jobs` → `Train`).
- `frontend/src/shell/app.js` — `data-benchmark-tab="training"` shown tab title stays internal; only user-visible strings change.
- `frontend/src/shell/benchmark-mount.jsx` — tab title strings.

## Sub-tab ownership and data

| Tab | Sub-tab | Contents | Data |
|---|---|---|---|
| Benchmark | Runs | MLflow-style run table: one row per evaluation cell, models as named rows (scripted baselines ft/act/mp/ev_rule/ped_rule_mp, LLM, `generalist*` RL); flat metrics columns (delay, throughput, CO₂, EV, pedestrian); search/filter; compare-checkbox mode | `frontend/public/data/runs.json` (regenerate: `python scripts/export_dashboard_data.py`) |
| Benchmark | Compare | delta table with paired stats + Holm significance, hyper-parameter-vs-outcome scatter, per-metric curve overlay | `runs.json` + `comparisons.json` |
| Benchmark | Models | named-model registry, lineage, promote / launch-eval actions | `frontend/public/data/models.json` |
| Benchmark | Train | launch PPO training (`python -m cotraffic train --recipe generalist …`), job history, checkpoint status; completed job auto-registers a Run | training exports under `results/training/` |
| Live Map | Events / Optimize / Predict / Roam | 3D env rendering the SUMO net (road layout straight from the converted net), Mapbox raster tiles projected underneath, vehicles + traffic lights as the only dynamic props | live SUMO session (`src/cotraffic/envs`, lon/lat from net offsets) |

## Networks in scope

San Francisco only until further notice: `sf_mission_2x2` and `sf_mission_3x3` (Mission/Howard × 6th–8th arterials, built by `scripts/explore/build_sf_grids.py` from OSM + netconvert). Grid3×3/Monaco/Tunis stay available as data, but the Live Map 3D env and scenario menu lead with the SF corridors.

## Conventions

- Sub-tab keys are machine ids (`runs|compare|models|training`), referenced via `data-benchmark-tab`, persisted in the URL hash when deep-linkable.
- Nothing outside these tabs may register nav entries without updating this file.
