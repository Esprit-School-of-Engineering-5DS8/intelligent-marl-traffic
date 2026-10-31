"""Model registry: ``GET /api/models`` and ``POST /api/models/promote``.

MLflow's registry rebuilt small: a named model is a list of versions, each pointing at
the run it came from. The registry lives in ``frontend/public/data/models.json`` so the
same file is served statically by ``GET /api/data/models`` (like every other export) and
mutated here.

The files are small (one entry per named model), so the whole file is rewritten on every
promotion - concurrent writes are guarded with ``threading.Lock``, which is enough for a
single-process demo backend.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend" / "public" / "data"
REGISTRY = ROOT / "results" / "models.json"
CHECKPOINTS = ROOT / "results" / "checkpoints"
TRAINING = ROOT / "results" / "training"

router = APIRouter(tags=["models"])
_lock = threading.Lock()


def load_registry() -> dict[str, Any]:
    if not REGISTRY.is_file():
        legacy = DATA / "models.json"
        if legacy.is_file():
            return json.loads(legacy.read_text(encoding="utf-8"))
        return {"models": {}}
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def save_registry(payload: dict[str, Any]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    temp = REGISTRY.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, REGISTRY)


def _already_registered(registry: dict[str, Any], digest: str) -> str | None:
    """Name of the existing ``model vN`` that already holds exactly these weights.

    Two identical weight files registered under different names (or twice under the same
    name) produce two rows that can never differ in a benchmark, so they are refused.
    """
    if not digest:
        return None
    for name, versions in registry.get("models", {}).items():
        for entry in versions:
            if str(entry.get("sha256", "")) == digest:
                return f"{name} v{entry.get('version')}"
    return None


def _candidate_checkpoint(run: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    artifact = run.get("artifacts", {}).get("checkpoint")
    candidates = []
    if artifact:
        raw = Path(str(artifact))
        candidates.extend([raw, ROOT / raw])
    run_id = str(run.get("runId", ""))
    parts = run_id.split("__")
    if len(parts) >= 2:
        recipe, network = parts[0], parts[1]
        seed = run.get("seed")
        if seed is not None:
            candidates.extend(sorted((TRAINING / recipe / network / f"seed{int(seed)}" / "checkpoints").glob("model_*_steps.zip"), key=lambda p: p.stat().st_mtime, reverse=True))
            candidates.append(CHECKPOINTS / recipe / network / f"seed{int(seed)}.zip")
        else:
            candidates.extend(sorted((TRAINING / recipe / network).glob("seed*/checkpoints/model_*_steps.zip"), key=lambda p: p.stat().st_mtime, reverse=True))
            candidates.append(CHECKPOINTS / recipe / network / "seed1.zip")
    for path in candidates:
        resolved = path.resolve()
        if resolved.is_file() and resolved.suffix == ".zip":
            sidecar = resolved.with_suffix(".json")
            meta = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else {}
            return resolved, meta
    raise HTTPException(422, "the source run has no available checkpoint artifact")


@router.get("/api/models")
def list_models() -> dict[str, Any]:
    return load_registry()


def _training_candidates() -> list[dict[str, Any]]:
    candidates = []
    for info_path in sorted(TRAINING.glob("*/**/seed*/run_info.json")):
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            agent, network, seed = info["agent"], info["network"], int(info["seed"])
            steps = int(info.get("total_timesteps", 0))
            checkpoint = info_path.parent / "checkpoints" / f"model_{steps}_steps.zip"
            sidecar = checkpoint.with_suffix(".json")
            if not checkpoint.is_file() or not sidecar.is_file():
                continue
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            candidates.append({"id": f"{agent}|{network}|{seed}", "agent": agent, "label": info.get("config", {}).get("label", agent), "network": network, "seed": seed, "timesteps": steps, "checkpoint": checkpoint.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(), "bytes": checkpoint.stat().st_size, "recipeHash": info.get("recipe_hash", ""), "algorithm": info.get("config", {}).get("algorithm", "ppo"), "recipe": info.get("config", {}), "sidecar": meta})
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return candidates


@router.get("/api/models/candidates")
def list_candidates() -> dict[str, Any]:
    return {"candidates": _training_candidates()}


class CandidateRegistration(BaseModel):
    candidate_id: str
    name: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)


@router.post("/api/models/register-candidate", status_code=201)
def register_candidate(req: CandidateRegistration) -> dict[str, Any]:
    candidate = next((c for c in _training_candidates() if c["id"] == req.candidate_id), None)
    if candidate is None:
        raise HTTPException(404, "completed training checkpoint not found")
    existing = _already_registered(load_registry(), candidate["sha256"])
    if existing:
        raise HTTPException(
            409, f"these weights are already registered as {existing} (identical SHA-256)"
        )
    source = (ROOT / candidate["checkpoint"]).resolve()
    sidecar = candidate["sidecar"]
    artifact_dir = ROOT / "results" / "models" / uuid.uuid4().hex
    artifact_dir.mkdir(parents=True, exist_ok=False)
    checkpoint = artifact_dir / "weights.zip"
    shutil.copyfile(source, checkpoint)
    Path(str(checkpoint) + ".json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    with _lock:
        registry = load_registry()
        versions = registry.setdefault("models", {}).setdefault(req.name, [])
        version = max((int(v.get("version", 0)) for v in versions), default=0) + 1
        entry = {"version": version, "runId": candidate["id"], "runName": candidate["label"], "network": candidate["network"], "checkpoint": str(checkpoint.relative_to(ROOT)), "sha256": candidate["sha256"], "bytes": candidate["bytes"], "trainingSeed": candidate["seed"], "timesteps": candidate["timesteps"], "algorithm": candidate["algorithm"], "method": candidate["agent"], "recipeHash": candidate["recipeHash"], "recipe": candidate["recipe"], "available": True, "promoted": False, "notes": req.notes or "", "createdAt": datetime.now(UTC).isoformat()}
        versions.append(entry)
        save_registry(registry)
    return {"model": req.name, "version": entry}


class PromoteRequest(BaseModel):
    runId: str
    name: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=1000)


def _run_of(run_id: str) -> dict[str, Any]:
    target = (DATA / "runs.json").resolve()
    if not target.is_file():
        raise HTTPException(404, "runs.json not found (run scripts/export_dashboard_data.py)")
    registry = json.loads(target.read_text(encoding="utf-8"))
    for run in registry.get("runs", []):
        if run["runId"] == run_id:
            return run
    raise HTTPException(404, f"unknown run {run_id}")


@router.post("/api/models/promote", status_code=201)
def promote(req: PromoteRequest) -> dict[str, Any]:
    run = _run_of(req.runId)
    source, sidecar = _candidate_checkpoint(run)
    recipe = sidecar.get("config", {})
    network = sidecar.get("network") or run.get("network")
    training_seed = sidecar.get("training_seed", sidecar.get("seed", run.get("seed")))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    existing = _already_registered(load_registry(), digest)
    if existing:
        raise HTTPException(
            409, f"these weights are already registered as {existing} (identical SHA-256)"
        )
    artifact_dir = (ROOT / "results" / "models" / uuid.uuid4().hex).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=False)
    checkpoint = artifact_dir / "weights.zip"
    shutil.copyfile(source, checkpoint)
    models_path = Path(str(checkpoint) + ".json")
    models_path.write_text(json.dumps(sidecar or {"config": recipe, "network": network}, indent=2), encoding="utf-8")
    version = 1
    with _lock:
        registry = load_registry()
        models = registry.setdefault("models", {})
        versions = models.setdefault(req.name, [])
        version = max((int(v.get("version", 0)) for v in versions), default=0) + 1
        entry = {
            "version": version,
            "runId": req.runId,
            "runName": run.get("name", req.runId),
            "network": network,
            "checkpoint": str(checkpoint.relative_to(ROOT)),
            "sha256": digest,
            "bytes": checkpoint.stat().st_size,
            "trainingSeed": training_seed,
            "algorithm": recipe.get("algorithm", "ppo"),
            "method": sidecar.get("config", {}).get("name", req.runId.split("__", 1)[0]),
            "recipeHash": sidecar.get("recipe_hash", run.get("hyperparameters", {}).get("recipe_hash", "")),
            "recipe": recipe,
            "available": True,
            "promoted": False,
            "notes": req.notes or "",
            "createdAt": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        versions.append(entry)
        save_registry(registry)
    return {"model": req.name, "version": entry}


@router.delete("/api/models/{name}/{version}")
def delete_version(name: str, version: int) -> dict[str, Any]:
    """Forget one saved version and delete its copied artifact.

    Only the copy under ``results/models`` is removed; the training checkpoint the version
    was registered from is left untouched, so it can be registered again.
    """
    with _lock:
        registry = load_registry()
        models = registry.setdefault("models", {})
        versions = models.get(name, [])
        target = next((entry for entry in versions if int(entry.get("version", 0)) == version), None)
        if target is None:
            raise HTTPException(404, f"{name} has no version {version}")
        models[name] = [entry for entry in versions if int(entry.get("version", 0)) != version]
        if not models[name]:
            del models[name]
        save_registry(registry)
        remaining = len(models.get(name, []))

    checkpoint = (ROOT / str(target.get("checkpoint", ""))).resolve()
    models_root = (ROOT / "results" / "models").resolve()
    if checkpoint.is_file() and checkpoint.is_relative_to(models_root):
        shutil.rmtree(checkpoint.parent, ignore_errors=True)
    return {"deleted": f"{name} v{version}", "remaining": remaining}


@router.post("/api/models/promote-version/{name}/{version}", status_code=202)
def promote_version(name: str, version: int) -> dict[str, Any]:
    """Set the baseline and queue an explicit, full-length evaluation smoke check."""
    with _lock:
        registry = load_registry()
        versions = registry.get("models", {}).get(name, [])
        target = next((entry for entry in versions if int(entry["version"]) == version), None)
        if target is None:
            raise HTTPException(404, f"{name} has no version {version}")
        checkpoint = (ROOT / str(target.get("checkpoint", ""))).resolve()
        if not target.get("available") or not checkpoint.is_relative_to((ROOT / "results" / "models").resolve()) or not checkpoint.is_file():
            raise HTTPException(422, "saved model checkpoint is unavailable")
        if target.get("sha256") and hashlib.sha256(checkpoint.read_bytes()).hexdigest() != target["sha256"]:
            raise HTTPException(422, "saved model checksum mismatch")
    from api.jobs import runner
    job = runner.submit_model_benchmark(
        str(target.get("network")), "normal", "medium", [2001],
        [{"id": f"{name}@v{version}", "label": f"{name} v{version}", "version": version,
          "network": target.get("network"), "method": target.get("method", name),
          "checkpoint": str(checkpoint), "recipe": target.get("recipe", {})}], quick=False,
    )
    with _lock:
        registry = load_registry()
        versions = registry.get("models", {}).get(name, [])
        for entry in versions:
            entry["promoted"] = int(entry["version"]) == version
        save_registry(registry)
        target = next(entry for entry in versions if int(entry["version"]) == version)
    return {"model": name, "version": target, "evaluationJob": job}
