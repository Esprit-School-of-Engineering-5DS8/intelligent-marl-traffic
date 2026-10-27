"""Composable agent recipes.

A *recipe* is a single agent definition that combines:

* a **policy** (PPO/DQN hyperparameters, observation blocks, reward terms),
* a **runtime stack** (ordered overlays such as EV preemption and pedestrian service),
* optional **LLM** settings (provider, model, prompt, tools).

Presets such as ``ind``, ``coop`` and ``coop_full`` remain valid recipes: legacy files in
``configs/agents`` are loaded transparently when no file exists in ``configs/recipes``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from cotraffic import config
from cotraffic.paths import CONFIG_DIR

RECIPE_DIR = CONFIG_DIR / "recipes"

#: Overlay ids understood by :mod:`cotraffic.controllers.overlays`.
OVERLAY_IDS = ("ev_preemption", "pedestrian_service", "mp_fallback")

#: Default priorities: higher wins. EV preemption must override pedestrian service.
OVERLAY_PRIORITY = {"ev_preemption": 100, "pedestrian_service": 90, "mp_fallback": 10}

OBSERVATION_BLOCKS = ("neighbours", "emergency", "pedestrians", "buses", "forecast")
REWARD_TERMS = ("co2", "ev", "ped")
REWARD_BASES = ("wait", "queue", "pressure")

PPO_HYPERPARAMETERS = (
    "learning_rate",
    "n_steps",
    "batch_size",
    "n_epochs",
    "gamma",
    "gae_lambda",
    "clip_range",
    "ent_coef",
    "vf_coef",
    "max_grad_norm",
    "net_arch",
)
DQN_HYPERPARAMETERS = (
    "learning_rate",
    "buffer_size",
    "learning_starts",
    "batch_size",
    "tau",
    "gamma",
    "train_freq",
    "gradient_steps",
    "target_update_interval",
    "exploration_fraction",
    "exploration_initial_eps",
    "exploration_final_eps",
    "net_arch",
)


def _path(name: str) -> Path:
    candidate = Path(name)
    if candidate.suffix in (".yaml", ".yml") and candidate.is_file():
        return candidate
    recipe = RECIPE_DIR / f"{name}.yaml"
    if recipe.is_file():
        return recipe
    return config.config_path("agents", name)


def load_recipe(name: str) -> dict[str, Any]:
    """Load a recipe by name/path; legacy agent YAMLs are accepted and normalised."""
    path = _path(name)
    data = config.load_yaml(path)
    data.setdefault("name", path.stem)
    parent = data.pop("extends", None)
    if parent:
        merged = config.deep_merge(load_recipe(parent), data)
        merged["name"] = path.stem
        merged["description"] = data.get("description", "")
        data = merged
    return normalize_recipe(data)


def normalize_recipe(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a validated, canonical recipe dict (legacy flat agent configs included)."""
    cfg = copy.deepcopy(raw)
    cfg.setdefault("name", "recipe")
    cfg.setdefault("description", "")
    cfg.setdefault("algorithm", "ppo")
    if cfg["algorithm"] not in ("ppo", "dqn"):
        raise ValueError(f"algorithm must be 'ppo' or 'dqn', got {cfg['algorithm']!r}")

    cfg["observation"] = dict(cfg.get("observation") or {})
    for key in cfg["observation"]:
        if key not in OBSERVATION_BLOCKS:
            raise ValueError(f"unknown observation block {key!r}")
        cfg["observation"][key] = bool(cfg["observation"][key])

    reward = dict(cfg.get("reward") or {})
    base = reward.get("base", "wait")
    if base not in REWARD_BASES:
        raise ValueError(f"reward.base must be one of {REWARD_BASES}, got {base!r}")
    reward.setdefault("base", base)
    for key in reward:
        if key not in ("base", "person_weighted", "clip", *REWARD_TERMS):
            raise ValueError(f"unknown reward key {key!r}")
    cfg["reward"] = reward

    cfg.setdefault("runtime", {})
    cfg["runtime"] = dict(cfg["runtime"] or {})
    cfg["runtime"]["overlays"] = normalize_overlays(cfg["runtime"].get("overlays"))
    if "shield" in cfg["runtime"]:
        cfg["runtime"]["shield"] = dict(cfg["runtime"]["shield"] or {})

    cfg.setdefault("training", {})
    cfg.setdefault("validation", {})

    algorithm = cfg["algorithm"]
    if algorithm not in cfg:
        # Legacy DQN recipes inherit the PPO block from base; never use the wrong one.
        cfg[algorithm] = dict(cfg.get("ppo" if algorithm == "ppo" else "dqn") or {})
    if not isinstance(cfg[algorithm], dict):
        raise ValueError(f"{algorithm} block must be a mapping")
    if "net_arch" in cfg[algorithm]:
        arch = cfg[algorithm]["net_arch"]
        if not isinstance(arch, list) or not all(isinstance(x, int) for x in arch):
            raise ValueError("net_arch must be a list of integers")

    cfg.setdefault("llm", None)
    return cfg


def normalize_overlays(raw: Any) -> list[dict[str, Any]]:
    """Accept strings, mappings or ``{id, params}`` entries and return a canonical list."""
    if raw is None:
        return []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("runtime.overlays must be a list")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        params: dict[str, Any] = {}
        if isinstance(item, str):
            overlay_id = item
        elif isinstance(item, dict):
            if "id" in item:
                overlay_id = str(item["id"])
                params = dict(item.get("params") or {})
                params.update({k: v for k, v in item.items() if k not in ("id", "params")})
            elif len(item) == 1:
                overlay_id, value = next(iter(item.items()))
                overlay_id = str(overlay_id)
                params = dict(value or {}) if isinstance(value, dict) else {}
            else:
                raise ValueError(f"cannot read overlay entry {item!r}")
        else:
            raise ValueError(f"cannot read overlay entry {item!r}")
        if overlay_id not in OVERLAY_IDS:
            raise ValueError(f"unknown overlay {overlay_id!r}; expected one of {OVERLAY_IDS}")
        if overlay_id in seen:
            raise ValueError(f"overlay {overlay_id!r} appears twice")
        seen.add(overlay_id)
        if params.get("enabled", True) is False:
            continue
        params.pop("enabled", None)
        params.setdefault("priority", OVERLAY_PRIORITY[overlay_id])
        out.append({"id": overlay_id, **params})
    return out


def overlay_ids(recipe: dict[str, Any]) -> list[str]:
    return [o["id"] for o in recipe.get("runtime", {}).get("overlays", [])]


def recipe_hash(recipe: dict[str, Any]) -> str:
    payload = json.dumps(recipe, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def save_recipe(recipe: dict[str, Any], *, overwrite: bool = True) -> Path:
    """Validate and write ``configs/recipes/<name>.yaml`` atomically."""
    cfg = normalize_recipe(recipe)
    name = str(cfg["name"]).strip()
    if not name or any(ch in name for ch in "\\/:*?\"<>|"):
        raise ValueError(f"invalid recipe name {name!r}")
    RECIPE_DIR.mkdir(parents=True, exist_ok=True)
    path = RECIPE_DIR / f"{name}.yaml"
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    import yaml

    path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return path


def list_recipes() -> list[dict[str, Any]]:
    """Every recipe (new files first, legacy agent YAMLs as presets)."""
    names: dict[str, str] = {}
    for path in sorted(RECIPE_DIR.glob("*.yaml")) if RECIPE_DIR.is_dir() else []:
        names[path.stem] = "recipe"
    for name in config.available("agents"):
        names.setdefault(name, "preset")
    out = []
    for name, source in sorted(names.items()):
        try:
            cfg = load_recipe(name)
        except Exception as error:  # noqa: BLE001 - a broken file must not hide the rest
            out.append(
                {
                    "id": name,
                    "label": name,
                    "source": source,
                    "error": str(error),
                    "hash": "",
                }
            )
            continue
        algorithm = cfg.get("algorithm", "ppo")
        out.append(
            {
                "id": name,
                "label": cfg.get("label") or name.replace("_", " ").title(),
                "source": source,
                "description": cfg.get("description", ""),
                "algorithm": algorithm,
                "overlays": overlay_ids(cfg),
                "hash": recipe_hash(cfg),
                "trainable": bool(cfg.get("training")) and bool(cfg.get(algorithm)),
                "config": cfg,
            }
        )
    return out


def recipe_schema() -> dict[str, Any]:
    """Metadata used by the Training Studio to render the knobs without hardcoding."""
    return {
        "observations": [
            {
                "key": "neighbours",
                "label": "Neighbour messages (COOP)",
                "description": "Receive queue/release/pressure summaries from upstream junctions.",
            },
            {
                "key": "emergency",
                "label": "Emergency vehicles",
                "description": "Observe approaching emergency vehicles per phase.",
            },
            {
                "key": "pedestrians",
                "label": "Pedestrians",
                "description": "Observe waiting pedestrians at each controlled crossing.",
            },
            {
                "key": "buses",
                "label": "Buses",
                "description": "Observe occupancy-weighted bus load per approach.",
            },
            {
                "key": "forecast",
                "label": "Inflow forecast",
                "description": "Add the Ridge prediction of inflow for the next 5 minutes.",
            },
        ],
        "reward_bases": list(REWARD_BASES),
        "reward_terms": [
            {"key": "person_weighted", "label": "Person-weighted delay", "type": "bool"},
            {"key": "co2", "label": "CO2 penalty (lambda)", "type": "float"},
            {"key": "ev", "label": "Emergency-vehicle penalty (lambda)", "type": "float"},
            {"key": "ped", "label": "Pedestrian penalty (lambda)", "type": "float"},
            {"key": "clip", "label": "Reward clip", "type": "float"},
        ],
        "algorithms": ["ppo", "dqn"],
        "hyperparameters": {
            "ppo": list(PPO_HYPERPARAMETERS),
            "dqn": list(DQN_HYPERPARAMETERS),
        },
        "overlays": [
            {
                "id": "ev_preemption",
                "label": "EV preemption",
                "description": "Give green to an approaching emergency vehicle.",
                "params": {
                    "range_m": {"type": "float", "default": 200},
                    "priority": {"type": "int", "default": 100},
                },
            },
            {
                "id": "pedestrian_service",
                "label": "Pedestrian service",
                "description": "Serve a crossing once a pedestrian has waited long enough.",
                "params": {
                    "wait_s": {"type": "float", "default": 30},
                    "priority": {"type": "int", "default": 90},
                },
            },
            {
                "id": "mp_fallback",
                "label": "Max-Pressure fallback",
                "description": "Fill missing/invalid policy actions with Max-Pressure.",
                "params": {"priority": {"type": "int", "default": 10}},
            },
        ],
        "training": {
            "demand_levels": ["low", "medium", "peak", "rush_profile"],
            "scenarios": ["normal", "emergency", "pedestrians", "buses", "incident"],
        },
    }
