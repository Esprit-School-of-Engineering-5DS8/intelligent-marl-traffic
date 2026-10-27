"""Training and comparison endpoints.

Provides POST /api/train, GET /api/jobs, GET /api/jobs/{id},
SSE /api/jobs/{id}/events, POST /api/jobs/{id}/cancel, POST /api/compare.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.jobs import runner

router = APIRouter(tags=["jobs"])


class TrainRequest(BaseModel):
    agent: str | None = None
    recipe_id: str | None = None
    recipe: dict[str, Any] | None = None
    overrides: dict[str, Any] | None = None
    network: str
    seeds: list[int] = Field(default_factory=lambda: [1])
    timesteps: int | None = Field(default=None, ge=500, le=2_000_000)


class CompareRequest(BaseModel):
    """A paired A/B run: every method runs on the same seeds, so the deltas are paired."""

    network: str
    scenario: str = "normal"
    demand: str = "medium"
    seed: int = 3
    seeds: list[int] | None = Field(default=None, max_length=5)
    methods: list[str] = Field(min_length=2, max_length=5)
    # Quick episodes are shortened for the UI; they are written to results/tmp, and a
    # result that matters should be re-run with quick=false.
    quick: bool = True
    # Per-method agent-config override, e.g. {"coop_ev_ped": {"runtime": {"overlays": []}}}
    # toggles the runtime overlays at evaluation without retraining.
    overrides: dict[str, dict[str, Any]] | None = None


@router.post("/api/train", status_code=202)
def start_train(req: TrainRequest) -> dict[str, Any]:
    try:
        return runner.submit_train(
            req.agent,
            req.network,
            req.seeds,
            req.timesteps,
            recipe_id=req.recipe_id,
            recipe=req.recipe,
            overrides=req.overrides,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/compare", status_code=202)
def start_compare(req: CompareRequest) -> dict[str, Any]:
    try:
        return runner.submit_compare(
            req.network,
            req.scenario,
            req.demand,
            req.seed,
            req.methods,
            req.seeds,
            req.quick,
            req.overrides,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    return runner.list()


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = runner.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@router.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, Any]:
    if not runner.delete(job_id):
        raise HTTPException(400, f"Cannot delete job {job_id}: it is not finished or does not exist")
    return {"ok": True, "jobId": job_id}


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    success = runner.cancel(job_id)
    if not success:
        raise HTTPException(400, f"Cannot cancel job {job_id}")
    return {"ok": True, "jobId": job_id}


@router.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    job = runner.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    q = runner.subscribe(job_id)

    async def event_generator():
        try:
            while True:
                # Non-blocking get with async sleep
                try:
                    payload = q.get_nowait()
                    yield f"data: {json.dumps(payload)}\n\n"
                    if payload.get("status") in ("done", "failed", "cancelled"):
                        break
                except Exception:
                    await asyncio.sleep(0.5)
        finally:
            runner.unsubscribe(job_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
