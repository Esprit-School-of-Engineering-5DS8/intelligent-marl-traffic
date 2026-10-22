"""Small helpers for result files."""

from __future__ import annotations

import csv
import subprocess
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from cotraffic.paths import REPO_ROOT


@lru_cache(maxsize=1)
def git_commit() -> str:
    """Short hash of HEAD, with ``-dirty`` when tracked files have uncommitted changes."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return head + ("-dirty" if dirty.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_row(path: Path, row: Mapping[str, Any]) -> None:
    """Write one result row as a single-line CSV (with header)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
