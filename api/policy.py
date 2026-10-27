"""Active control policy of the dashboard (RL checkpoint, LLM or baseline).

The policy is what the live simulation and the "new scenario" defaults run. It is read
from ``configs/dashboard_policy.yaml`` (defaults), overlaid by
``results/dashboard_policy.json`` (last choice made in the dashboard), and validated
against the controller registry so an unavailable method is refused instead of silently
downgraded.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import yaml

from cotraffic.controllers.registry import BASELINES, LEARNED, LLM
from cotraffic.llm.providers import provider_available
from cotraffic.paths import RESULTS_DIR, default_checkpoint

ROOT = Path(__file__).resolve().parents[1]
POLICY_CONFIG = ROOT / "configs" / "dashboard_policy.yaml"
POLICY_STATE = RESULTS_DIR / "dashboard_policy.json"

METHODS = BASELINES + LEARNED + LLM
NETWORKS = ("grid2x2", "grid3x3", "grid4x4", "real_district")
LABELS = {
    "ft": "Fixed-time",
    "act": "Actuated",
    "mp": "Max-Pressure",
    "ev_rule": "EV rule",
    "ev_rule_mp": "EV rule + MP",
    "ped_rule_mp": "Pedestrian rule",
    "ind": "Independent PPO",
    "coop": "Cooperative PPO",
    "coop_eco": "COOP eco (λ=1.0)",
    "coop_eco05": "COOP eco (λ=0.5)",
    "coop_full": "COOP full",
    "dqn": "DQN",
    "llm": "LLM controller",
    "llm_team": "LLM team",
}

_lock = threading.RLock()


def _defaults() -> dict[str, Any]:
    try:
        data = yaml.safe_load(POLICY_CONFIG.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    live = data.get("live") or {}
    method = str(live.get("method", "mp"))
    network = str(live.get("network", "grid4x4"))
    return {
        "method": method if method in METHODS else "mp",
        "network": network if network in NETWORKS else "grid4x4",
        "checkpoint": str(live.get("checkpoint", "auto")),
    }


def _load() -> dict[str, Any]:
    state = _defaults()
    if POLICY_STATE.is_file():
        try:
            saved = json.loads(POLICY_STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
        if saved.get("method") in METHODS:
            state["method"] = saved["method"]
        if saved.get("network") in NETWORKS:
            state["network"] = saved["network"]
        if saved.get("checkpoint"):
            state["checkpoint"] = saved["checkpoint"]
    return state


def _llm_ready(method: str = "llm") -> tuple[bool, str | None]:
    if method == "llm_team":
        backend = (os.environ.get("COTRAFFIC_LLM_BACKEND") or "opencode").lower()
        if backend in ("mock", "replay"):
            return True, None
    default = "opencode" if method == "llm_team" else "groq"
    provider = (os.environ.get("COTRAFFIC_LLM_PROVIDER") or default).lower()
    ready, reason = provider_available(provider)
    if not ready:
        return False, f"{reason} on the backend"
    return True, None


def checkpoint_path(method: str, network: str) -> Path | None:
    """The checkpoint a learned method runs with, or ``None`` for scripted/LLM methods."""
    if method not in LEARNED:
        return None
    return default_checkpoint(method, network)


def availability(method: str, network: str) -> tuple[bool, str | None]:
    """Whether ``method`` can run on ``network``, plus a warning when it degrades.

    A learned method without a checkpoint cannot run at all (the UI must choose another).
    The LLM controller *can* run without a key: every call falls back to Max-Pressure, so
    it stays available and reports the degradation as a reason.
    """
    if method not in METHODS:
        return False, f"unknown method {method!r}"
    if network not in NETWORKS:
        return False, f"unknown network {network!r}"
    if method in LEARNED:
        checkpoint = checkpoint_path(method, network)
        if checkpoint is None or not checkpoint.exists():
            return False, f"no trained {method} model for {network} (train it first)"
        return True, None
    if method in LLM:
        ready, reason = _llm_ready(method)
        if ready:
            return True, None
        return True, f"{reason}: every LLM call falls back to Max-Pressure"
    return True, None


def current() -> dict[str, Any]:
    """The active policy plus what the UI needs to render the controls."""
    with _lock:
        state = _load()
    method, network = state["method"], state["network"]
    ready, reason = availability(method, network)
    checkpoint = checkpoint_path(method, network)
    degraded = ready and reason is not None
    return {
        "method": method,
        "network": network,
        "label": LABELS.get(method, method),
        "checkpoint": str(checkpoint) if checkpoint and checkpoint.exists() else None,
        "available": ready,
        "degraded": degraded,
        "reason": reason,
        "catalog": [
            {
                "method": name,
                "label": LABELS.get(name, name),
                "learned": name in LEARNED,
                "checkpoint": str(checkpoint_path(name, network))
                if checkpoint_path(name, network)
                else None,
            }
            for name in METHODS
        ],
        "networks": list(NETWORKS),
    }


def update(method: str, network: str | None = None) -> dict[str, Any]:
    """Validate and persist a policy change; ``ValueError`` carries the UI message."""
    with _lock:
        state = _load()
        network = network or state["network"]
        ready, reason = availability(method, network)
        if not ready:
            raise ValueError(reason or "policy not available")
        state.update({"method": method, "network": network})
        POLICY_STATE.parent.mkdir(parents=True, exist_ok=True)
        POLICY_STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return current()
