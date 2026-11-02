"""``GET/POST /api/runs`` and ``WS /ws/status``: side-by-side replay runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from api.policy import METHODS, NETWORKS
from api.runs import RunQueue
from cotraffic.controllers.registry import LEARNED
from cotraffic.paths import default_checkpoint

router = APIRouter(tags=["runs"])
runs = RunQueue()

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "results" / "models.json"
CHECKPOINT_ROOTS = (
    (ROOT / "results" / "checkpoints").resolve(),
    (ROOT / "results" / "training").resolve(),
    (ROOT / "results" / "models").resolve(),
)


def checkpoint_for(spec: str) -> Path | None:
    """The weights a run side names, or ``None`` for a built-in controller.

    Accepted specs: a controller id, ``model:<name>[@vN]`` from the registry, or
    ``checkpoint:<path under results/>``. The last form is what lets the comparison
    tab run any saved checkpoint, whatever agent produced it.
    """
    if spec in METHODS:
        return None
    if spec.startswith("model:"):
        raw = spec.split(":", 1)[1]
        name, _, version = raw.partition("@")
        if not REGISTRY.is_file():
            raise ValueError("no model registry yet (promote a run first)")
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        versions = registry.get("models", {}).get(name) or []
        if not versions:
            raise ValueError(f"unknown model {name!r}")
        if version:
            wanted = int(version.lstrip("v"))
            entry = next((v for v in versions if int(v.get("version", 0)) == wanted), None)
            if entry is None:
                raise ValueError(f"{name} has no version {wanted}")
        else:
            entry = max(versions, key=lambda v: int(v.get("version", 0)))
        path = (ROOT / str(entry.get("checkpoint", "")).replace("\\", "/")).resolve()
        if not path.is_file():
            raise ValueError(f"{name} v{entry.get('version')} has no saved checkpoint")
        return path
    if spec.startswith("checkpoint:"):
        raw = spec.split(":", 1)[1].replace("\\", "/")
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / raw
        path = path.resolve()
        if not any(path.is_relative_to(root) for root in CHECKPOINT_ROOTS):
            raise ValueError("checkpoint must live under results/")
        if not path.is_file():
            raise ValueError(f"checkpoint not found: {raw}")
        return path
    raise ValueError(f"unknown controller {spec}")


def known_methods() -> set[str]:
    """Every controller the registry can build (the single source of truth)."""
    return set(METHODS)


class ScenarioRequest(BaseModel):
    network: str
    demand: Literal["low", "medium", "peak"]
    events: list[Literal["emergency", "pedestrians", "incident", "buses"]] = Field(
        default_factory=list
    )
    seed: int = Field(ge=0, le=999)
    left: str
    right: str

    @field_validator("network")
    @classmethod
    def known_network(cls, network: str) -> str:
        if network not in NETWORKS:
            raise ValueError(f"unknown network {network}")
        return network

    @field_validator("left", "right")
    @classmethod
    def known_source(cls, source: str) -> str:
        if source in METHODS:
            return source
        checkpoint_for(source)  # raises ValueError with the UI message
        return source

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
    for source in (req.left, req.right):
        if source in LEARNED and not default_checkpoint(source, req.network).exists():
            raise HTTPException(422, f"no trained {source} model for {req.network}")
        checkpoint = checkpoint_for(source)
        if checkpoint is None:
            continue
        sidecar = checkpoint.with_suffix(".json")
        if not sidecar.is_file():
            continue
        try:
            trained_on = json.loads(sidecar.read_text(encoding="utf-8")).get("network")
        except (OSError, json.JSONDecodeError):
            trained_on = None
        if trained_on and trained_on != req.network:
            raise HTTPException(
                422, f"these weights were trained for {trained_on}, not {req.network}"
            )
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
