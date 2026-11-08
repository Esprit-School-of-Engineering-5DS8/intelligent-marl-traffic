"""Training and comparison endpoints.

Provides POST /api/train, GET /api/jobs, GET /api/jobs/{id},
SSE /api/jobs/{id}/events, POST /api/jobs/{id}/cancel, POST /api/compare.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.jobs import ROOT, runner

router = APIRouter(tags=["jobs"])


class TrainRequest(BaseModel):
    agent: str | None = None
    recipe_id: str | None = None
    recipe: dict[str, Any] | None = None
    overrides: dict[str, Any] | None = None
    network: str
    seeds: list[int] = Field(default_factory=lambda: [1])
    timesteps: int | None = Field(default=None, ge=500, le=2_000_000)


class LLMTeamSettings(BaseModel):
    """Run-time conditioning for the LLM team, sent by the Training page.

    Only the team's slow layer reads these; the SUMO shield still owns hard safety.
    """

    persona: str | None = Field(default=None, max_length=40)
    system_prompt: str | None = Field(default=None, max_length=4000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    cadence_s: float | None = Field(default=None, ge=5, le=120)
    safety_guardrails: bool = True
    explainability: bool = True


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
    # llm_team conditioning: persona, prompt, temperature, cadence and safety toggles.
    llm_settings: LLMTeamSettings | None = None


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
        raise HTTPException(400, str(e)) from e


class ModelBenchmarkRequest(BaseModel):
    network: str
    scenario: str = "normal"
    demand: str = "medium"
    seeds: list[int] = Field(min_length=1, max_length=10)
    model_versions: list[str] = Field(min_length=2, max_length=5)
    quick: bool = True
    primary_metric: Literal["mean_waiting_time"] = "mean_waiting_time"


class BenchmarkSuiteRequest(BaseModel):
    network: str
    scenarios: list[str] = Field(min_length=1, max_length=5)
    demands: list[str] = Field(min_length=1, max_length=4)
    seeds: list[int] = Field(min_length=1, max_length=10)
    model_versions: list[str] = Field(min_length=2, max_length=5)
    quick: bool = True


@router.post("/api/benchmarks", status_code=202)
def start_model_benchmark(req: ModelBenchmarkRequest) -> dict[str, Any]:
    from api.routes.models import load_registry

    registry = load_registry().get("models", {})
    selected = []
    for reference in req.model_versions:
        try:
            name, version_text = reference.rsplit("@v", 1)
            version_num = int(version_text)
            entry = next(v for v in registry[name] if int(v["version"]) == version_num)
        except (ValueError, KeyError, StopIteration):
            raise HTTPException(404, f"unknown saved model version {reference}") from None
        if not entry.get("available", False):
            raise HTTPException(422, f"saved model {reference} is unavailable")
        if any(selected_model["id"] == reference for selected_model in selected):
            raise HTTPException(422, f"saved model version selected more than once: {reference}")
        checkpoint = (ROOT / entry["checkpoint"]).resolve()
        if not checkpoint.is_relative_to((ROOT / "results" / "models").resolve()) or not checkpoint.is_file():
            raise HTTPException(422, f"saved model weights missing or outside model artifact storage: {reference}")
        if entry.get("sha256"):
            import hashlib
            if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != entry["sha256"]:
                raise HTTPException(422, f"saved model checksum mismatch: {reference}")
        selected.append({"id": reference, "label": f"{name} v{version_num}", "version": version_num, "network": entry.get("network"), "method": entry.get("method", name), "checkpoint": str(checkpoint), "recipe": entry.get("recipe", {})})
    from cotraffic import config
    from cotraffic.envs.episodes import unsupported
    if req.scenario != "normal":
        try:
            config.load("scenarios", req.scenario)
        except (FileNotFoundError, ValueError):
            raise HTTPException(422, f"unknown benchmark scenario {req.scenario}") from None
        if req.scenario in unsupported(req.network):
            raise HTTPException(422, f"{req.network} does not support scenario {req.scenario}")
    if req.demand not in {"low", "medium", "peak", "rush_profile"}:
        raise HTTPException(422, f"unknown demand profile {req.demand}")
    if any(model.get("network") != req.network for model in selected):
        incompatible = next(model for model in selected if model.get("network") != req.network)
        raise HTTPException(422, f"saved model {incompatible['id']} was trained for {incompatible.get('network')}, not {req.network}")
    try:
        return runner.submit_model_benchmark(req.network, req.scenario, req.demand, req.seeds, selected, req.quick)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/api/benchmarks/suite", status_code=202)
def start_benchmark_suite(req: BenchmarkSuiteRequest) -> dict[str, Any]:
    from api.routes.models import load_registry
    from cotraffic import config
    from cotraffic.envs.episodes import unsupported

    if req.network not in config.available("networks"):
        raise HTTPException(422, f"unknown benchmark network {req.network}")
    if len(set(req.scenarios)) != len(req.scenarios) or len(set(req.demands)) != len(req.demands):
        raise HTTPException(422, "benchmark suite contains duplicate scenarios or demands")
    if len(set(req.seeds)) != len(req.seeds):
        raise HTTPException(422, "benchmark suite seeds must be unique")
    if any(demand not in {"low", "medium", "peak", "rush_profile"} for demand in req.demands):
        raise HTTPException(422, "benchmark suite includes an unknown demand")
    for scenario in req.scenarios:
        if scenario != "normal":
            try:
                config.load("scenarios", scenario)
            except (FileNotFoundError, ValueError):
                raise HTTPException(422, f"unknown benchmark scenario {scenario}") from None
            if scenario in unsupported(req.network):
                raise HTTPException(422, f"{req.network} does not support scenario {scenario}")
    registry = load_registry().get("models", {})
    selected = []
    if len(set(req.model_versions)) != len(req.model_versions):
        raise HTTPException(422, "benchmark suite contains a duplicate model version")
    for reference in req.model_versions:
        try:
            name, version_text = reference.rsplit("@v", 1)
            version_num = int(version_text)
            entry = next(v for v in registry[name] if int(v["version"]) == version_num)
        except (ValueError, KeyError, StopIteration):
            raise HTTPException(404, f"unknown saved model version {reference}") from None
        checkpoint = (ROOT / str(entry.get("checkpoint", ""))).resolve()
        if not entry.get("available") or not checkpoint.is_file() or not checkpoint.is_relative_to((ROOT / "results" / "models").resolve()):
            raise HTTPException(422, f"saved model {reference} is unavailable")
        if entry.get("sha256"):
            import hashlib
            if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != entry["sha256"]:
                raise HTTPException(422, f"saved model checksum mismatch: {reference}")
        if entry.get("network") != req.network:
            raise HTTPException(422, f"saved model {reference} is incompatible with {req.network}")
        if entry.get("network") != req.network:
            raise HTTPException(422, f"saved model {reference} is incompatible with {req.network}")
        selected.append({"id": reference, "label": f"{name} v{version_num}", "version": version_num, "network": entry.get("network"), "method": entry.get("method", name), "checkpoint": str(checkpoint), "recipe": entry.get("recipe", {})})
    try:
        return runner.submit_benchmark_suite(req.network, req.scenarios, req.demands, req.seeds, selected, req.quick)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


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
            req.llm_settings.model_dump() if req.llm_settings else None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


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


@router.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict[str, Any]:
    """Finish an interrupted campaign from its retained episodes instead of re-running it."""
    try:
        return runner.resume(job_id)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


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
