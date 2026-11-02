---
name: Live Optimize · Predict · Roam tabs
overview: "Four phases to finish the live-map modes: put every panel on the run's own clock and zone, remove the remaining demo constants (Sector 6, 52% load, M-204, Monaco coordinates), compute the forecast and per-junction series once on the backend, and make Optimize's Apply actually change something through a validated signal endpoint."
todos:
  - id: p0-clock
    content: "Phase 0: panels follow the run's clock and network (no scrub-minute / Sector 6 mix); expose enough history through one endpoint"
    status: completed
  - id: p0-idle
    content: "Phase 0: idle/cold-start states instead of the 52% / 46% demo constants and mock zones"
    status: completed
  - id: p1-junctions
    content: "Phase 1: per-junction measured speed/queue series for Optimize ranking and Roam segments"
    status: completed
  - id: p1-apply
    content: "Phase 1: POST /api/simulation/signal (validated split change) + Optimize Apply wired to it"
    status: completed
  - id: p1-signal-editor
    content: "Phase 1: Signal timing sliders read live splits and apply through the same endpoint"
    status: completed
  - id: p2-forecast
    content: "Phase 2: backend GET /api/simulation/forecast (EWMA + trend, horizon, confidence, basis) consumed by Predict"
    status: completed
  - id: p2-inputs
    content: "Phase 2: what-if chips only when the backend supports them — otherwise the card is hidden, not empty"
    status: completed
  - id: p3-roam
    content: "Phase 3: Roam segments/follow/fly-through from the run (real vehicle ids, scenario centre, measured per-segment speed)"
    status: completed
  - id: p3-verify
    content: "Checks: pure-function tests for forecast/junction aggregation, API tests for signal validation, pytest + build + a live run pass on all three tabs"
    status: completed
isProject: false
---

# Live Optimize · Predict · Roam

**Context.** The three tabs already have a live bridge: `frontend/src/shell/modes/live.js`
is preferred by the `modeData` adapter whenever `isLive()` is true, and it derives
recommendations from `metrics.junctions`, the forecast from `trend.throughputPerMin`, the
roam strip from `metrics`, and the signal editor from `state.signals`. What is left is the
seam between that bridge and the mock model underneath it: the panels still run on a
24-hour scrub clock and Monaco "sectors", several constants are still demo values, the
forecast is a single-scalar extrapolation computed in the browser, and Optimize's Apply
changes nothing outside its own `Set`.

**Constraints (repo rules).** `api/` stays a thin adapter; simulation and metrics stay in
`src/cotraffic/`. Every displayed number is measured or explicitly labelled a forecast.
A panel with no run shows an explicit empty state — never the old demo values. The
dashboard contract stays camelCase JSON.

---

## What is already live (keep, don't rebuild)

| Surface | Source today |
|---|---|
| Optimize rows | `liveRecommendations()` — ranked from `metrics.junctions[i].pressure/queue` |
| Optimize gauges | `liveLoad()` / `liveEfficiency()` from `metrics.queueShare`, preview projections |
| Predict chart | `liveForecast()` — slope over `trend.throughputPerMin`, confidence from sample count |
| Roam strip | `liveRoamStats()` — speed/vehicles/incidents from `metrics` |
| Signal editor rows | `liveSignalTiming()` — first 6 TLS `duration`s from `state.signals` |
| Efficiency delta | first sample of `getLiveHistory()` |

The mock provider in `modes/data.js` stays only as the cold-start/demo source; it must stop
leaking into a running session.

---

## Gaps

| # | Where | Problem |
|---|---|---|
| 1 | `index.js:1052` + `:1216` | `state.minute` comes from the timeline scrubber (0–1439), while the numbers come from the live snapshot. Headers read `live · 03:12` with data from the run's own clock. |
| 2 | `index.js:293,353,455,947`, `data.js:22` | "Sector 6" and `sec-6` are mock zones; a run on `sf_mission_2x2` shows a Monaco sector name. |
| 3 | `index.js:897-898` | `LIVE_LOAD = 52`, `LIVE_EFFICIENCY = 46` are still the gauge fallback, and `:260` feeds them into the map haze. |
| 4 | `index.js:1065-1120` | Apply / Preview / Dismiss only mutate `state.applied` and toast; nothing reaches the run, and dismissals are never scoped to a run. |
| 5 | `index.js:563-587, 1131-1136` | Signal sliders change the label only; cycle text is not derived from the live plan when idle. |
| 6 | `live.js:147-181` | `liveForecast` maps history by slot index (not by time), multiplies a per-minute rate by 30 without saying why, and derives "expected delay" from a unitless formula. `inputs: []` empties Predict's Scenario inputs card. |
| 7 | `live.js:116-146` | Roam segment speed is `avgSpeed − queue·0.8` presented as per-segment km/h; density is `queueShare` shown as %. |
| 8 | `index.js:1162, 1169, 1176` | Follow says "vehicle M-204"; fly-through/recenter hardcode Monaco `[7.4245, 43.7335]` on every scenario. |
| 9 | snapshot | `trend` is capped at 60 samples (~5 min); `/api/simulation/history` keeps 900 but no panel fetches it, and there is no per-junction series at all. |

---

## Phase 0 — One clock, one place, honest idle

| File | Change |
|---|---|
| `modes/index.js` | Derive the panel "now" from the run: `isLive() ? simulationTime/60 : state.minute`. Scrub only while paused, and label it (`scrub · 03:12`). `setMinute` keeps driving the demo/mock path. |
| `modes/index.js` | Replace the three `Sector 6` subtitles and `sec-6` default with the run's network label (`sf_mission_2x2` → "SF Mission 2×2") and the selected junction/TLS; zone picker from `metrics.junctions` when live. |
| `modes/index.js` | Delete `LIVE_LOAD` / `LIVE_EFFICIENCY`; `null` gauges render `—` and the haze layer falls back to a neutral 0.5, not 52/46. |
| `modes/live.js` | Clear `applied` / `dismissed` / `previewId` when `runId` changes, so a restart cannot show stale "Applied" rows. |
| `app.js` | Fetch `/api/simulation/history` once per run (and on restart) and seed `setLiveState(state, samples)` with the 900-sample history instead of the 60-sample slice. |
| `api/simulation.py` | Include `runId` in the snapshot (it already resets telemetry on `start`) so the UI can scope per-run state. |

**Acceptance.** With no run, Optimize/Predict/Roam show empty states; with a run, every
header clock equals `state.clock`, and no "Sector 6" / 52% / 46% text can appear.

---

## Phase 1 — Optimize acts on the corridor

| File | Change |
|---|---|
| `api/simulation.py` | Extend `metrics.junctions[i]` with `avgSpeedKmh`, `queueShare`, and keep the per-TLS ring buffer (`{t, queue, pressure}`) so a junction trend exists. |
| `api/simulation.py` | `set_signal_split(tls, phase, green_s)` — validate TLS id against the network, clamp green to the plan's min/max, apply through `conn.trafficlight.setPhaseDuration`, publish a `signalChange` event with the operator as source. |
| `api/routes/simulation.py` | `POST /api/simulation/signal {junction, phase, green}` → 409 when idle, 422 for unknown TLS/out-of-range green. |
| `modes/live.js` | Ranking uses the measured `queue`/`pressure`; each recommendation carries the exact `junction` + `phase` it would change, so Apply has a target. |
| `modes/index.js` | Apply calls the endpoint, then re-reads the returned snapshot; failures show the backend reason and revert the row. Preview stays a projection, explicitly labelled "modelled". Dismiss is per run and resets on restart. |
| `modes/index.js` | Signal editor: sliders initialise from the live plan (`setPhaseDuration` values), "Apply plan" sends each changed row, and the cycle label is the sum of the live durations. |

**Acceptance.** Applying a row changes the TLS in the running simulation (verified via the
next snapshot's `signals[i].duration` and a `signalChange` event), a refused change leaves
the row unapplied and shows why, and the editor never displays a split the run is not using.

---

## Phase 2 — Predict with a real forecast

| File | Change |
|---|---|
| `api/routes/simulation.py` | `GET /api/simulation/forecast?horizon=5|10|15` → `{ basis, samples, confidence, points: [{t, queue, throughputPerMin, avgSpeedKmh}], method }`, computed from the session's ring buffer (EWMA + linear slope, clamped); 409 when idle. |
| `src/cotraffic/forecast.py` (new) | Pure functions: `ewma(series, alpha)`, `linear_trend(points)`, `project(samples, horizon)`, `confidence(samples, spread)` — importable and unit-tested without SUMO. |
| `modes/live.js` | `liveForecast()` becomes a thin mapper over the endpoint payload (no arithmetic): the chart draws measured points up to now and the projected points after, with a visible split marker. |
| `modes/index.js` | Predict header shows horizon + method + sample count; "Hours at risk" ranks by projected queue, not by re-scaled volume. Scenario inputs render only if the backend returns supported inputs; otherwise the card is hidden entirely. |

**Acceptance.** Forecast points for the first horizon equal what the run then measures
within a stated tolerance; every number carries its basis (`n samples, EWMA α`); no
`value × 30` conversions remain in the browser.

---

## Phase 3 — Roam is the run, not Monaco

| File | Change |
|---|---|
| `api/simulation.py` | Per-junction `avgSpeedKmh` from the vehicles on the TLS's controlled lanes (already collected for `junctions`), so segment speed is measured rather than derived from queue. |
| `modes/live.js` | `liveRoamStats().segments` maps junctions → `{id, label, speed, state}` with the measured speed and the same `flow|dense|jam` thresholds as the map layer. |
| `modes/index.js` | Follow-vehicle picks a real id from `state.vehicles` (emergency first, else the slowest), keeps `followMode` in sync with its presence, and clears when the vehicle leaves. Fly-through/recenter use `SCENARIOS[scenario].liveCenter/liveZoom` from `app.js`. |
| `modes/index.js` | Inspector rows show junction id, lanes, queue, pressure, measured speed; no mock segment names in live mode. |

**Acceptance.** Clicking Follow names a vehicle that exists in the current snapshot and the
camera keeps it in view; recenter lands on the active scenario in every network; segment
speeds match the per-junction values published by the API.

---

## Checks

- `pytest tests/test_simulation_telemetry.py tests/test_simulation_api.py` (new/extended):
  forecast pure functions, junction aggregation, `POST /api/simulation/signal` validation
  (idle 409, unknown TLS 422, out-of-range 422, valid 200 + event).
- `npm run build`.
- Manual pass on `grid-2x2` and `grid-3x3`: start a run, open each tab, pause, scrub,
  apply a signal change, restart, confirm no demo constants and no stale per-run state.

---

## Out of scope

- Editing road geometry, adding lanes or new networks (network work stays in `configs/networks`).
- Real dispatch/CTECC and camera/V2X feeds — no data source exists; those panels stay as they are.
- Turning the demo day-profile into a calibrated demand model; Predict forecasts the run, not a city.
- Reroute/ramp-meter actions that would need new demand or routing control in the simulator.
