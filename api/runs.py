"""Scenario runs launched from the dashboard: one replay recording at a time.

A run executes scripts/record_replay.py (two full evaluation episodes), then refreshes the
dashboard export so that the new replay appears. Runs are kept in memory: they are a
demonstration feature, not part of the study's results.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class RunRecord:
    id: str
    request: dict[str, Any]
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    replay_id: str | None = None
    log: list[str] = field(default_factory=list)
    error: str | None = None


def public(run: RunRecord) -> dict[str, Any]:
    """The run as the dashboard's contract has it (camelCase keys)."""
    data = asdict(run)
    data["createdAt"] = data.pop("created_at")
    data["replayId"] = data.pop("replay_id")
    return data


class RunQueue:
    def __init__(self) -> None:
        self.runs: dict[str, RunRecord] = {}
        self.lock = threading.Lock()
        self.jobs: queue.Queue[str] = queue.Queue()
        self.version = 0
        threading.Thread(target=self._worker, daemon=True).start()

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                public(r)
                for r in sorted(self.runs.values(), key=lambda r: r.created_at, reverse=True)
            ]

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        run = RunRecord(id=uuid.uuid4().hex[:10], request=request)
        with self.lock:
            self.runs[run.id] = run
            self.version += 1
        self.jobs.put(run.id)
        return public(run)

    def active(self) -> int:
        with self.lock:
            return sum(r.status in ("queued", "running") for r in self.runs.values())

    def _set(self, run: RunRecord, **changes: Any) -> None:
        with self.lock:
            for k, v in changes.items():
                setattr(run, k, v)
            self.version += 1

    def _stream(self, run: RunRecord, command: list[str]) -> int:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            if line:
                with self.lock:
                    run.log = [*run.log[-49:], line]
                    self.version += 1
        return process.wait()

    def _worker(self) -> None:
        while True:
            run = self.runs[self.jobs.get()]
            r = run.request
            scen = "+".join(r["events"]) or "normal"
            self._set(run, status="running")
            command = [
                sys.executable,
                "scripts/record_replay.py",
                "--net", r["network"],
                "--demand", r["demand"],
                "--seed", str(r["seed"]),
                "--left", r["left"],
                "--right", r["right"],
                "--scenarios", *r["events"],
            ]  # fmt: skip
            try:
                if self._stream(run, command) != 0:
                    raise RuntimeError("the simulation failed (see the log)")
                export = [sys.executable, "scripts/export_dashboard_data.py", "--skip-networks"]
                if self._stream(run, export) != 0:
                    raise RuntimeError("the export failed (see the log)")
                replay = f"{r['network']}__{scen}__{r['demand']}__s{r['seed']}"
                self._set(run, status="done", replay_id=replay)
            except Exception as err:  # reported to the user, the worker keeps running
                self._set(run, status="failed", error=str(err))
