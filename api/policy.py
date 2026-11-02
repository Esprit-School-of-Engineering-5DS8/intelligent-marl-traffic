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

from cotraffic import config
from cotraffic.controllers.registry import BASELINES, LEARNED as CORE_LEARNED, LLM
from cotraffic.llm.providers import provider_available
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR, default_checkpoint
from cotraffic.recipes import list_recipes

ROOT = Path(__file__).resolve().parents[1]
POLICY_CONFIG = ROOT / "configs" / "dashboard_policy.yaml"
POLICY_STATE = RESULTS_DIR / "dashboard_policy.json"

_TRAINABLE_RECIPES = tuple(
    r["id"] for r in list_recipes() if r.get("trainable") and r["id"] != "base"
)
LEARNED = tuple(dict.fromkeys((*CORE_LEARNED, *_TRAINABLE_RECIPES)))
METHODS = BASELINES + LEARNED + LLM
# The only active deployment scenarios are San Francisco Mission 2x2 and 3x3
NETWORKS = ("sf_mission_2x2", "sf_mission_3x3", "monaco", "tunis")
DEFAULT_NETWORK = "sf_mission_3x3"

# The dashboard's live scenario ids → the cotraffic network each one simulates.
# One map, shared by the simulation session and the model catalog, so a scenario's
# picker can never offer weights trained for a different network.
SCENARIO_NETWORKS = {
    "grid-2x2": "sf_mission_2x2",
    "grid-3x3": "sf_mission_3x3",
    "monaco": "monaco",
    "tunis": "tunis",
}


def network_for_scenario(scenario: str) -> str | None:
    return SCENARIO_NETWORKS.get(scenario)
LABELS = {
    "ft": "Fixed-time",
    "act": "Actuated",
    "mp": "Max-Pressure",
    "ev_rule": "EV rule",
    "ev_rule_mp": "EV rule + MP",
    "ped_rule_mp": "Pedestrian rule",
    "llm": "LLM controller",
    "llm_team": "LLM team",
}
LABELS.update(
    {
        recipe["id"]: recipe.get("label", recipe["id"])
        for recipe in list_recipes()
        if recipe["id"] not in LABELS
    }
)

_lock = threading.RLock()


def _defaults() -> dict[str, Any]:
    try:
        data = yaml.safe_load(POLICY_CONFIG.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    live = data.get("live") or {}
    method = str(live.get("method", "mp"))
    network = str(live.get("network", DEFAULT_NETWORK))
    return {
        "method": method if method in METHODS else "mp",
        "network": network if network in NETWORKS else DEFAULT_NETWORK,
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
    """Whether the selected LLM controller can reach a provider.

    The team also runs on the mock and replay backends, which need no key, and its
    provider is whatever ``COTRAFFIC_LLM_PROVIDER`` names (groq, gemini or opencode).
    """
    backend = (os.environ.get("COTRAFFIC_LLM_BACKEND") or "provider").lower()
    if method == "llm_team" and backend in ("mock", "replay"):
        return True, None
    provider = (os.environ.get("COTRAFFIC_LLM_PROVIDER") or "groq").lower()
    return provider_available(provider)


def _checkpoint_network(path: Path) -> str | None:
    """Network a checkpoint was trained on: the sidecar's ``network``, else its folder."""
    for sidecar in (path.with_suffix(".json"), Path(str(path) + ".json")):
        if sidecar.is_file():
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("network"):
                return str(data["network"])
    return path.parent.name if path.parent.name in NETWORKS else None


def _validated_checkpoint(raw: str) -> Path:
    """Resolve a checkpoint the UI picked, refusing anything outside the artifacts."""
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if path.suffix != ".zip" or not path.is_file():
        raise ValueError(f"checkpoint not found: {raw}")
    resolved = path.resolve()
    allowed = (
        CHECKPOINTS_DIR.resolve(),
        (RESULTS_DIR / "training").resolve(),
        (RESULTS_DIR / "models").resolve(),
    )
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise ValueError(
            "checkpoint must live under results/checkpoints, results/training or results/models"
        )
    return resolved


def _explicit_checkpoint(method: str, network: str) -> Path | None:
    """The checkpoint picked in the dashboard, when it belongs to this method/network."""
    state = _load()
    if state.get("method") != method or state.get("network") != network:
        return None
    raw = str(state.get("checkpoint") or "auto")
    if raw == "auto":
        return None
    path = Path(raw)
    return path if path.is_file() else None


def checkpoint_path(method: str, network: str, explicit: Path | None = None) -> Path | None:
    """The checkpoint a learned method runs with, or ``None`` for scripted/LLM methods.

    An explicitly selected checkpoint (PUT /api/policy with ``checkpoint``) wins; a run
    that never had one picked falls back to training run 1 of that agent/network.
    """
    if method not in LEARNED:
        return None
    return explicit or _explicit_checkpoint(method, network) or default_checkpoint(method, network)


def availability(
    method: str, network: str, checkpoint: Path | None = None
) -> tuple[bool, str | None]:
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
        path = checkpoint if checkpoint is not None else checkpoint_path(method, network)
        if path is None or not path.exists():
            return False, f"no trained {method} model for {network} (train it first)"
        trained_on = _checkpoint_network(path)
        if trained_on not in (None, network):
            return False, f"these weights were trained for {trained_on}, not {network}"
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
        "checkpointSource": (
            "explicit" if _explicit_checkpoint(method, network)
            else ("auto" if method in LEARNED else None)
        ),
        "available": ready,
        "degraded": degraded,
        "reason": reason,
        "llmProvider": (os.environ.get("COTRAFFIC_LLM_PROVIDER") or "groq").lower(),
        "llmBackend": (os.environ.get("COTRAFFIC_LLM_BACKEND") or "provider").lower(),
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


def update(
    method: str, network: str | None = None, checkpoint: str | None = None
) -> dict[str, Any]:
    """Validate and persist a policy change; ``ValueError`` carries the UI message.

    ``checkpoint`` is a path under ``results/`` (or ``"auto"`` to go back to training run
    1). Selecting weights pins that exact file, so a re-trained ``seed1.zip`` no longer
    silently replaces the model the dashboard was set to.
    """
    with _lock:
        state = _load()
        network = network or state["network"]
        chosen: Path | None = None
        if checkpoint not in (None, "", "auto"):
            chosen = _validated_checkpoint(str(checkpoint))
            trained_on = _checkpoint_network(chosen)
            if trained_on not in (None, network):
                raise ValueError(f"these weights were trained for {trained_on}, not {network}")
        ready, reason = availability(method, network, chosen)
        if not ready:
            raise ValueError(reason or "policy not available")
        state.update({"method": method, "network": network})
        state["checkpoint"] = str(chosen) if chosen is not None else "auto"
        POLICY_STATE.parent.mkdir(parents=True, exist_ok=True)
        POLICY_STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return current()
