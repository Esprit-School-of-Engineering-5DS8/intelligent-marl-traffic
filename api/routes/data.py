"""``GET /api/data/<file>``: the exported result files the dashboard reads."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend" / "public" / "data"

router = APIRouter(tags=["data"])


@router.get("/api/data/{path:path}")
def data(path: str) -> FileResponse:
    target = (DATA / f"{path}.json").resolve()
    if not target.is_relative_to(DATA.resolve()) or not target.is_file():
        raise HTTPException(404, f"{path} not found (run scripts/export_dashboard_data.py)")
    return FileResponse(target, media_type="application/json")
