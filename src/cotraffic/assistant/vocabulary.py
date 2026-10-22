"""Words people use for the project's entities, in French and English.

Used to read a request without the language model (keyword matching) and to name things
in answers. Patterns are tried in order, so a specific name comes before a general one
(``coop_full`` before ``coop``, ``ev_rule_mp`` before ``mp``).
"""

from __future__ import annotations

import re
import unicodedata

# (value, patterns) - regular expressions on the normalised text (lower case, no accents)
METHODS: list[tuple[str, tuple[str, ...]]] = [
    ("ev_rule_mp", (r"ev[ -_]?rule[ -_]?mp", r"preemption (sur|avec|\+) ?(mp|max)")),
    ("ped_rule_mp", (r"ped[ -_]?rule", r"regle (des |pour les )?pietons?")),
    ("ev_rule", (r"ev[ -_]?rule", r"preemption")),
    ("coop_forecast", (r"coop[ -_]?forecast", r"prevision", r"forecast")),
    ("coop_full", (r"coop[ -_]?full", r"agent complet", r"cooperati\w* complet")),
    ("coop_eco05", (r"coop[ -_]?eco[ -_]?0?[.,]?5", r"lambda ?=? ?0[.,]5")),
    ("coop_eco", (r"coop[ -_]?eco", r"\beco\b")),
    ("coop", (r"\bcoop\b", r"cooperati")),
    ("ind", (r"\bind\b", r"independant")),
    ("mp", (r"\bmp\b", r"max[ -]?pressure", r"max pression")),
    ("act", (r"\bact\b", r"actionne", r"actuated")),
    ("ft", (r"\bft\b", r"feux? fixes?", r"temps fixe", r"fixed[ -]time", r"webster")),
]
NETWORKS: list[tuple[str, tuple[str, ...]]] = [
    ("real_district_ped", (r"real_district_ped", r"quartier avec (des )?trottoirs")),
    ("grid8x8", (r"8 ?x ?8", r"grid8", r"64 carrefours", r"grande grille")),
    ("grid2x2", (r"2 ?x ?2", r"grid2")),
    ("grid4x4", (r"4 ?x ?4", r"grid4", r"\bgrille\b", r"\bgrid\b")),
    ("real_district", (r"quartier", r"tunis", r"district", r"reel")),
]
SCENARIOS: list[tuple[str, tuple[str, ...]]] = [
    ("comm_dropout_50", (r"50 ?% (des )?messages", r"comm[ -_]?dropout[ -_]?50")),
    ("comm_dropout_10", (r"10 ?% (des )?messages", r"comm[ -_]?dropout[ -_]?10")),
    ("comm_dropout_30", (r"messages? perdu", r"perte (de |des )?messages", r"comm[ -_]?dropout")),
    ("sensor_noise", (r"capteur", r"detecteur", r"sensor", r"panne")),
    ("incident", (r"accident", r"incident", r"voie bloquee", r"rue bloquee")),
    ("emergency", (r"ambulance", r"urgence", r"pompier", r"emergency", r"\bev\b")),
    ("pedestrians", (r"pieton", r"pedestrian", r"passages? pietons?")),
    ("buses", (r"\bbus\b", r"autobus", r"transport (en commun|public)")),
    ("normal", (r"normal", r"sans evenement")),
]
DEMANDS: list[tuple[str, tuple[str, ...]]] = [
    ("rush_profile", (r"profil", r"rush", r"monte", r"variable")),
    ("peak", (r"pointe", r"peak", r"sature", r"charge")),
    ("medium", (r"moyen", r"medium", r"normale")),
    ("low", (r"faible", r"low", r"creuse", r"leger")),
]
METRICS: list[tuple[str, tuple[str, ...]]] = [
    ("ped_mean_waiting_time", (r"attente (des |moyenne des )?pietons", r"pietons? attend")),
    ("ev_delay", (r"retard (des )?(ambulances?|urgences?|vehicules? d.urgence)", r"ev delay")),
    ("bus_delay", (r"retard (des )?bus",)),
    ("co2_total_kg", (r"co2", r"emission", r"pollution", r"carbone")),
    ("ssm_conflicts_per_1000_veh", (r"conflit", r"securite", r"collision")),
    ("throughput_per_h", (r"debit", r"throughput", r"vehicules? par heure")),
    ("mean_queue", (r"\bfiles?\b", r"queue", r"bouchon")),
    ("p95_waiting_time", (r"95", r"plus longue attente", r"equite")),
    ("mean_waiting_time", (r"attente", r"waiting")),
    ("mean_travel_time", (r"temps de trajet", r"trajet", r"travel", r"duree", r"rapide")),
]

METRIC_FR = {
    "mean_travel_time": ("temps de trajet moyen", "s"),
    "mean_waiting_time": ("attente moyenne", "s"),
    "mean_queue": ("file moyenne", "véhicules"),
    "throughput_per_h": ("débit", "véh/h"),
    "co2_total_kg": ("CO2 émis sur l'heure mesurée", "kg"),
    "ev_delay": ("retard des véhicules d'urgence", "s"),
    "bus_delay": ("retard des bus", "s"),
    "ped_mean_waiting_time": ("attente moyenne des piétons", "s"),
    "p95_waiting_time": ("attente au 95e centile", "s"),
    "ssm_conflicts_per_1000_veh": ("conflits pour 1 000 véhicules", ""),
}
HIGHER_IS_BETTER = {"throughput_per_h"}
NETWORK_FR = {
    "grid2x2": "la grille 2×2",
    "grid4x4": "la grille 4×4",
    "grid8x8": "la grille 8×8",
    "real_district": "le quartier de Tunis",
    "real_district_ped": "le quartier de Tunis avec trottoirs",
}
SCENARIO_FR = {
    "normal": "trafic normal",
    "incident": "accident",
    "emergency": "véhicules d'urgence",
    "pedestrians": "piétons",
    "buses": "bus",
    "sensor_noise": "pannes de capteurs",
    "comm_dropout_10": "10 % de messages perdus",
    "comm_dropout_30": "30 % de messages perdus",
    "comm_dropout_50": "50 % de messages perdus",
}
DEMAND_FR = {
    "low": "faible",
    "medium": "moyenne",
    "peak": "de pointe",
    "rush_profile": "en profil de pointe",
}


def normalise(text: str) -> str:
    """Lower case without accents, so that "Piétons" and "pietons" match the same pattern."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def find_all(text: str, table: list[tuple[str, tuple[str, ...]]]) -> list[str]:
    """Every value of ``table`` mentioned in ``text``, in order of first mention."""
    norm = normalise(text)
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for value, patterns in table:
        for pattern in patterns:
            for m in re.finditer(pattern, norm):
                if any(a < m.end() and m.start() < b for a, b in taken):
                    continue  # already part of a more specific match
                taken.append((m.start(), m.end()))
                found.append((m.start(), value))
    seen: list[str] = []
    for _, value in sorted(found):
        if value not in seen:
            seen.append(value)
    return seen


def find_first(text: str, table: list[tuple[str, tuple[str, ...]]]) -> str | None:
    values = find_all(text, table)
    return values[0] if values else None
