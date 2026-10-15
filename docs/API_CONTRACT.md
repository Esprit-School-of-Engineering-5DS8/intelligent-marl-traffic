# Dashboard data and API contract

The dashboard reads one set of JSON files, written by `scripts/export_dashboard_data.py`
and `scripts/record_replay.py` from the result files. They are served in two ways with
identical content:

- statically, from `frontend/public/data/<file>.json` (source "Real results");
- by the backend, at `GET /api/data/<file>` (source "Live backend").

The Zod schemas in `frontend/src/shared/schemas/index.ts` are the reference: every file
is validated on arrival. Controllers and metrics are open strings so that a new
experiment does not break the interface. Missing measurements are `null` (JSON has no NaN).

## Files

| File | Content | Source |
| --- | --- | --- |
| `meta` | Index: evaluated cells (network, scenario, demand, controllers), controllers, metrics, run counts, available replays, decision runs, training runs, networks, DQN availability | all |
| `summary` | One row per cell x controller x metric: `n`, `nTrain`, `mean`, `ciLo`, `ciHi` (95% bootstrap CI), `std`. Extra-run metrics (pedestrian P95, crossings in green, ETA error, reward terms) use a normal-approximation CI over seeds | `results/summary/summary.csv`, `results/extra/raw` |
| `comparisons` | Paired tests against a reference: `pairedImprovementPct` (positive = better), `pairedCiLo/Hi`, `pValue`, `pHolm`, `cliffsDelta`, `effect`, `significant`, `family` (core, exploratory, dqn) | `results/summary/comparisons_*.csv` |
| `timeseries/<network>__<scenario>__<demand>` | Per controller, per minute: halted, running, waiting vehicles, mean waiting time, mean speed (mean over seeds) | `results/logs/timeseries` |
| `distributions/<cell>` | Per controller: vehicles per 15 s waiting bin, per run | `results/logs/waiting_distributions` |
| `decisions/<run id>` | Every decision of a learned controller: time, agent, requested and executed phase, shield, explanation | `results/logs/decisions/explained__*` |
| `training/<agent>__<network>` | Per seed and training episode: timesteps, reward, mean halted vehicles, demand, switches, shield corrections | `results/training/*/*/seed*/episodes.csv` |
| `pedestrian_greens` | Per cell and controller: mean pedestrian green length by waiting crowd (crowd sizes seen at least 10 times) | `results/extra/logs/pedestrian_greens` |
| `emergency_log` | Every emergency vehicle of the extra runs: planned departure, ETA at departure, trip time, delay, ETA error, stops at red | `results/extra/logs/emergency` |
| `networks/<network>` | Geometry in SUMO metres: lanes (shape, width, vehicle/pedestrian, internal/crossing), junctions (position, shape, signalised), signal links (index, incoming lane, stop-line position) | `networks/<name>/<name>.net.xml` |
| `replays/<network>__<scenarios>__<demand>__s<seed>` | The same episode under two controllers: frames every `every` seconds over `window` seconds, KPIs of each full episode, emergency-vehicle events | `scripts/record_replay.py` |

### Replay frames

Integers keep the files small. For each frame:

- `t`: seconds from the start of the window;
- `v`: vehicles, 6 integers each: id, kind (0 car, 1 bus, 2 emergency, 3 incident),
  x and y in decimetres, heading in degrees (0 = north, clockwise), speed in dm/s.
  SUMO positions are the front bumper;
- `p`: pedestrians, 3 integers each: x, y in decimetres, waiting (0/1);
- `s`: one signal state string per traffic light, in the order of `signals`
  (SUMO letters: `G`/`g` green, `y` amber, `r` red).

## Backend endpoints

Start: `uvicorn api.main:app --port 8000` (repository root).

| Method | Path | Body / query | Answer |
| --- | --- | --- | --- |
| GET | `/api/health` | | `{ok, data, activeRuns}` |
| GET | `/api/data/<file>` | | the JSON file above, 404 if absent |
| GET | `/api/assistant/status` | `provider` = ollama, claude, openai | `{available, provider, model, message}` |
| POST | `/api/assistant/chat` | `{question, context: {page, cell, controllers}, provider, language}` | `text/event-stream` of chat events |
| GET | `/api/runs` | | list of runs |
| POST | `/api/runs` | `{network, demand, events[], seed, left, right}` | the queued run (201); 422 if a controller is unknown or has no trained model for the network |
| WS | `/ws/status` | | `{"type": "runs", "active", "version"}` when runs change, `{"type": "ping"}` every 2 s |

### Chat events

One JSON object per SSE `data:` line:

- `{"type": "token", "text": "..."}`: a piece of the answer;
- `{"type": "source", "file": "results/summary/summary.csv"}`: a file the answer used;
- `{"type": "tool_call", "id": "...", "call": {"name": ..., "args": ...}}`: a proposal,
  one of `getKpis`, `compareControllers`, `focusIntersection`, `generateChart`,
  `runScenario`. The dashboard never executes anything it receives: it renders the
  call, and `runScenario` (which changes state) needs the user's confirmation;
- `{"type": "done", "writtenBy": "model" | "code"}`: `model` when the language model's
  wording passed the number check, `code` when the answer is the sentence written by code;
- `{"type": "error", "message": "..."}`.

### Runs

A run executes `scripts/record_replay.py` with the requested options (two full
evaluation episodes, a few minutes), then `scripts/export_dashboard_data.py
--skip-networks` so that the replay appears. One run at a time; runs live in memory.
Status: `queued`, `running`, `done` (with `replayId`), `failed` (with `error`); the last
50 log lines are kept.
