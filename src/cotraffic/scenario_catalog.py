"""What the dashboard's "new scenario" form offers: networks, events and controllers.

One list for the form (exported in meta.json), the API that checks a request and the
recorder that plays it (scripts/record_replay.py), so that the three always agree. The
events a network accepts come from its config (``unsupported_scenarios``); a learned
controller is offered only when its trained model is on disk.

The large imported cities (Paris, Barcelona) are played as in the exploratory
demonstration of scripts/bigcity.py: the lights the models cannot read keep their SUMO
program, and the demand is reduced to what the network carries. Nothing recorded here is a
result of the study: a replay is a demonstration of two controllers on one episode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cotraffic import config
from cotraffic.controllers.registry import BASELINES, CANDIDATE, LLM_CANDIDATE, ON_COOP_FULL
from cotraffic.paths import CHECKPOINTS_DIR, default_checkpoint

NETWORKS = ("grid4x4", "grid8x8", "real_district", "real_district_ped", "paris", "barcelona")
EVENTS = ("emergency", "pedestrians", "incident", "buses")
DEMANDS = ("low", "medium", "peak")
# demand factor of the big-city demonstration (results/bigcity/demo): at the planned
# demand Barcelona blocks under every controller, fixed time included (FAILURES F-016)
BIG_CITIES = {"paris": 0.5, "barcelona": 0.25}
# the controllers of that demonstration: the others were never run on these imports
BIG_CITY_METHODS = ("ft", "mp", "ev_rule_mp", "coop_full", CANDIDATE, LLM_CANDIDATE)
# the order of the form: our final controller first, then the references
ORDER = (CANDIDATE, LLM_CANDIDATE, "ft", "act", "mp", "ev_rule_mp", "ev_rule", "ped_rule_mp",
         "coop_full", "coop", "ind")  # fmt: skip
# big networks: a shorter recorded window keeps the replay file small
WINDOW_S = {"grid8x8": 300.0, "paris": 300.0, "barcelona": 240.0}
DEFAULT_WINDOW_S = 480.0


def is_big_city(network: str) -> bool:
    return network in BIG_CITIES


def demand_scale(network: str) -> float:
    return BIG_CITIES.get(network, 1.0)


def window(network: str) -> float:
    return WINDOW_S.get(network, DEFAULT_WINDOW_S)


def events(network: str) -> list[str]:
    """The events the network's config can generate."""
    unsupported = set(config.load("networks", network).get("unsupported_scenarios") or [])
    return [e for e in EVENTS if e not in unsupported]


def pedestrians(network: str) -> bool:
    """Whether people walk in this network (sidewalks and crossings in the SUMO file)."""
    return "pedestrians" in events(network)


def checkpoint(method: str, network: str) -> Path | None:
    """The trained model a controller needs on this network (None: it needs none)."""
    if method in ON_COOP_FULL:  # the candidate and its LLM version run on COOP-FULL
        return default_checkpoint("coop_full", network)
    if (CHECKPOINTS_DIR / method).is_dir():
        return default_checkpoint(method, network)
    return None


def available(method: str, network: str) -> bool:
    ckpt = checkpoint(method, network)
    return ckpt is None or ckpt.exists()


def methods(network: str, study: list[str]) -> list[str]:
    """The controllers offered on ``network``: the study's, the candidate and its LLM
    version, each one only with its trained model on disk."""
    pool = list(BIG_CITY_METHODS) if is_big_city(network) else [*study, CANDIDATE, LLM_CANDIDATE]
    pool = [m for m in dict.fromkeys(pool) if m in BASELINES or available(m, network)]
    rank = {m: i for i, m in enumerate(ORDER)}
    return sorted(pool, key=lambda m: (rank.get(m, len(ORDER)), m))


def catalog(study: list[str]) -> dict[str, Any]:
    """The form's options, as meta.json carries them."""
    return {
        "networks": [
            {
                "network": n,
                "events": events(n),
                "methods": methods(n, study),
                "scale": demand_scale(n),
                "window": window(n),
                "bigCity": is_big_city(n),
            }
            for n in NETWORKS
        ],
        "demands": list(DEMANDS),
        "candidate": CANDIDATE,
        "llm": LLM_CANDIDATE,
    }
