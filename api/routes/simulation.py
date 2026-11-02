"""``/api/simulation``: the live run driven by the active control policy."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from api.simulation import (
    NETWORK_SCENARIOS,
    NotRunning,
    SCENARIOS,
    network_geojson,
    resolve_scenario,
    session,
)

router = APIRouter(tags=["simulation"])


class SimulationRequest(BaseModel):
    # Either id may be sent: ``network`` names the cotraffic network to run on,
    # ``scenario`` the dashboard scenario. A pair that disagrees is refused.
    scenario: str | None = None
    network: str | None = None
    speed: float = Field(default=1, ge=0.25, le=20)
    count: int = Field(default=1, ge=1, le=600)
    # Optional weights for this run: choosing them goes through PUT /api/policy, so a
    # request cannot start weights the policy layer would refuse.
    method: str | None = None
    checkpoint: str | None = None
    # Rain slows vehicles and lengthens their headway inside SUMO, so it changes
    # the run's numbers, not just the map's look.
    weather: str = "clear"

    @field_validator("scenario")
    @classmethod
    def known_scenario(cls, scenario: str | None) -> str | None:
        if scenario is not None and scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario}")
        return scenario

    @field_validator("network")
    @classmethod
    def known_network(cls, network: str | None) -> str | None:
        if network is not None and network not in NETWORK_SCENARIOS:
            raise ValueError(f"unknown network {network}")
        return network

    @field_validator("weather")
    @classmethod
    def known_weather(cls, weather: str) -> str:
        if weather not in ("clear", "rain"):
            raise ValueError(f"unknown weather {weather}")
        return weather


@router.get("/api/simulation/history")
def simulation_history() -> dict[str, Any]:
    return session.history()


@router.get("/api/simulation/state")
def simulation_state() -> dict[str, Any]:
    return session.snapshot()


@router.get("/api/simulation/network/{scenario}")
def simulation_network(scenario: str) -> JSONResponse:
    if scenario not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario {scenario}")
    return JSONResponse(network_geojson(scenario))


@router.post("/api/simulation/start")
def simulation_start(request: SimulationRequest) -> dict[str, Any]:
    try:
        scenario = resolve_scenario(request.scenario, request.network)
        return session.start(
            scenario, request.speed, request.method, request.checkpoint, request.weather
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/api/simulation/pause")
def simulation_pause() -> dict[str, Any]:
    return session.pause()


@router.post("/api/simulation/resume")
def simulation_resume() -> dict[str, Any]:
    return session.resume()


class WeatherRequest(BaseModel):
    weather: str = Field(pattern="^(clear|rain)$")


@router.post("/api/simulation/weather")
def simulation_weather(request: WeatherRequest) -> dict[str, Any]:
    """Turn rain on or off for the running live run."""
    try:
        return session.set_weather(request.weather)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/api/simulation/stop")
def simulation_stop() -> dict[str, Any]:
    return session.stop()


@router.post("/api/simulation/incident")
def simulation_incident() -> dict[str, Any]:
    """Inject an operator-reported collision into the live run."""
    try:
        return session.inject_incident()
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


class SignalRequest(BaseModel):
    junction: str = Field(min_length=1, max_length=40)
    green: float = Field(ge=6, le=90)


@router.post("/api/simulation/signal")
def simulation_signal(request: SignalRequest) -> dict[str, Any]:
    """Change the current phase's green time at one junction, for the running corridor."""
    try:
        return session.queue_signal(request.junction, request.green)
    except NotRunning as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/api/simulation/junctions")
def simulation_junctions() -> dict[str, Any]:
    return session.junctions()


@router.get("/api/simulation/forecast")
def simulation_forecast(horizon: int = Query(default=15, ge=5, le=30)) -> dict[str, Any]:
    """Queue/throughput projection from the run's own history."""
    try:
        return session.forecast(horizon)
    except NotRunning as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/api/simulation/step")
def simulation_step(request: SimulationRequest | None = None) -> dict[str, Any]:
    """Advance a paused run; the body is optional (one decision by default)."""
    return session.step(request.count if request else 1)


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
