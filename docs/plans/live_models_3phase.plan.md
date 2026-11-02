---
name: Live models and data-driven live tabs
overview: "Three phases to make saved RL checkpoints (results/checkpoints, results/training, results/models) selectable and actually loaded by the live run, then to replace the live map's hardcoded demo values with the run's real telemetry across the four tabs (Events, Optimize, Predict, Roam)."
todos:
  - id: p1-api
    content: "Phase 1 backend: /api/models/live catalog + optional modelId on POST /api/simulation/start"
    status: completed
  - id: p1-ui
    content: "Phase 1 UI: selection stays in Settings → Models; the Compare tab records A/B from any saved checkpoint (live picker removed on request)"
    status: completed
  - id: p1-test
    content: "Phase 1 checks: catalog filtering, checkpoint validation, start-with-model round trip"
    status: completed
  - id: p2-metrics
    content: "Phase 2: richer per-step metrics (queues, speeds, arrivals, phase changes, inference ms)"
    status: completed
  - id: p2-history
    content: "Phase 2: history ring buffer + GET /api/simulation/history and trend in the WS payload"
    status: completed
  - id: p2-events
    content: "Phase 2: enriched live events (signal, controller/model, incidents) with detail payloads"
    status: completed
  - id: p3-events
    content: "Phase 3: Events tab renders the live feed + event detail, no static accident copy"
    status: completed
  - id: p3-optimize
    content: "Phase 3: Optimize tab shows active model, per-junction pressure/queue, phase-change log"
    status: completed
  - id: p3-predict
    content: "Phase 3: Predict tab forecasts from history (measured vs forecast clearly separated)"
    status: completed
  - id: p3-roam
    content: "Phase 3: Roam tab is map-first with a live status strip from the same state"
  - id: p3-verify
    content: "Checks run: pytest 23 passed, npm build OK; a SUMO end-to-end pass still needs trained checkpoints"
    status: pending
isProject: false
---

# Live models, live dashboard — 3 phases

**Context.** Training already writes weights that the dashboard can list and validate
(`api/routes/model_catalog.py`, `api/policy.py`) and the live run already honours the
active policy (`api/simulation.py` → `make_controller`). What is missing is a way to
*pick* those weights from the live screen, and live telemetry behind the four live tabs:
`frontend/index.html` + `frontend/src/shell/app.js` still show static incident text,
`2.4 km` queues, `+18 min` delay, `12.5k` volume, and the four tabs only swap a
`data-live-tab` attribute and a CSS class.

**Constraints (repo rules).** `api/` stays a thin adapter; simulation and metrics stay in
`src/cotraffic/`. The dashboard contract is camelCase JSON. Nothing may present a
hardcoded number as a measured one. Failures (no weights, no SUMO, no LLM key) must show
a reason, not a silent downgrade.

---

## Phase 1 — Saved models are usable from the live Events tab

### 1.1 Backend

| File | Change |
|---|---|
| `api/routes/model_catalog.py` | Add `GET /api/models/live?scenario=grid-2x2` returning only checkpoints that can run on that scenario's network, each with `id`, `label`, `method`, `network`, `seed`, `timesteps`, `source`, `checkpoint`, `available`, `reason`. Reuse `_entry()`; add a `trainable`/`runnable` flag mirroring `policy.availability`. |
| `api/policy.py` | Export `SCENARIO_NETWORKS = {"grid-2x2": "sf_mission_2x2", "grid-3x3": "sf_mission_3x3", ...}` as the single scenario→network map (today duplicated inside `api/simulation.py`). Reuse it in `availability`, `update` and the new route. |
| `api/routes/simulation.py` | `SimulationRequest` gains optional `method: str` and `checkpoint: str`. `session.start()` resolves them through `policy.update()` **before** starting, so a request cannot run weights the policy layer would refuse. |
| `api/simulation.py` | `start()` accepts an explicit checkpoint; pass it to `policy.checkpoint_path(method, network, explicit)` and to `make_controller`. Include the resolved checkpoint basename in `state["policy"]` (already present as a path). |
| `api/README.md` | Document `/api/models/live` and the new `start` body fields. |

Rules:
- A checkpoint outside `results/checkpoints`, `results/training`, `results/models` is refused
  (existing `_validated_checkpoint`), as are weights trained for another network.
- Selecting a model persists it (`results/dashboard_policy.json`), so a reload or a restart
  keeps running the same weights.
- `checkpointSource` (`auto` vs `explicit`) is surfaced, so the UI can say “default seed1”
  vs “pinned weights”.

### 1.2 Frontend (vanilla live map)

| File | Change |
|---|---|
| `frontend/index.html` | In the live Events tab panel add `#liveModelPicker`: a `<select>` of models, a `Refresh` button, and a `#liveModelStatus` line (algorithm · seed · steps · source). |
| `frontend/src/shell/app.js` | `loadLiveModels(scenario)` fetches `/api/models/live?scenario=…`; `applyLiveModel(id)` calls `PUT /api/policy` then `POST /api/simulation/start` on the current scenario and calls `updateSimulationState`. Reuse the existing `simulationFetch`, `showToast`, `escapeModelText` helpers. Re-fetch when `sumo:scenariochange` fires. |
| `frontend/src/shell/app.js` | In `updateSimulationState`, render the active policy in the timeline header: label + checkpoint basename + `auto/explicit`, and disable the picker with the backend `reason` when unavailable. |
| `frontend/styles.css` | Styling for the picker consistent with the existing `live-panel` / `settings-select` look, including the disabled/empty state. |

Acceptance:
- Starting a live run with a saved model loads exactly those weights (the state's
  `policy.checkpoint` basename matches the picker).
- Switching model while running restarts the run on the same grid and keeps the tab.
- With no weights for the network, the picker is disabled and shows why.
- Reload keeps the last choice.

### 1.3 Checks
`tests/test_model_selection.py` additions: `/api/models/live` filters by scenario/network;
`POST /api/simulation/start` with a foreign-network checkpoint returns 422; with a valid
checkpoint it reaches `make_controller` (monkeypatched) with that exact path. Run
`pytest tests/test_model_selection.py tests/test_policy_api.py`.

---

## Phase 2 — Real telemetry behind the dashboard

### 2.1 Metrics (`api/simulation.py`)

Extend `_publish`'s `metrics` (keeping existing keys):
- `vehicles`, `pedestrians`, `arrived`, `departed`, `running`
- `queued` (speed < 0.1), `queueShare`
- `avgSpeedKmh`, `avgWaitingS`
- `throughputPerMin` (arrivals in the last 60 s of sim time)
- `signalPhaseChanges` (count since start), `controllerCalls`, `lastDecisionMs`
- `junctions`: per-TLS `{ id, pressure, queue, phase, state }` computed from the lanes
  already read for signals (reuse `signalLanePositions` lane ids; no new TraCI calls
  where avoidable).

All numbers must come from the connection/session, never from config. Where a value is
not measurable yet, omit the key rather than inventing one.

### 2.2 History (`api/simulation.py`, `api/routes/simulation.py`)

- Add a bounded ring buffer (`deque(maxlen≈900)`) of compact samples
  `{ t, clock, vehicles, queued, avgSpeedKmh, arrived, throughputPerMin }`, reset on `start`.
- `GET /api/simulation/history` → `{ runId, samples }`.
- Include the last 60 samples as `trend` in the snapshot so the WS (4 Hz) does not need a
  second request; `GET /state` keeps the same shape plus `trend`.

### 2.3 Events (`_publish_events`)

Keep the rising-edge keys already there (`emergency`, `bus`, `congestion`, `incident`,
`pedestrians`) and add:
- `signalChange` — per TLS phase change, with `detail: { tls, phase, state }`
- `controller` — active policy/model summary when the run starts, and on every
  degradation/fallback (`detail: { method, checkpoint, reason }`)
- `modelLoaded` / `modelError` — what weights were loaded, or why loading failed

Each event gets `detail` (object) and stays deduplicated by `_event_keys`, capped at 40
(keep the cap; the tabs read the newest first).

### 2.4 Checks
`tests/test_simulation_telemetry.py` (new): pure-function tests over a fake state —
rising-edge dedupe, metrics keys present, trend length/cap, junction aggregation. No SUMO
required. Also `curl /api/simulation/history` in the manual pass.

---

## Phase 3 — The four live tabs read that data

### 3.1 Structure

- `frontend/index.html`: give each tab a panel keyed by `data-live-panel="events|optimize|predict|roam"` inside `.live-map-overlay`; move the static zone/queue copy behind ids and make it placeholder-only (hidden once live values arrive).
- `frontend/src/shell/app.js`: add `renderEventsTab(state)`, `renderOptimizeTab(state)`, `renderPredictTab(state)`, `renderRoamTab(state)`; call the active one from `updateSimulationState` and on `sumo:livetabchange`. Keep the current `renderLiveEvents` feed as the Events list.
- `frontend/styles.css`: show/hide by `live-map-view[data-live-tab="…"] [data-live-panel]`, keeping the existing `live-roam-mode` rules.

### 3.2 Tab behaviour

| Tab | Content (all from `state` / `history`) |
|---|---|
| **Events** | Live feed (newest first, severity colour), selected event detail from `detail`, CTECC status derived from the last critical/incident events, empty state before the first event. Static “Accident Detected” block removed/hidden. |
| **Optimize** | Active controller card: policy label, checkpoint basename, `checkpointSource`, `controllerCalls`, `lastDecisionMs`; per-junction pressure/queue table from `metrics.junctions`; phase-change log from `signalChange` events. The existing control actions dispatch to the simulation endpoints (step/pause/speed) instead of only toggling CSS. |
| **Predict** | 5/10/15-minute horizon cards for queue and throughput computed from `history` (EWMA + linear trend), each labelled **Forecast** with its basis, and the last measured value shown beside it. If `history` is too short, show “collecting data (n/20 samples)” rather than a guess. |
| **Roam** | Map-first (existing panel collapse behaviour) plus a compact live strip: status, clock, vehicles, queued, avg speed, active policy. No static volume/delay numbers. |

Rules:
- Every displayed number is either measured (state/history) or explicitly labelled forecast.
- Anything unavailable (no run, no SUMO, no weights) renders an explicit empty/error state,
  never the old demo values.
- The four tabs share one render path so they cannot disagree with each other.

### 3.3 Checks
- `pytest tests/test_policy_api.py tests/test_model_selection.py tests/test_simulation_telemetry.py`
- `uvicorn api.main:app --port 8000` + `npm run dev` in `frontend/`: start a run on
  `grid-2x2`, switch models, visit each of the four tabs, pause/step, reload; confirm no
  static values survive and the header shows the active model.
- If SUMO is not installed in this environment, report the backend tests and the tab
  rendering against a mocked state instead, and say so.

---

## Out of scope

- New training runs or hyperparameter search.
- Redesigning the React Benchmark pages.
- Persisting live runs into the study's `results/raw` (the live run stays a demo, per
  `docs/ARCHITECTURE.md`).
- Multi-user policy sessions (the policy remains a single-process setting).
