"""FastAPI backend of the dashboard.

    uvicorn api.main:app --port 8000        (from the repository root)

- ``GET /api/data/<file>``: the exported result files (the same JSON as the static
  export in frontend/public/data, so both data sources show identical numbers);
- ``GET /api/assistant/status``, ``POST /api/assistant/chat``: the assistant, streamed as
  Server-Sent Events. Numbers come from the result files; a language model (local Ollama by
  default, or a hosted one whose key stays here) only words the answer, and its text is
  kept only if every number in it is one of the facts. Tool calls are proposals: the
  dashboard shows them and asks for confirmation before anything changes state;
- ``GET/POST /api/runs``: record a side-by-side replay (scripts/record_replay.py);
- ``WS /ws/status``: liveness and run updates for the dashboard's status badge.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from api.llm_remote import make_llm
from api.runs import RunQueue
from cotraffic.assistant.ask import ask
from cotraffic.assistant.llm import LLMUnavailableError
from cotraffic.assistant.scenario import plan_demo
from cotraffic.controllers.registry import LEARNED
from cotraffic.paths import default_checkpoint

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "frontend" / "public" / "data"
NETWORKS = ("grid4x4", "real_district")
EVENTS = ("emergency", "pedestrians", "incident", "buses")
RUN_WORDS = re.compile(r"\b(lance|lancer|simule|simuler|run|démarre|demarre)\b", re.IGNORECASE)

app = FastAPI(title="CoTraffic API", version="1.0")
runs = RunQueue()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "data": DATA.exists(), "activeRuns": runs.active()}


@app.get("/api/data/{path:path}")
def data(path: str) -> FileResponse:
    target = (DATA / f"{path}.json").resolve()
    if not target.is_relative_to(DATA.resolve()) or not target.is_file():
        raise HTTPException(404, f"{path} not found (run scripts/export_dashboard_data.py)")
    return FileResponse(target, media_type="application/json")


# --- assistant -----------------------------------------------------------------------------


@app.get("/api/assistant/status")
def assistant_status(provider: Literal["ollama", "claude", "openai"] = "ollama") -> dict[str, Any]:
    llm = make_llm(provider)
    available, message = llm.status()
    return {
        "available": available,
        "provider": provider,
        "model": llm.model if available else None,
        "message": message,
    }


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=600)
    context: dict[str, Any] = Field(default_factory=dict)
    provider: Literal["ollama", "claude", "openai"] = "ollama"
    language: str = "fr"


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def known_methods() -> set[str]:
    meta = DATA / "meta.json"
    return set(json.loads(meta.read_text(encoding="utf-8"))["methods"]) if meta.exists() else set()


def proposed_run(question: str, llm) -> dict[str, Any] | None:
    """A run the user may confirm, read from a demonstration request; never started here."""
    plan = plan_demo(question, llm)
    spec = plan.spec
    network = "real_district" if spec.network.startswith("real_district") else "grid4x4"
    demand = spec.demand if spec.demand in ("low", "medium", "peak") else "peak"
    return {
        "name": "runScenario",
        "args": {
            "network": network,
            "demand": demand,
            "events": [s for s in spec.scenarios if s in EVENTS],
            "seed": int(spec.seed),
            "left": spec.left,
            "right": spec.right,
        },
    }


async def answer(req: ChatRequest) -> AsyncIterator[str]:
    llm = make_llm(req.provider)
    usable, _ = await run_in_threadpool(llm.status)
    try:
        if RUN_WORDS.search(req.question):
            call = await run_in_threadpool(proposed_run, req.question, llm if usable else None)
            a = call["args"]
            text = (
                f"Je propose de lancer **{a['left']}** contre **{a['right']}** sur {a['network']} "
                f"({', '.join(a['events']) or 'trafic normal'}, demande {a['demand']}, "
                f"graine {a['seed']}). "
                "Rien ne démarre sans votre confirmation."
            )
            for word in re.split(r"(?<= )", text):
                yield sse({"type": "token", "text": word})
            yield sse({"type": "tool_call", "id": "run", "call": call})
            yield sse({"type": "done", "writtenBy": "code"})
            return
        reply = await run_in_threadpool(ask, req.question, llm if usable else None)
    except LLMUnavailableError as err:
        yield sse({"type": "error", "message": str(err)})
        return
    for word in re.split(r"(?<= )", reply.text):
        yield sse({"type": "token", "text": word})
        await asyncio.sleep(0.01)
    if reply.finding.source:
        for source in str(reply.finding.source).split(","):
            yield sse({"type": "source", "file": source.strip()})
    q = reply.query
    if q.junction:
        network = q.network if q.network in NETWORKS else "grid4x4"
        call = {"name": "focusIntersection", "args": {"network": network, "junction": q.junction}}
        yield sse({"type": "tool_call", "id": "focus", "call": call})
    elif len(q.methods) >= 2 and q.network and q.scenario and q.demand and q.metric:
        cell = {"network": q.network, "scenario": q.scenario, "demand": q.demand}
        call = {
            "name": "compareControllers",
            "args": {"cell": cell, "a": q.methods[0], "b": q.methods[1], "metric": q.metric},
        }
        yield sse({"type": "tool_call", "id": "compare", "call": call})
    yield sse({"type": "done", "writtenBy": "model" if reply.written_by != "code" else "code"})


@app.post("/api/assistant/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        answer(req), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


# --- scenario runs ------------------------------------------------------------------------------


class ScenarioRequest(BaseModel):
    network: Literal["grid4x4", "real_district"]
    demand: Literal["low", "medium", "peak"]
    events: list[Literal["emergency", "pedestrians", "incident", "buses"]] = Field(
        default_factory=list
    )
    seed: int = Field(ge=0, le=999)
    left: str
    right: str

    @field_validator("right")
    @classmethod
    def different(cls, right: str, info) -> str:
        if right == info.data.get("left"):
            raise ValueError("pick two different controllers")
        return right


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    return runs.list()


@app.post("/api/runs", status_code=201)
def create_run(req: ScenarioRequest) -> dict[str, Any]:
    methods = known_methods()
    for method in (req.left, req.right):
        if methods and method not in methods:
            raise HTTPException(422, f"unknown controller {method}")
        if method in LEARNED and not default_checkpoint(method, req.network).exists():
            raise HTTPException(422, f"no trained {method} model for {req.network}")
    return runs.submit(req.model_dump())


# --- live status ----------------------------------------------------------------------------------


@app.websocket("/ws/status")
async def status(ws: WebSocket) -> None:
    await ws.accept()
    seen = -1
    try:
        while True:
            if runs.version != seen:
                seen = runs.version
                await ws.send_json({"type": "runs", "active": runs.active(), "version": seen})
            else:
                await ws.send_json({"type": "ping"})
            await asyncio.sleep(2)
    except (WebSocketDisconnect, RuntimeError):
        return
