"""``GET/POST /api/runs`` and ``WS /ws/status``: side-by-side replay runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from api.runs import RunQueue
from cotraffic.controllers.registry import LEARNED
from cotraffic.paths import default_checkpoint

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend" / "public" / "data"

router = APIRouter(tags=["runs"])
runs = RunQueue()


def known_methods() -> set[str]:
    meta = DATA / "meta.json"
    return set(json.loads(meta.read_text(encoding="utf-8"))["methods"]) if meta.exists() else set()


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


@router.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    return runs.list()


@router.post("/api/runs", status_code=201)
def create_run(req: ScenarioRequest) -> dict[str, Any]:
    methods = known_methods()
    for method in (req.left, req.right):
        if methods and method not in methods:
            raise HTTPException(422, f"unknown controller {method}")
        if method in LEARNED and not default_checkpoint(method, req.network).exists():
            raise HTTPException(422, f"no trained {method} model for {req.network}")
    return runs.submit(req.model_dump())


@router.websocket("/ws/status")
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
