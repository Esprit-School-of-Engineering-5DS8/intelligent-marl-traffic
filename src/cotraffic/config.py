"""Loading YAML configuration files.

Configs are grouped by kind (``networks``, ``demand``, ``scenarios``, ``agents``,
``experiments``) under ``configs/``. A config is referenced either by name
(``grid4x4``) or by path.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from cotraffic.paths import CONFIG_DIR

KINDS = ("networks", "demand", "scenarios", "agents", "experiments")


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at top level")
    return data


def config_path(kind: str, name: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"Unknown config kind {kind!r}, expected one of {KINDS}")
    candidate = Path(name)
    if candidate.suffix in (".yaml", ".yml") and candidate.is_file():
        return candidate
    return CONFIG_DIR / kind / f"{name}.yaml"


def load(kind: str, name: str) -> dict[str, Any]:
    """Load ``configs/<kind>/<name>.yaml``; ``name`` may also be a path to a YAML file."""
    data = load_yaml(config_path(kind, name))
    data.setdefault("name", Path(name).stem)
    return data


def available(kind: str) -> list[str]:
    return sorted(p.stem for p in (CONFIG_DIR / kind).glob("*.yaml"))


def load_protocol() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "protocol.yaml")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out
