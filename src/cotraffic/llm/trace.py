"""Durable per-call LLM telemetry.

Every request is appended to ``results/telemetry/<run_id>/llm_calls.jsonl``. The record
keeps the exact prompt, the raw answer, the parsed payload, token usage, context-window
utilisation, latency, retry number and fallback state, so a reported LLM number can be
audited call by call.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from cotraffic.paths import RESULTS_DIR

TRACE_DIR = RESULTS_DIR / "telemetry"

# Known context windows (tokens). Unknown models use a conservative default, which is
# only used for the utilisation gauge, never to truncate a prompt.
CONTEXT_WINDOWS = {
    "openai/gpt-oss-20b": 131072,
    "openai/gpt-oss-120b": 131072,
    "llama-3.1-8b-instant": 131072,
    "llama-3.3-70b-versatile": 131072,
    "gemini-2.5-flash": 1048576,
    "gemini-2.5-pro": 1048576,
}
DEFAULT_CONTEXT_WINDOW = 8192


def context_window(model: str | None) -> int:
    return CONTEXT_WINDOWS.get(str(model or ""), DEFAULT_CONTEXT_WINDOW)


class LLMTracer:
    """Thread-safe JSONL writer for one run."""

    def __init__(self, run_id: str, *, root: Path | None = None, enabled: bool = True) -> None:
        self.run_id = run_id
        self.enabled = enabled
        self._lock = threading.Lock()
        self._count = 0
        self._errors = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._latency_ms = 0.0
        base = Path(root) if root is not None else TRACE_DIR
        self.dir = base / run_id
        self.path = self.dir / "llm_calls.jsonl"
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def record(self, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        payload = {
            "ts": time.time(),
            "run_id": self.run_id,
            **event,
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._count += 1
            self._errors += int(bool(payload.get("error")))
            self._prompt_tokens += int(payload.get("prompt_tokens") or 0)
            self._completion_tokens += int(payload.get("completion_tokens") or 0)
            self._latency_ms += float(payload.get("latency_ms") or 0.0)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "trace_path": str(self.path) if self.enabled else "",
                "calls": self._count,
                "errors": self._errors,
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
                "latency_ms_total": round(self._latency_ms, 2),
            }

    def write_summary(self) -> Path | None:
        if not self.enabled:
            return None
        path = self.dir / "summary.json"
        path.write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        return path
