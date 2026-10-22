"""Running SUMO command-line tools with loud failures."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cotraffic.utils.sumo import find_sumo_home, tool


class CommandError(RuntimeError):
    pass


def run(cmd: list[str], cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command, raising with the tail of stderr/stdout if it fails."""
    env = dict(os.environ, SUMO_HOME=str(find_sumo_home()))
    result = subprocess.run(
        [str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, env=env, check=False
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-3000:]
        raise CommandError(
            f"Command failed with code {result.returncode}: {' '.join(map(str, cmd))}\n{tail}"
        )
    return result


def run_tool(
    script: str, args: list[str], cwd: str | Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a Python script from SUMO's tools directory with the current interpreter."""
    return run([sys.executable, str(tool(script)), *args], cwd=cwd)
