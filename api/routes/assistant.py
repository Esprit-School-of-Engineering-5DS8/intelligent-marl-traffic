"""``/api/assistant``: answers grounded in the result files, streamed as SSE."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.llm_groq import GroqClient, GroqError
from cotraffic.assistant.ask import ask
from cotraffic.assistant.llm import LLMUnavailableError
from cotraffic.assistant.scenario import plan_demo

router = APIRouter(tags=["assistant"])
groq = GroqClient()

NETWORKS = ("grid3x3", "tunis")
EVENTS = ("emergency", "pedestrians", "incident", "buses")
RUN_WORDS = re.compile(r"\b(lance|lancer|simule|simuler|run|démarre|demarre)\b", re.IGNORECASE)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=600)
    context: dict[str, Any] = Field(default_factory=dict)
    language: str = "fr"


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def proposed_run(question: str, llm) -> dict[str, Any] | None:
    """A run the user may confirm, read from a demonstration request; never started here."""
    plan = plan_demo(question, llm)
    spec = plan.spec
    network = "tunis" if spec.network.startswith("tunis") else "grid3x3"
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
    usable = bool(groq.api_key)
    try:
        if RUN_WORDS.search(req.question):
            call = await run_in_threadpool(proposed_run, req.question, None)
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
        reply = await run_in_threadpool(ask, req.question, groq if usable else None)
    except (GroqError, LLMUnavailableError) as err:
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
        network = q.network if q.network in NETWORKS else "grid3x3"
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


@router.get("/api/assistant/status")
def assistant_status() -> dict[str, Any]:
    return groq.status()


@router.post("/api/assistant/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        answer(req), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
