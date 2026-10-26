# api/ — HTTP adapter

Thin FastAPI layer over `src/cotraffic`. It serves the dashboard; it must not contain
simulation logic of its own (see [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)).

## Run

```bash
# repository root
pip install -r requirements.txt
uvicorn api.main:app --port 8000
```

The Vite dev server proxies `/api` and `/ws` to `http://127.0.0.1:8000`, so the frontend
needs no absolute URLs.

## Layout

| File | Contents |
|---|---|
| `main.py` | app factory, CORS, `/api/health`, router mounting — nothing else |
| `routes/data.py` | `GET /api/data/{path}` — exported result files |
| `routes/assistant.py` | `/api/assistant/status`, `POST /api/assistant/chat` (SSE) |
| `routes/runs.py` | `GET/POST /api/runs`, `WS /ws/status` (replay queue) |
| `routes/simulation.py` | `/api/simulation/*`, `WS /ws/simulation` (live run) |
| `routes/policy.py` | `GET/PUT /api/policy` (active control policy) |
| `simulation.py` | `SimulationSession`: drives `CoTrafficEnv` + `make_controller` |
| `policy.py` | policy state, validation, availability of checkpoints/LLM |
| `runs.py` | replay subprocess queue (`scripts/record_replay.py`) |
| `llm_groq.py` | Groq client for the assistant only (control LLM uses `cotraffic.llm`) |

## Policy

`GET /api/policy` returns the active method, its label, whether it can run here (checkpoint
present, LLM key configured) and the catalog the UI renders. `PUT /api/policy` accepts
`{"method": "coop", "network": "grid4x4"}` and answers `422` when the method is unknown or
has no checkpoint. Defaults live in `configs/dashboard_policy.yaml`; the last choice is
persisted to `results/dashboard_policy.json` (gitignored).

## Environment

| Variable | Purpose |
|---|---|
| `SUMO_HOME`, `LIBSUMO_AS_TRACI` | SUMO binaries and the fast TraCI binding |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | assistant + LLM controller (server-side only) |
| `COTRAFFIC_LLM_PROVIDER`, `COTRAFFIC_LLM_MODEL`, `COTRAFFIC_LLM_INTERVAL_S`, `COTRAFFIC_LLM_MAX_CALLS` | LLM controller behaviour |
| `FRONTEND_ORIGIN` | extra CORS origin for the Vite dev server |

Loaded from `.env` at the repository root (never committed).

## Checks

```bash
curl -s localhost:8000/api/health
curl -s localhost:8000/api/data/meta
curl -s localhost:8000/api/policy
curl -s -X PUT localhost:8000/api/policy -H 'Content-Type: application/json' \
     -d '{"method":"coop","network":"grid4x4"}'
```
