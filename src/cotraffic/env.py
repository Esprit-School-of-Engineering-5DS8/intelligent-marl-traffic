"""Load the repository ``.env`` file without adding a dependency.

Values already present in the process environment win, so a shell export can
temporarily override the file. The parser handles comments, blank lines,
``export`` prefixes, and single- or double-quoted values.
"""

from __future__ import annotations

import os
from pathlib import Path


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        values[key] = _strip_quotes(value.strip())
    return values


def load_dotenv(path: Path | None = None) -> Path | None:
    candidates = [path] if path is not None else [
        Path(__file__).resolve().parents[2] / ".env",
        Path.cwd() / ".env",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            for key, value in parse_dotenv(candidate.read_text(encoding="utf-8")).items():
                os.environ.setdefault(key, value)
            return candidate
    return None
