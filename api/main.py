"""FastAPI backend of the dashboard.

    uvicorn api.main:app --port 8000        (from the repository root)

This module only assembles the app: CORS, health, and one router per concern
(``api/routes/``). The URLs are the dashboard's contract — see docs/ARCHITECTURE.md §4.

- ``GET /api/data/<file>``: the exported result files (the same JSON as the static
  export in frontend/public/data, so both data sources show identical numbers);
- ``GET /api/assistant/status``, ``POST /api/assistant/chat``: the assistant, streamed as
  Server-Sent Events. Numbers come from the result files;
- ``GET/POST /api/runs``: record a side-by-side replay (scripts/record_replay.py);
- ``/api/simulation/*``: the live run, driven by the active control policy;
- ``GET/PUT /api/policy``: read or change that policy (RL checkpoint, LLM or baseline);
- ``WS /ws/status``, ``WS /ws/simulation``: liveness and live state.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import assistant, data, policy, runs, simulation

DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def create_app() -> FastAPI:
    app = FastAPI(title="KEMETRA API", version="1.1")

    origins = list(DEFAULT_ORIGINS)
    extra = os.environ.get("FRONTEND_ORIGIN")
    if extra and extra not in origins:
        origins.append(extra)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (data, assistant, runs, simulation, policy):
        app.include_router(module.router)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "data": data.DATA.exists(), "activeRuns": runs.runs.active()}

    return app


app = create_app()
