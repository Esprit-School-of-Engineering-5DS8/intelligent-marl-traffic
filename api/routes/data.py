"""``GET /api/data/<file>``: the exported result files the dashboard reads.

``DELETE /api/data/runs/<runId>`` removes a run from the registry export and
memorizes the deletion in ``results/registry_hidden.json`` so the next export
run does not resurrect it.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend" / "public" / "data"
TOMBSTONES = ROOT / "results" / "registry_hidden.json"

router = APIRouter(tags=["data"])


@router.delete("/api/data/runs/{run_id}")
def delete_run(run_id: str) -> dict[str, object]:
    runs_file = DATA / "runs.json"
    if not runs_file.is_file():
        raise HTTPException(404, "runs.json not found (run scripts/export_dashboard_data.py)")
    payload = json.loads(runs_file.read_text(encoding="utf-8"))
    runs = payload.get("runs", [])
    kept = [run for run in runs if run.get("runId") != run_id]
    if len(kept) == len(runs):
        raise HTTPException(404, f"unknown run {run_id}")
    payload["runs"] = kept
    payload["generatedAt"] = payload.get("generatedAt")
    runs_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    hidden: set[str] = set()
    if TOMBSTONES.is_file():
        try:
            hidden = set(json.loads(TOMBSTONES.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            hidden = set()
    hidden.add(run_id)
    TOMBSTONES.write_text(json.dumps(sorted(hidden), indent=2), encoding="utf-8")
    return {"deleted": run_id, "remaining": len(kept)}


@router.get("/api/data/{path:path}")
def data(path: str) -> FileResponse:
    target = (DATA / f"{path}.json").resolve()
    if not target.is_relative_to(DATA.resolve()) or not target.is_file():
        raise HTTPException(404, f"{path} not found (run scripts/export_dashboard_data.py)")
    return FileResponse(
        target,
        media_type="application/json",
        # no-cache (not no-store): the browser may keep the body but must
        # revalidate with the ETag. Without this, heuristic caching (built
        # from Last-Modified alone) pins a stale export for hours after
        # scripts/export_dashboard_data.py runs, and the pages mix old meta
        # with new result files.
        headers={"Cache-Control": "no-cache"},
    )
