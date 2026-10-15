# CoTraffic dashboard

Control-room web application for the CoTraffic project: supervision of the results,
side-by-side replays on a 2D map and in 3D, comparison of the learned agents with the
classical controllers, scenario runs and an assistant that answers questions about the
results. Every number on screen comes from the project's result files (`results/`).

## Quick start

Node.js 22 or newer.

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

That is enough: the dashboard reads the exported results bundled in `public/data`
(source "Real results", the default). To refresh them after new experiments:

```bash
# from the repository root, in the Python environment
python scripts/export_dashboard_data.py            # results -> frontend/public/data
python scripts/record_replay.py --net grid4x4 --scenarios emergency --demand peak \
    --left ft --right coop_full                    # a side-by-side replay (~5 min)
python scripts/export_dashboard_data.py --skip-networks   # list the new replay
```

Replays are not committed (several MB each): record them once on a new machine. The
four used in the demonstration take about 20 minutes in total:

```bash
for s in emergency pedestrians incident; do
  python scripts/record_replay.py --net grid4x4 --scenarios $s --demand peak
done
python scripts/record_replay.py --net real_district --scenarios emergency --demand peak
```

### With the backend (live source)

The backend adds the assistant's language model, scenario runs and the live status
stream. Start it from the repository root, then choose "Live backend" in Settings:

```bash
pip install fastapi uvicorn                 # once (pinned in requirements.txt)
uvicorn api.main:app --port 8000
```

The Vite development server forwards `/api` and `/ws` to `http://localhost:8000`
(`VITE_API_URL` to change it). The assistant uses the local Ollama model by default
(`ollama pull qwen2.5:3b`); hosted models are optional and their keys stay on the backend
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). The browser never holds a key.

## Pages

| Page                 | What it shows                                                                                                                                                                        | Data                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------- |
| Overview             | KPIs of a controller against a reference (paired gain, Holm significance), metric by controller with 95% CI, halted vehicles over the episode, data provenance                       | summary, comparisons, timeseries |
| Live map             | The network (deck.gl), vehicles coloured by speed, signal states at the stop lines, two controllers side by side on the same traffic, junction details, follow the emergency vehicle | networks, replays                |
| 3D simulation        | The same replay in 3D (React Three Fiber), orbit, zoom and pan                                                                                                                       | networks, replays                |
| RL agents            | Learning curves per seed (PPO, DQN), reward decomposition, explained decisions and safety-shield corrections                                                                         | training, extra runs, decisions  |
| Comparative analysis | Forest plot of gains per scenario, gain map, statistical tests (CSV export), waiting-time distributions                                                                              | comparisons, distributions       |
| Assistant            | Questions in plain language; answers with sources, inline charts, navigation, proposed runs                                                                                          | all of the above                 |
| Scenarios            | Recorded replays, form to record a new one (backend), CSV export                                                                                                                     | replays, summary                 |
| Pedestrians          | Waiting at crossings (mean, P95, max), crossings finished in green, green length against the waiting crowd, pedestrian/vehicle trade-off                                             | summary, extra runs              |
| Emergency            | Emergency-vehicle delay and trip, stops at red, ETA error, effect on other road users, intervention log                                                                              | summary, extra runs              |
| Settings             | Theme, language (French, English, Arabic right to left), units, data source, language model provider                                                                                 | local                            |

## Architecture

```
src/
  app/            shell (sidebar, top bar), routes (one lazy chunk per page), providers,
                  theme, error boundary
  features/       one folder per page; replay/ is shared by the map and the 3D view
  shared/
    api/          data source (static export or backend), TanStack Query hooks,
                  backend calls, status WebSocket with exponential backoff
    schemas/      Zod contract of every file and message (types are inferred from it)
    domain/       controller names and colours, metric units and direction, formatting
    charts/       ECharts (modular import), chart builders, chart card with data table
    components/   pickers, KPI card, query states, scenario focus
    ui/           primitives (Radix-based): button, card, badge, sheet, dialogs...
    i18n/         French, English, Arabic
    state/        filters shared between pages (Zustand)
```

- Data flow: result files -> `scripts/export_dashboard_data.py` -> JSON files, served
  either statically (`public/data`) or by the backend (`/api/data/...`, the same files) ->
  validated with Zod on arrival -> cached by TanStack Query.
- Playback: one clock (Zustand) drives both the 2D map and the 3D view; frames are
  interpolated between recorded samples, so playback is smooth at any speed.
- Assistant: without the backend, the browser reads the question with keywords and
  computes the answer from the exported results; with it, the answer is streamed (SSE)
  from the backend, whose language model only words facts taken from the results.
  Tool calls are data: charts and comparisons render at once, navigation waits for a
  click, and launching a simulation needs an explicit confirmation.

The JSON files and the backend endpoints are described in
[docs/API_CONTRACT.md](../docs/API_CONTRACT.md).

## Quality

```bash
npm run lint           # ESLint (TypeScript, React hooks, jsx-a11y)
npm run typecheck      # TypeScript strict
npm test               # Vitest + Testing Library
npm run e2e            # Playwright (builds and serves the production bundle)
npm run build
```

The pre-commit hook (Husky + lint-staged) formats and lints staged files; the
`frontend` GitHub workflow runs all of the above.

Accessibility: keyboard navigation everywhere (skip link, focus rings, Space to play a
replay, Ctrl+K for the assistant), labelled controls, every chart has a text alternative
and a data table, colour is never the only cue (traffic states also carry a label or an
icon), reduced motion respected, right-to-left layout for Arabic.
