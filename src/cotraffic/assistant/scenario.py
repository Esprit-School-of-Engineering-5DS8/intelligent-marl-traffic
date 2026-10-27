"""Turn a request in plain words into a run of the side-by-side demo.

"Montre MP contre COOP-FULL à Tunis avec un accident et des piétons" becomes the
command ``python scripts/demo_side_by_side.py --left mp --right coop_full --net
tunis --scenarios emergency buses pedestrians incident --follow-incident``.

Keyword matching reads the request; when it recognises nothing, the language model fills a
JSON object restricted to the values the demo accepts. The result is then checked against
what exists (trained agents, networks with sidewalks) and corrected with a note, so the
command always runs.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from cotraffic.assistant.llm import LLMUnavailableError, LocalLLM
from cotraffic.assistant.vocabulary import (
    DEMANDS,
    METHODS,
    NETWORKS,
    SCENARIOS,
    find_all,
    find_first,
    normalise,
)
from cotraffic.paths import REPO_ROOT, default_checkpoint

BASELINES = ("ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp")
LEARNED = ("ind", "coop", "coop_eco", "coop_eco05", "coop_full", "coop_forecast")
DEMO_NETWORKS = ("grid3x3", "monaco", "tunis", "tunis")
DEMO_SCENARIOS = ("emergency", "buses", "pedestrians", "incident", "sensor_noise")
DEMO_DEMANDS = ("low", "medium", "peak", "rush_profile")


@dataclass
class DemoSpec:
    left: str = "mp"
    right: str = "coop_full"
    network: str = "tunis"
    demand: str = "peak"
    scenarios: list[str] = field(default_factory=lambda: ["emergency", "buses"])
    seed: int = 3
    follow_ev: bool = False
    follow_incident: bool = False
    quick: bool = False


@dataclass
class DemoPlan:
    spec: DemoSpec
    command: list[str]
    notes: list[str]
    read_by: str


def parse_rules(text: str) -> tuple[DemoSpec, set[str]]:
    """Keyword reading of the request; also returns the fields written explicitly."""
    norm = normalise(text)
    spec = DemoSpec()
    explicit: set[str] = set()
    methods = [m for m in find_all(text, METHODS) if m in BASELINES + LEARNED]
    if len(methods) >= 2:
        spec.left, spec.right = methods[0], methods[1]
        explicit |= {"left", "right"}
    elif methods:
        if methods[0] in LEARNED:
            spec.right = methods[0]
            explicit.add("right")
        else:
            spec.left = methods[0]
            explicit.add("left")
    network = find_first(text, NETWORKS)
    if network in DEMO_NETWORKS:
        spec.network = network
        explicit.add("network")
    demand = find_first(text, DEMANDS)
    if demand:
        spec.demand = demand
        explicit.add("demand")
    scenarios = [s for s in find_all(text, SCENARIOS) if s in DEMO_SCENARIOS]
    if scenarios:
        spec.scenarios = scenarios
        explicit.add("scenarios")
    if "incident" in spec.scenarios:
        spec.follow_incident = True
    if "emergency" in spec.scenarios and re.search(r"suiv|\bsuit\b|\bsuis\b|camera|follow", norm):
        spec.follow_ev = True
    if re.search(r"\bcourt|rapide|vite|quick|\bteste?r?\b", norm):
        spec.quick = True
    seed = re.search(r"(?:graine|seed)\s*(\d+)", norm)
    if seed:
        spec.seed = int(seed.group(1))
        explicit.add("seed")
    return spec, explicit


def _schema() -> dict:
    controllers = list(BASELINES + LEARNED)
    return {
        "type": "object",
        "properties": {
            "left": {"type": "string", "enum": controllers},
            "right": {"type": "string", "enum": controllers},
            "network": {"type": "string", "enum": list(DEMO_NETWORKS)},
            "demand": {"type": "string", "enum": list(DEMO_DEMANDS)},
            "scenarios": {
                "type": "array",
                "items": {"type": "string", "enum": list(DEMO_SCENARIOS)},
            },
            "seed": {"type": "integer", "minimum": 0, "maximum": 99},
            "follow_ev": {"type": "boolean"},
            "follow_incident": {"type": "boolean"},
            "quick": {"type": "boolean"},
        },
        "required": [
            "left",
            "right",
            "network",
            "demand",
            "scenarios",
            "follow_ev",
            "follow_incident",
            "quick",
        ],
    }


PROMPT = """You configure a traffic-simulation demo that shows two signal controllers side \
by side on the same traffic. Return JSON only. Controllers: ft fixed-time, act actuated, mp \
Max-Pressure, ev_rule_mp Max-Pressure with emergency preemption, ped_rule_mp Max-Pressure \
with a pedestrian rule, ind / coop / coop_full learned agents (coop_full handles emergency \
vehicles, pedestrians and buses). "left" is the classical controller, "right" the learned \
agent, unless the request says otherwise. Networks: tunis (Tunis district), \
tunis (Tunis with sidewalks, needed for pedestrians), grid3x3, monaco. \
Scenarios: emergency (ambulances), buses, pedestrians, incident (accident), sensor_noise. \
follow_ev: camera follows ambulances. follow_incident: camera on the accident. quick: short \
episode. Defaults: left mp, right coop_full, network tunis, demand peak, scenarios \
emergency and buses, seed 3."""


def parse_llm(text: str, llm: LocalLLM) -> DemoSpec:
    value = llm.chat_json(
        [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}], _schema()
    )
    return DemoSpec(
        left=value["left"],
        right=value["right"],
        network=value["network"],
        demand=value["demand"],
        scenarios=list(dict.fromkeys(value["scenarios"])) or ["emergency", "buses"],
        seed=int(value.get("seed", 3)),
        follow_ev=bool(value["follow_ev"]),
        follow_incident=bool(value["follow_incident"]),
        quick=bool(value["quick"]),
    )


def check(spec: DemoSpec) -> list[str]:
    """Make ``spec`` runnable; returns what was changed and why."""
    notes = []
    if "pedestrians" in spec.scenarios and spec.network == "tunis":
        spec.network = "tunis"
        notes.append(
            "Piétons demandés sur le quartier : réseau tunis (le quartier avec "
            "trottoirs, démonstration seulement)."
        )
    if spec.network == "tunis" and "pedestrians" not in spec.scenarios:
        spec.scenarios.append("pedestrians")  # the reason this variant exists
    for side in ("left", "right"):
        method = getattr(spec, side)
        if method in LEARNED and not default_checkpoint(method, spec.network).is_file():
            setattr(spec, side, "coop_full")
            notes.append(
                f"{method} n'est pas entraîné pour {spec.network} : remplacé par coop_full."
            )
    if spec.left == spec.right:
        spec.left = "mp" if spec.right != "mp" else "ft"
        notes.append(f"Les deux fenêtres avaient le même contrôleur : à gauche, {spec.left}.")
    if spec.follow_incident and "incident" not in spec.scenarios:
        spec.scenarios.append("incident")
    if spec.follow_ev and "emergency" not in spec.scenarios:
        spec.scenarios.append("emergency")
    if spec.follow_ev and spec.follow_incident:
        notes.append(
            "La caméra suit d'abord les ambulances, puis l'accident quand elles sont arrivées."
        )
    return notes


def command(spec: DemoSpec) -> list[str]:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "demo_side_by_side.py"),
        "--left",
        spec.left,
        "--right",
        spec.right,
        "--net",
        spec.network,
        "--demand",
        spec.demand,
        "--seed",
        str(spec.seed),
        "--scenarios",
        *spec.scenarios,
    ]
    if spec.follow_ev:
        cmd.append("--follow-ev")
    if spec.follow_incident:
        cmd.append("--follow-incident")
    if spec.quick:
        cmd.append("--quick")
    return cmd


def plan_demo(text: str, llm: LocalLLM | None = None) -> DemoPlan:
    rules, explicit = parse_rules(text)
    spec, read_by, notes = rules, "mots-clés", []
    # as for questions, keywords first (6 test demo requests read correctly out of 6, the
    # model alone 4): the model is asked only when no controller, network or event was recognised
    if llm is not None and not explicit and not rules.follow_incident and not rules.quick:
        try:
            spec = parse_llm(text, llm)
            read_by = "modèle local"
            for name in explicit:
                setattr(spec, name, getattr(rules, name))
            spec.follow_incident = spec.follow_incident or rules.follow_incident
            spec.follow_ev = spec.follow_ev or rules.follow_ev
            spec.quick = spec.quick or rules.quick
        except LLMUnavailableError as err:
            notes.append(f"Modèle local indisponible, lecture par mots-clés ({err}).")
    notes += check(spec)
    return DemoPlan(spec, command(spec), notes, read_by)
