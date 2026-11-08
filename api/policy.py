"""Active control policy of the dashboard (RL checkpoint, LLM or baseline).

The policy is what the live simulation and the "new scenario" defaults run. It is read
from ``configs/dashboard_policy.yaml`` (defaults), overlaid by
``results/dashboard_policy.json`` (last choice made in the dashboard), and validated
against the controller registry so an unavailable method is refused instead of silently
downgraded.

The choice is stored **per network**: every scenario (2x2 grid, 3x3 grid, Monaco, Tunis)
has its own controller and its own weights, because a policy trained on one network
cannot drive another. ``networks`` in the state file holds one entry per network; the
top-level ``method``/``network``/``checkpoint`` still mirror the last one edited, which is
the "active" scenario the live controls show.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import yaml

from cotraffic.controllers.registry import BASELINES, LLM
from cotraffic.controllers.registry import LEARNED as CORE_LEARNED
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
_NETWORK_SCENARIOS = {network: scenario for scenario, network in SCENARIO_NETWORKS.items()}

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


def network_for_scenario(scenario: str) -> str | None:
    return SCENARIO_NETWORKS.get(scenario)


def _defaults() -> dict[str, Any]:
    try:
        data = yaml.safe_load(POLICY_CONFIG.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    live = data.get("live") or {}
    method = str(live.get("method", "mp"))
    network = str(live.get("network", DEFAULT_NETWORK))
    checkpoint = str(live.get("checkpoint", "auto"))
    return {
        "network": network if network in NETWORKS else DEFAULT_NETWORK,
        "networks": {
            name: {
                "method": method if method in METHODS else "mp",
                # Only the configured network may carry an explicit path: a path belonging
                # to one network would be refused on the others.
                "checkpoint": checkpoint if name == network else "auto",
            }
            for name in NETWORKS
        },
    }


def _load() -> dict[str, Any]:
    """The policy of every network, defaults overlaid by the saved choices."""
    state = _defaults()
    if POLICY_STATE.is_file():
        try:
            saved = json.loads(POLICY_STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
        if not isinstance(saved, dict):
            saved = {}
        entries = saved.get("networks")
        if isinstance(entries, dict):
            for name, entry in entries.items():
                if name not in NETWORKS or not isinstance(entry, dict):
                    continue
                if entry.get("method") in METHODS:
                    state["networks"][name]["method"] = entry["method"]
                if entry.get("checkpoint"):
                    state["networks"][name]["checkpoint"] = str(entry["checkpoint"])
        # A state file written before per-scenario models carries one method/checkpoint
        # pair for the whole dashboard: it still belongs to that one network.
        network = saved.get("network") if saved.get("network") in NETWORKS else state["network"]
        state["network"] = network
        if saved.get("method") in METHODS:
            state["networks"][network]["method"] = saved["method"]
        if saved.get("checkpoint"):
            state["networks"][network]["checkpoint"] = str(saved["checkpoint"])
    for entry in state["networks"].values():
        if entry["method"] not in METHODS:
            entry["method"] = "mp"
    return state


def method_for(network: str) -> str:
    """The controller pinned to one network — what a live run of that scenario uses."""
    entry = _load()["networks"].get(network) or {}
    method = str(entry.get("method") or "")
    return method if method in METHODS else "mp"


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
    """The checkpoint picked for this network, when it belongs to this method/network."""
    entry = _load()["networks"].get(network) or {}
    if entry.get("method") != method:
        return None
    raw = str(entry.get("checkpoint") or "auto")
    if raw == "auto":
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
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


def _describe(network: str, entry: dict[str, Any]) -> dict[str, Any]:
    """One scenario's controller: what runs, which weights, and whether it can run."""
    method = str(entry.get("method") or "mp")
    ready, reason = availability(method, network)
    checkpoint = checkpoint_path(method, network)
    explicit = _explicit_checkpoint(method, network)
    return {
        "network": network,
        "scenario": _NETWORK_SCENARIOS.get(network),
        "method": method,
        "label": LABELS.get(method, method),
        "checkpoint": str(checkpoint) if checkpoint and checkpoint.exists() else None,
        "weights": checkpoint.name if checkpoint and checkpoint.exists() else None,
        "checkpointSource": (
            "explicit" if explicit else ("auto" if method in LEARNED else None)
        ),
        "available": ready,
        "degraded": ready and reason is not None,
        "reason": reason,
    }


def scenario(network: str) -> dict[str, Any]:
    """One network's own controller, as the live run and the panel see it."""
    state = _load()
    return _describe(network, state["networks"].get(network, {"method": "mp"}))


def current() -> dict[str, Any]:
    """The active policy plus what the UI needs to render the controls.

    ``perNetwork`` holds every scenario's own controller, so the settings page can show
    and change each one without switching the live scenario first.
    """
    with _lock:
        state = _load()
    active = _describe(state["network"], state["networks"][state["network"]])
    per_network = [
        _describe(network, state["networks"][network]) for network in NETWORKS
    ]
    body: dict[str, Any] = {
        "method": active["method"],
        "network": active["network"],
        "label": active["label"],
        "checkpoint": active["checkpoint"],
        "checkpointSource": active["checkpointSource"],
        "available": active["available"],
        "degraded": active["degraded"],
        "reason": active["reason"],
        "llmProvider": (os.environ.get("COTRAFFIC_LLM_PROVIDER") or "groq").lower(),
        "llmBackend": (os.environ.get("COTRAFFIC_LLM_BACKEND") or "provider").lower(),
        "llmModel": (
            os.environ.get("COTRAFFIC_LLM_MODEL")
            or os.environ.get("OPENROUTER_MODEL")
            or os.environ.get("GROQ_MODEL")
            or None
        ),
        "catalog": _catalog_entries(active["network"]),
        "networks": list(NETWORKS),
        "perNetwork": per_network,
        # The controller list is scenario-specific: a learned method only becomes
        # selectable once that network has weights, but stays listed with its reason.
        "catalogByNetwork": {network: _catalog_entries(network) for network in NETWORKS},
    }
    return body


def _catalog_entries(network: str) -> list[dict[str, Any]]:
    """Every controller for one network, with whether it can actually run there.

    ``checkpoint`` is only a path string (it may be the training-run default that does
    not exist yet), so ``available``/``reason`` are what the UI must trust before it
    offers a learned controller on a network that has no weights.
    """
    entries: list[dict[str, Any]] = []
    for name in METHODS:
        path = checkpoint_path(name, network)
        ready, reason = availability(name, network)
        entries.append(
            {
                "method": name,
                "label": LABELS.get(name, name),
                "learned": name in LEARNED,
                "checkpoint": str(path) if path else None,
                "available": ready,
                "reason": reason,
            }
        )
    return entries


def update(
    method: str, network: str | None = None, checkpoint: str | None = None
) -> dict[str, Any]:
    """Validate and persist the controller of one network; ``ValueError`` is the UI message.

    ``checkpoint`` is a path under ``results/`` (or ``"auto"`` to go back to training run
    1). Selecting weights pins that exact file, so a re-trained ``seed1.zip`` no longer
    silently replaces the model the dashboard was set to. Only the network being edited
    changes: the other scenarios keep their own controller.
    """
    with _lock:
        state = _load()
        network = network or state["network"]
        if network not in NETWORKS:
            raise ValueError(f"unknown network {network!r}")
        chosen: Path | None = None
        if checkpoint not in (None, "", "auto"):
            chosen = _validated_checkpoint(str(checkpoint))
            trained_on = _checkpoint_network(chosen)
            if trained_on not in (None, network):
                raise ValueError(f"these weights were trained for {trained_on}, not {network}")
        ready, reason = availability(method, network, chosen)
        if not ready:
            raise ValueError(reason or "policy not available")
        state["networks"][network] = {
            "method": method,
            "checkpoint": str(chosen) if chosen is not None else "auto",
        }
        state["network"] = network
        saved = {
            "network": network,
            "method": method,
            "checkpoint": state["networks"][network]["checkpoint"],
            "networks": state["networks"],
        }
        POLICY_STATE.parent.mkdir(parents=True, exist_ok=True)
        POLICY_STATE.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    return current()
