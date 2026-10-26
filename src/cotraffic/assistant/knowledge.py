"""What the assistant can look up: the result files of the project, read only.

Every lookup returns a :class:`Finding`: the facts an answer may quote (each a number with
its label and unit), a table to display, and a sentence written from those facts by code.
That sentence is the answer whenever the language model is absent or its text is
rejected, so an answer never depends on the model to be correct.
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from cotraffic.analysis.style import label
from cotraffic.assistant.vocabulary import (
    DEMAND_FR,
    HIGHER_IS_BETTER,
    METRIC_FR,
    NETWORK_FR,
    SCENARIO_FR,
)
from cotraffic.paths import DOCS_DIR, LOGS_DIR, SUMMARY_DIR


@dataclass
class Fact:
    label: str
    value: float
    unit: str = ""
    signed: bool = False  # the sign is part of the value (a bound of a difference)


@dataclass
class Finding:
    summary: str
    facts: list[Fact] = field(default_factory=list)
    table: pd.DataFrame | None = None
    source: str = ""
    found: bool = True


def fmt(value: float, decimals: int = 1) -> str:
    """French number format: 1 234,5."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    text = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return text.replace("-", "−") if value < 0 else text


def cell_name(network: str, scenario: str, demand: str) -> str:
    return (
        f"{NETWORK_FR.get(network, network)}, {SCENARIO_FR.get(scenario, scenario)}, "
        f"demande {DEMAND_FR.get(demand, demand)}"
    )


def metric_name(metric: str) -> tuple[str, str]:
    return METRIC_FR.get(metric, (metric.replace("_", " "), ""))


@functools.lru_cache(maxsize=1)
def summary() -> pd.DataFrame:
    return pd.read_csv(SUMMARY_DIR / "summary.csv")


@functools.lru_cache(maxsize=16)
def comparisons(metric: str) -> pd.DataFrame | None:
    path = SUMMARY_DIR / f"comparisons_{metric}.csv"
    return pd.read_csv(path) if path.is_file() else None


def available() -> dict[str, list[str]]:
    s = summary()
    return {
        col: sorted(s[col].unique())
        for col in ("network", "scenario", "demand", "method", "metric")
    }


def _cell(network: str, scenario: str, demand: str, metric: str) -> pd.DataFrame:
    s = summary()
    return s[
        (s.network == network)
        & (s.scenario == scenario)
        & (s.demand == demand)
        & (s.metric == metric)
    ]


def _missing(network: str, scenario: str, demand: str, metric: str) -> Finding:
    """Say what exists instead, so the user can rephrase."""
    s = summary()
    here = s[(s.network == network) & (s.metric == metric)]
    if here.empty:
        here = s[s.network == network]
    cells = sorted({f"{r.scenario}/{r.demand}" for r in here.itertuples()})
    hint = ", ".join(cells[:12]) if cells else "aucune"
    text = (
        f"Nous n'avons pas de résultat pour {cell_name(network, scenario, demand)} "
        f"({metric_name(metric)[0]}). Cellules évaluées sur ce réseau : {hint}."
    )
    if network == "real_district" and scenario == "pedestrians":
        text += (
            " Les piétons ne sont pas évalués sur le quartier : son import n'a presque pas de "
            "trottoirs (FAILURES F-011)."
        )
    return Finding(text, found=False, source="results/summary/summary.csv")


def ranking(
    network: str, scenario: str, demand: str, metric: str, methods: list[str] | None = None
) -> Finding:
    """All methods of a cell from best to worst on ``metric``."""
    rows = _cell(network, scenario, demand, metric)
    if methods:
        rows = rows[rows.method.isin(methods)]
    if rows.empty:
        return _missing(network, scenario, demand, metric)
    rows = rows.sort_values("mean", ascending=metric not in HIGHER_IS_BETTER)
    name, unit = metric_name(metric)
    facts = []
    # a short list reads better for a small model: every mean, the interval of the best
    facts = [Fact(f"{label(r.method)} : {name}", float(r.mean), unit) for r in rows.itertuples()]
    best = rows.iloc[0]
    facts += [
        Fact(f"{label(best.method)} : borne basse de l'IC 95 %", float(best.ci_lo), unit),
        Fact(f"{label(best.method)} : borne haute de l'IC 95 %", float(best.ci_hi), unit),
        Fact("nombre de contrôleurs comparés", float(len(rows))),
    ]
    others = ", ".join(
        f"{label(r.method)} {fmt(r.mean)} {unit}".strip() for r in rows.iloc[1:6].itertuples()
    )
    text = (
        f"Sur {cell_name(network, scenario, demand)}, le meilleur résultat pour le critère "
        f"« {name} » est celui de {label(best.method)} : {fmt(best['mean'])} {unit} "
        f"(IC 95 % [{fmt(best.ci_lo)} ; {fmt(best.ci_hi)}], {int(best.n)} simulations)."
    )
    if others:
        text += f" Suivent : {others}."
    table = pd.DataFrame(
        {
            "méthode": [label(m) for m in rows.method],
            f"{name} ({unit})" if unit else name: rows["mean"].round(1).to_numpy(),
            "IC 95 % bas": rows.ci_lo.round(1).to_numpy(),
            "IC 95 % haut": rows.ci_hi.round(1).to_numpy(),
            "simulations": rows.n.astype(int).to_numpy(),
        }
    )
    return Finding(text, facts, table, "results/summary/summary.csv")


def compare(
    method: str,
    network: str,
    scenario: str,
    demand: str,
    metric: str,
    reference: str | None = None,
) -> Finding:
    """``method`` against ``reference`` (default: the best classical controller of the cell)."""
    rows = _cell(network, scenario, demand, metric)
    if rows.empty or method not in set(rows.method):
        return _missing(network, scenario, demand, metric)
    name, unit = metric_name(metric)
    table = comparisons(metric)
    hit = None
    if table is not None:
        sel = table[
            (table.network == network)
            & (table.scenario == scenario)
            & (table.demand == demand)
            & (table.method == method)
        ]
        sel = sel[sel.reference == reference] if reference else sel[sel.kind == "best_baseline"]
        if not sel.empty:
            hit = sel.iloc[0]
    if hit is not None:
        ref = str(hit.reference)
        gain = float(hit.paired_improvement_pct)  # positive: better than the reference
        better = gain > 0
        facts = [
            Fact(f"{label(method)} : {name}", float(hit["mean"]), unit),
            Fact(f"{label(ref)} : {name}", float(hit.reference_mean), unit),
            Fact("écart apparié (%)", abs(gain), "%"),
            Fact("p de Holm", float(hit.p_holm)),
        ]
        lo, hi = sorted((-float(hit.paired_ci_hi), -float(hit.paired_ci_lo)))
        facts += [
            Fact(
                f"IC 95 % de l'écart {label(method)} moins {label(ref)}, borne basse", lo, "%", True
            ),
            Fact(
                f"IC 95 % de l'écart {label(method)} moins {label(ref)}, borne haute", hi, "%", True
            ),
        ]
        verdict = "mieux" if better else "moins bien"
        text = (
            f"Sur {cell_name(network, scenario, demand)}, {label(method)} fait "
            f"{fmt(abs(gain))} % {verdict} que {label(ref)} sur le {name} : "
            f"{fmt(hit['mean'])} contre {fmt(hit.reference_mean)} {unit}. Écart apparié par "
            f"graine de test ({label(method)} moins {label(ref)}) : IC 95 % [{fmt(lo)} ; "
            f"{fmt(hi)}] %, p de Holm {fmt(float(hit.p_holm), 3)}."
        )
        if not bool(hit.significant):
            text += " La différence n'est pas significative après correction de Holm."
        return Finding(text, facts, None, f"results/summary/comparisons_{metric}.csv")
    # no stored comparison: plain difference of the means
    if reference is None:
        baselines = rows[
            rows.method.isin(["ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp"])
        ]
        baselines = baselines[baselines.method != method]
        if baselines.empty:
            return ranking(network, scenario, demand, metric)
        best = baselines.sort_values("mean", ascending=metric not in HIGHER_IS_BETTER).iloc[0]
        reference = str(best.method)
    if reference not in set(rows.method):
        return _missing(network, scenario, demand, metric)
    m = float(rows[rows.method == method]["mean"].iloc[0])
    r = float(rows[rows.method == reference]["mean"].iloc[0])
    diff = 100.0 * (m - r) / r
    lower = diff < 0
    better = lower != (metric in HIGHER_IS_BETTER)
    facts = [
        Fact(f"{label(method)} : {name}", m, unit),
        Fact(f"{label(reference)} : {name}", r, unit),
        Fact("écart des moyennes (%)", abs(diff), "%"),
    ]
    text = (
        f"Sur {cell_name(network, scenario, demand)}, critère « {name} » : {label(method)} "
        f"{fmt(m)} {unit} contre {fmt(r)} {unit} pour {label(reference)}, soit "
        f"{fmt(abs(diff))} % {'plus bas' if lower else 'plus haut'}, donc "
        f"{'mieux' if better else 'moins bien'} (écart des moyennes, sans test apparié)."
    )
    return Finding(text, facts, None, "results/summary/summary.csv")


_EXPLANATION_FR = [
    ("switches to north-south green", "passe au vert nord-sud"),
    ("switches to east-west green", "passe au vert est-ouest"),
    ("keeps north-south green", "garde le vert nord-sud"),
    ("keeps east-west green", "garde le vert est-ouest"),
    ("halting on north-south", "véhicules arrêtés côté nord-sud"),
    ("halting on east-west", "véhicules arrêtés côté est-ouest"),
    ("switches to", "passe à"),
    ("keeps", "garde"),
    ("halting on", "véhicules arrêtés sur"),
    ("emergency vehicle", "véhicule d'urgence à"),
    ("m from the north", "m, venant du nord"),
    ("m from the south", "m, venant du sud"),
    ("m from the east", "m, venant de l'est"),
    ("m from the west", "m, venant de l'ouest"),
    ("shield: min green", "bouclier : vert minimum pas encore atteint"),
    ("shield: max green", "bouclier : vert maximum atteint"),
    ("shield: starvation", "bouclier : un mouvement attendait depuis trop longtemps"),
    ("shield: invalid", "bouclier : action invalide"),
]
_BLOCK_FR = {
    "local lanes": "ses voies entrantes",
    "phase and timers": "la phase en cours et ses minuteries",
    "neighbour messages": "les messages des voisins",
    "emergency vehicles": "le bloc véhicules d'urgence",
    "none": "aucun bloc en particulier",
}


def decision_logs() -> list[Path]:
    return sorted((LOGS_DIR / "decisions").glob("explained__*.csv"))


def decision(agent: str, network: str, time_s: float | None, junction: str | None) -> Finding:
    """The explained decision of one junction at one moment, from the decision logs."""
    logs = [p for p in decision_logs() if f"__{agent}__{network}__" in p.name]
    if not logs:
        names = ", ".join(p.stem.replace("explained__", "") for p in decision_logs()) or "aucun"
        return Finding(
            f"Pas de journal de décisions pour {label(agent)} sur "
            f"{NETWORK_FR.get(network, network)}. "
            f"Journaux disponibles : {names} (créés par `python -m cotraffic explain`).",
            found=False,
        )
    path = logs[0]
    log = pd.read_csv(path)
    if junction and junction.upper() in set(log.agent):
        log = log[log.agent == junction.upper()]
    if time_s is not None:
        row = log.iloc[(log.time - time_s).abs().argsort().iloc[0]]
    else:
        switched = log[log.explanation.str.startswith("switches")]
        row = (switched if not switched.empty else log).iloc[0]
    explanation = str(row.explanation)
    for en, fr in _EXPLANATION_FR:
        explanation = explanation.replace(en, fr)
    depends = "; ".join(_BLOCK_FR.get(b.strip(), b.strip()) for b in str(row.depends_on).split(";"))
    numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(row.explanation))]
    facts = [Fact("temps (s)", float(row.time), "s")] + [
        Fact("valeur de l'explication", n) for n in numbers
    ]
    _, _, scenario, demand, seed = path.stem.replace("explained__", "").split("__")
    text = (
        f"{label(agent)}, carrefour {row.agent}, à t = {fmt(float(row.time), 0)} s "
        f"({SCENARIO_FR.get(scenario, scenario)}, demande {DEMAND_FR.get(demand, demand)}, graine "
        f"{seed.lstrip('s')}) : {explanation}. La décision dépend surtout de {depends} "
        "(ce qui change la décision quand on le brouille)."
    )
    return Finding(text, facts, None, f"results/logs/decisions/{path.name}")


def importance(agent: str, network: str) -> Finding:
    path = SUMMARY_DIR / f"importance_{agent}_{network}.csv"
    if not path.is_file():
        have = ", ".join(
            p.stem.replace("importance_", "") for p in SUMMARY_DIR.glob("importance_*.csv")
        )
        return Finding(
            f"Pas de mesure d'importance pour {label(agent)} sur "
            f"{NETWORK_FR.get(network, network)}. "
            f"Disponibles : {have or 'aucune'}.",
            found=False,
        )
    t = pd.read_csv(path)
    facts, parts = [], []
    for r in t.itertuples():
        block = _BLOCK_FR.get(r.group, r.group)
        changed = 100 * float(r.action_change_rate_active)
        facts += [
            Fact(f"{block} : décisions changées (%)", changed, "%"),
            Fact(
                f"{block} : hausse du temps de trajet (%)", float(r.travel_time_increase_pct), "%"
            ),
        ]
        part = (
            f"brouiller {block} change {fmt(changed, 0)} % des décisions et "
            f"{'augmente' if r.travel_time_increase_pct >= 0 else 'baisse'} le temps de trajet de "
            f"{fmt(abs(float(r.travel_time_increase_pct)))} %"
        )
        ev = getattr(r, "ev_delay_increase_pct", float("nan"))
        if isinstance(ev, float) and not math.isnan(ev):
            facts.append(Fact(f"{block} : hausse du retard des urgences (%)", ev, "%"))
            part += f" (retard des urgences {'+' if ev >= 0 else '−'}{fmt(abs(ev), 0)} %)"
        parts.append(part)
    text = (
        f"Importance des blocs d'observation de {label(agent)} sur "
        f"{NETWORK_FR.get(network, network)} : " + " ; ".join(parts) + "."
    )
    table = t[["group", "action_change_rate_active", "travel_time_increase_pct"]].copy()
    return Finding(text, facts, table, f"results/summary/{path.name}")


def failure(code: str) -> Finding:
    """One entry of docs/FAILURES.md (title and diagnosis)."""
    text = (DOCS_DIR / "FAILURES.md").read_text(encoding="utf-8")
    code = code.upper().replace(" ", "-")
    m = re.search(rf"^## {re.escape(code)} - (.+?)$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        codes = ", ".join(sorted(set(re.findall(r"^## (F-\d+)", text, re.MULTILINE))))
        return Finding(f"{code} n'existe pas. Entrées : {codes}.", found=False)
    title, body = m.group(1).strip(), m.group(2)
    body = re.sub(r"\s+", " ", body).strip()
    numbers = [
        float(x.replace(" ", "")) for x in re.findall(r"\d[\d ]*(?:\.\d+)?", body + " " + title)
    ]
    return Finding(
        f"{code} - {title} (registre des échecs, en anglais) : {body}",
        [Fact("valeur du registre", n) for n in numbers],
        None,
        "docs/FAILURES.md",
    )
