"""
agents/llm/env.py
Minimal .env loader (stdlib only, no python-dotenv dependency).

Format: one KEY=VALUE per line; blank lines and lines starting with `#` are
ignored; an optional `export ` prefix is allowed; single/double quotes around
the value are stripped. Real environment variables always win unless
`override=True`.

The repo-root `.env` is gitignored; `.env.example` documents the keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional


def parse_env_file(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            values[key] = value
    return values


def load_env_file(path: str, override: bool = False) -> int:
    """Load a .env file into os.environ. Returns the number of keys set."""
    if not path or not os.path.isfile(path):
        return 0
    loaded = 0
    for key, value in parse_env_file(path).items():
        if override or key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_repo_env(filename: str = ".env") -> Optional[str]:
    """Load `<repo>/.env` if present; returns the path or None."""
    path = repo_root() / filename
    if not path.is_file():
        return None
    load_env_file(str(path))
    return str(path)
