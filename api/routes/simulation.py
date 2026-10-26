"""``/api/simulation``: the live run driven by the active control policy."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.simulation import network_geojson, session

router = APIRouter(tags=["simulation"])


class SimulationRequest(BaseModel):
    scenario: Literal["grid-2x2", "grid-3x3"] = "grid-2x2"
    speed: float = Field(default=1, ge=0.25, le=20)
    count: int = Field(default=1, ge=1, le=600)


@router.get("/api/simulation/state")
def simulation_state() -> dict[str, Any]:
    return session.snapshot()


@router.get("/api/simulation/network/{scenario}")
def simulation_network(scenario: Literal["grid-2x2", "grid-3x3"]) -> JSONResponse:
    return JSONResponse(network_geojson(scenario))


@router.post("/api/simulation/start")
def simulation_start(request: SimulationRequest) -> dict[str, Any]:
    try:
        return session.start(request.scenario, request.speed)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/api/simulation/pause")
def simulation_pause() -> dict[str, Any]:
    return session.pause()


@router.post("/api/simulation/resume")
def simulation_resume() -> dict[str, Any]:
    return session.resume()


@router.post("/api/simulation/stop")
def simulation_stop() -> dict[str, Any]:
    return session.stop()


@router.post("/api/simulation/step")
def simulation_step(request: SimulationRequest) -> dict[str, Any]:
    return session.step(request.count)


@router.post("/api/simulation/speed")
def simulation_speed(request: SimulationRequest) -> dict[str, Any]:
    return session.set_speed(request.speed)


@router.websocket("/ws/simulation")
async def simulation_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(session.snapshot())
            await asyncio.sleep(0.25)
    except (WebSocketDisconnect, RuntimeError):
        return
