"""``GET /api/models/catalog``: the trained weights a live run can be set to use.

Three sources, one list:

* ``selected`` — ``results/checkpoints/<agent>/<network>/seed<k>.zip``, what
  ``python -m cotraffic select`` copies the best validated checkpoint to;
* ``training`` — the raw ``model_*_steps.zip`` checkpoints of a training run under
  ``results/training/<agent>/<network>/seed<k>/checkpoints``;
* ``registry`` — the versioned copies under ``results/models`` (see
  ``api/routes/models.py``).

The list is read-only: picking one goes through ``PUT /api/policy`` with an explicit
``checkpoint``, so the selection and its validation live in one place.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api import policy

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINTS = ROOT / "results" / "checkpoints"
TRAINING = ROOT / "results" / "training"
MODELS_ROOT = ROOT / "results" / "models"
REGISTRY = ROOT / "results" / "models.json"

router = APIRouter(tags=["models"])


def _sidecar(path: Path) -> dict[str, Any]:
    """Agent config stored next to a checkpoint (same convention as the trainer)."""
    for candidate in (path.with_suffix(".json"), Path(str(path) + ".json")):
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _entry(
    path: Path,
    *,
    source: str,
    agent: str,
    network: str,
    seed: int | None,
    timesteps: int | None,
    label: str | None = None,
) -> dict[str, Any]:
    meta = _sidecar(path)
    config = meta.get("config") or {}
    return {
        "id": f"{source}:{_rel(path)}",
        "source": source,
        "agent": agent,
        "label": label or config.get("label") or agent,
        "network": meta.get("network") or network,
        "seed": meta.get("training_seed", meta.get("seed", seed)),
        "timesteps": timesteps,
        "algorithm": config.get("algorithm") or meta.get("algorithm") or "ppo",
        "checkpoint": _rel(path),
        "checkpointPath": str(path.resolve()),
        "bytes": path.stat().st_size,
        # A checkpoint without its agent-config sidecar cannot be loaded safely: the
        # observation/action shapes would be guesses.
        "hasAgentConfig": bool(config),
        "available": bool(config),
        "reason": None if config else "no agent-config sidecar next to these weights",
    }


def _from_selected() -> list[dict[str, Any]]:
    entries = []
    for path in sorted(CHECKPOINTS.glob("*/*/seed*.zip")):
        try:
            seed = int(path.stem.removeprefix("seed"))
        except ValueError:
            continue
        entries.append(
            _entry(path, source="selected", agent=path.parent.parent.name,
                   network=path.parent.name, seed=seed, timesteps=None)
        )
    return entries


def _from_training() -> list[dict[str, Any]]:
    entries = []
    for path in sorted(TRAINING.glob("*/*/seed*/checkpoints/model_*_steps.zip")):
        stem = path.stem.removeprefix("model_").removesuffix("_steps")
        try:
            steps = int(stem)
        except ValueError:
            steps = None
        seed_name = path.parent.parent.name
        seed = int(seed_name.removeprefix("seed")) if seed_name.startswith("seed") else None
        entries.append(
            _entry(path, source="training", agent=path.parent.parent.parent.name,
                   network=path.parent.parent.parent.parent.name, seed=seed, timesteps=steps)
        )
    return entries


def _from_registry() -> list[dict[str, Any]]:
    if not REGISTRY.is_file():
        return []
    try:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = []
    for name, versions in (registry.get("models") or {}).items():
        for version in versions or []:
            raw = str(version.get("checkpoint") or "")
            path = (ROOT / raw).resolve()
            if not path.is_relative_to(MODELS_ROOT.resolve()) or not path.is_file():
                continue
            entry = _entry(
                path, source="registry", agent=str(version.get("method") or name),
                network=str(version.get("network") or ""),
                seed=version.get("trainingSeed"),
                timesteps=version.get("timesteps"),
                label=f"{name} v{version.get('version')}",
            )
            entry["id"] = f"registry:{name}@v{version.get('version')}"
            entry["modelName"] = name
            entry["version"] = version.get("version")
            entries.append(entry)
    return entries


@router.get("/api/models/live")
def live_catalog(scenario: str = Query(...)) -> dict[str, Any]:
    """The checkpoints a live run of ``scenario`` can actually be started with.

    Same entries as ``/api/models/catalog``, narrowed to the scenario's network and
    annotated with the policy layer's verdict, so the live picker offers only weights
    that ``PUT /api/policy`` would accept. Unavailable entries stay in the list with
    their reason instead of disappearing silently.
    """
    network = policy.network_for_scenario(scenario)
    if network is None:
        raise HTTPException(404, f"unknown live scenario {scenario}")
    body = model_catalog(network=network)
    models = []
    for raw in body["models"]:
        entry = dict(raw)
        ready, reason = policy.availability(
            entry["agent"], network, Path(entry["checkpointPath"])
        )
        entry["method"] = entry["agent"]
        entry["runnable"] = bool(ready)
        entry["reason"] = reason
        models.append(entry)
    return {
        "scenario": scenario,
        "network": network,
        "count": len(models),
        "runnableCount": sum(1 for entry in models if entry["runnable"]),
        "models": models,
    }


@router.get("/api/models/catalog")
def model_catalog(network: str | None = Query(default=None)) -> dict[str, Any]:
    """Every checkpoint the dashboard can hand to ``PUT /api/policy``."""
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for entry in (*_from_selected(), *_from_registry(), *_from_training()):
        path = Path(entry["checkpointPath"])
        if path in seen:
            continue
        if network and entry["network"] != network:
            continue
        seen.add(path)
        entries.append(entry)
    order = {"selected": 0, "registry": 1, "training": 2}
    entries.sort(key=lambda e: (e["network"], order.get(e["source"], 9), e["agent"], e["seed"] or 0))
    return {"network": network, "count": len(entries), "models": entries}
