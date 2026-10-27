"""LLM provider catalogue and durable call traces."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from cotraffic.llm.trace import CONTEXT_WINDOWS, TRACE_DIR, context_window

router = APIRouter(tags=["llm"])

KNOWN_MODELS = {
    "groq": [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
    ],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro"],
}


@router.get("/api/llm/providers")
def providers() -> dict[str, Any]:
    groq_key = bool(os.environ.get("GROQ_API_KEY"))
    gemini_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return {
        "providers": [
            {
                "id": "groq",
                "label": "Groq",
                "available": groq_key,
                "models": [
                    {
                        "id": model,
                        "context_window": CONTEXT_WINDOWS.get(
                            model, context_window(model)
                        ),
                    }
                    for model in KNOWN_MODELS["groq"]
                ],
            },
            {
                "id": "gemini",
                "label": "Gemini",
                "available": gemini_key,
                "models": [
                    {
                        "id": model,
                        "context_window": CONTEXT_WINDOWS.get(
                            model, context_window(model)
                        ),
                    }
                    for model in KNOWN_MODELS["gemini"]
                ],
            },
        ],
        "default": {
            "provider": os.environ.get("COTRAFFIC_LLM_PROVIDER", "groq"),
            "model": os.environ.get("COTRAFFIC_LLM_MODEL")
            or os.environ.get("GROQ_MODEL")
            or "openai/gpt-oss-20b",
        },
    }


def _safe_dir(run_id: str) -> Path:
    if not run_id or any(part in run_id for part in ("..", "/", "\\")):
        raise HTTPException(400, "invalid run id")
    path = TRACE_DIR / run_id
    if not path.is_dir():
        raise HTTPException(404, f"no trace for run {run_id!r}")
    return path


@router.get("/api/llm/traces")
def list_traces() -> list[dict[str, Any]]:
    if not TRACE_DIR.is_dir():
        return []
    out = []
    for folder in sorted(TRACE_DIR.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        summary_file = folder / "summary.json"
        summary: dict[str, Any] = {}
        if summary_file.is_file():
            try:
                summary = json.loads(summary_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                summary = {}
        calls_file = folder / "llm_calls.jsonl"
        size = calls_file.stat().st_size if calls_file.is_file() else 0
        out.append(
            {
                "run_id": folder.name,
                "calls": summary.get("calls"),
                "errors": summary.get("errors"),
                "prompt_tokens": summary.get("prompt_tokens"),
                "completion_tokens": summary.get("completion_tokens"),
                "total_tokens": summary.get("total_tokens"),
                "bytes": size,
                "has_trace": calls_file.is_file(),
            }
        )
    return out


@router.get("/api/llm/traces/{run_id}")
def get_trace(
    run_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    folder = _safe_dir(run_id)
    calls_file = folder / "llm_calls.jsonl"
    events: list[dict[str, Any]] = []
    if calls_file.is_file():
        with calls_file.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    summary_file = folder / "summary.json"
    summary: dict[str, Any] = {}
    if summary_file.is_file():
        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            summary = {}
    return {
        "run_id": run_id,
        "summary": summary,
        "events": events[-limit:],
        "truncated": len(events) > limit,
    }
