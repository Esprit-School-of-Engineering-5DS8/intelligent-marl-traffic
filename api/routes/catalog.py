"""Dynamic catalog and scenario configuration for the dashboard.

Serves live network geometry/bbox, agent counts, checkpoint status from filesystem,
and runnable/disabled status.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from api import policy
from api.policy import LABELS, LEARNED, METHODS, NETWORKS
from cotraffic import config
from cotraffic.networks.build import ensure_network
from cotraffic.paths import CHECKPOINTS_DIR, default_checkpoint

router = APIRouter(tags=["catalog"])

# Measured baseline wall times for 3-minute runs (from BENCHMARK_REDESIGN.md)
MEASURED_SECONDS_3MIN = {
    "grid2x2": 52,
    "grid3x3": 136,
    "tunis": 125,
    "monaco": 74,
}

NETWORK_TITLES = {
    "grid2x2": "Grid 2×2",
    "grid3x3": "Grid 3×3",
    "tunis": "Tunis Corridor",
    "monaco": "Monaco Principality",
}

NETWORK_DESCRIPTIONS = {
    "grid2x2": "4 intersections, synthetic arterial grid for rapid debugging and demonstration.",
    "grid3x3": "9 intersections, standard small benchmark grid for MARL coordination.",
    "tunis": "Central Tunis city network (lake, medina, Bourguiba, El Menzah — 13 TLS).",
    "monaco": "Port Hercule to Monte-Carlo arterial network with complex geometry.",
}


@lru_cache(maxsize=8)
def _network_metadata(name: str) -> dict[str, Any]:
    net_path = ensure_network(name)
    tree = ET.parse(net_path)
    root = tree.getroot()

    location = root.find("location")
    bounds = {"west": 0.0, "south": 0.0, "east": 0.0, "north": 0.0}
    orig_bounds = None
    if location is not None:
        conv = location.get("convBoundary", "0,0,0,0").split(",")
        if len(conv) == 4:
            bounds = {
                "west": float(conv[0]),
                "south": float(conv[1]),
                "east": float(conv[2]),
                "north": float(conv[3]),
            }
        orig = location.get("origBoundary")
        if orig:
            parts = orig.split(",")
            if len(parts) == 4:
                orig_bounds = {
                    "west": float(parts[0]),
                    "south": float(parts[1]),
                    "east": float(parts[2]),
                    "north": float(parts[3]),
                }

    cfg = config.load("networks", name)
    if "osm" in cfg and "bbox" in cfg["osm"]:
        bbox = cfg["osm"]["bbox"]
        real_geo_bounds = {
            "west": bbox[0],
            "south": bbox[1],
            "east": bbox[2],
            "north": bbox[3],
        }
    else:
        real_geo_bounds = orig_bounds or bounds

    edges = [e for e in root.findall("edge") if not e.get("id", "").startswith(":")]
    junctions = root.findall("junction")
    tls_junctions = [
        j for j in junctions if j.get("type") in ("traffic_light", "traffic_light_right_on_red")
    ]

    return {
        "network": name,
        "title": NETWORK_TITLES.get(name, name),
        "description": NETWORK_DESCRIPTIONS.get(name, ""),
        "tlsCount": len(tls_junctions),
        "edgeCount": len(edges),
        "junctionCount": len(junctions),
        "bounds": bounds,
        "geoBounds": real_geo_bounds,
        "measuredWallTimeS": MEASURED_SECONDS_3MIN.get(name, 120),
    }


def _get_agent_configs() -> list[dict[str, Any]]:
    from cotraffic import recipes

    agents = []
    for recipe in recipes.list_recipes():
        name = recipe["id"]
        if name == "base":
            continue
        cfg = recipe.get("config") or {}
        if name == "llm" or cfg.get("llm") is not None:
            family = "llm"
        elif recipe.get("source") == "recipe" and (name == "rl" or name.startswith("rl_")) and not recipe.get("error"):
            family = "rl"
        else:
            # Legacy variants (ind, coop_eco, ...) stay listed for named-run
            # compatibility but the UI hides them behind the `legacy` family.
            family = "legacy"
        agents.append(
            {
                "name": name,
                "label": LABELS.get(name, recipe.get("label", name)),
                "family": family,
                "algorithm": recipe.get("algorithm", "ppo"),
                "note": cfg.get("note")
                or cfg.get("description")
                or f"Variant {name}",
                "source": recipe.get("source", "preset"),
                "hash": recipe.get("hash", ""),
                "overlays": recipe.get("overlays") or [],
                "trainable": recipe.get("trainable", False),
                "error": recipe.get("error"),
            }
        )
    return agents


def _checkpoints_for_network(network: str) -> dict[str, Any]:
    res = {}
    for method in METHODS:
        ready, reason = policy.availability(method, network)
        ckpt = default_checkpoint(method, network) if method in LEARNED else None
        res[method] = {
            "method": method,
            "label": LABELS.get(method, method),
            "learned": method in LEARNED,
            "trained": ready if method in LEARNED else True,
            "available": ready,
            "reason": reason,
            "checkpointPath": str(ckpt) if ckpt and ckpt.exists() else None,
        }
    return res


@router.get("/api/catalog")
def get_catalog() -> dict[str, Any]:
    """Catalog of all networks, controllers, checkpoints and agent configurations."""
    networks_list = []
    for net in NETWORKS:
        meta = _network_metadata(net)
        controllers = _checkpoints_for_network(net)

        # Runnable verdict
        runnable = True
        disabled_reason = None
        if net == "monaco":
            # Monaco is runnable with ssm=False
            runnable = True
        networks_list.append(
            {
                **meta,
                "runnable": runnable,
                "disabledReason": disabled_reason,
                "controllers": controllers,
            }
        )

    return {
        "networks": networks_list,
        "agentConfigs": _get_agent_configs(),
        "controllers": [
            {
                "method": m,
                "label": LABELS.get(m, m),
                "learned": m in LEARNED,
            }
            for m in METHODS
        ],
    }
