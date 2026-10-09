"""Answer a question about the results, in French.

1. Read the question into a :class:`Query` by keyword matching; the language model (JSON
   constrained to the values that exist in our results) reads only a question the keywords
   cannot classify (see :func:`read_question` for why).
2. Look the answer up in the result files (:mod:`cotraffic.assistant.knowledge`).
3. Let the model phrase it from those facts. Its text is kept only if every number in it
   is one of the facts; otherwise, or without a model, the sentence written by code is
   the answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from cotraffic.assistant import knowledge
from cotraffic.assistant.llm import LLMUnavailableError, LocalLLM
from cotraffic.assistant.vocabulary import (
    DEMANDS,
    METHODS,
    METRICS,
    NETWORKS,
    SCENARIOS,
    find_all,
    normalise,
)

TABLES = {"network": NETWORKS, "scenario": SCENARIOS, "demand": DEMANDS, "metric": METRICS}
INTENTS = ("best", "compare", "values", "decision", "importance", "failure", "help")
UNSPECIFIED = "unspecified"
DEMAND_ORDER = ("peak", "medium", "low", "rush_profile")
# the measure that matters most in a scenario, when the question names none
SCENARIO_METRIC = {
    "emergency": "ev_delay",
    "pedestrians": "ped_mean_waiting_time",
    "buses": "bus_delay",
}
# the demand level the report studies a scenario at (section 8.7: people at medium demand)
SCENARIO_DEMAND = {"pedestrians": "medium", "buses": "medium"}
HELP = (
    "Je réponds à partir des résultats du projet. Exemples : « Quel contrôleur est le "
    "meilleur à la pointe sur la grille ? », « Compare COOP et MP sur le quartier », « Quel "
    "est le retard des ambulances avec EV-RULE-MP ? », « Pourquoi COOP-FULL garde le vert au "
    "carrefour C1 à 600 s ? », « Sur quoi COOP-FULL fonde ses décisions ? », « Explique "
    "F-014 »."
)


@dataclass
class Query:
    intent: str = "help"
    network: str | None = None
    scenario: str | None = None
    demand: str | None = None
    metric: str | None = None
    methods: list[str] = field(default_factory=list)
    failure_code: str | None = None
    time_s: float | None = None
    junction: str | None = None


@dataclass
class Reply:
    text: str
    finding: knowledge.Finding
    query: Query
    read_by: str  # "modèle local" or "mots-clés"
    written_by: str  # "modèle local" or "code"
    note: str = ""


def parse_rules(question: str) -> tuple[Query, set[str]]:
    """Keyword reading of the question; also returns the fields the user wrote explicitly."""
    norm = normalise(question)
    q = Query()
    explicit: set[str] = set()
    q.methods = find_all(question, METHODS)
    for name, table in TABLES.items():
        values = find_all(question, table)
        if values:
            setattr(q, name, values[0])
            if len(values) == 1:  # named once: unambiguous
                explicit.add(name)
    if q.methods:
        explicit.add("methods")
    code = re.search(r"\bf ?-? ?(\d{3})\b", norm)
    m_time = re.search(r"(\d+(?:[.,]\d+)?)\s*(min|minutes?|s|sec|secondes?)\b", norm)
    if m_time:
        value = float(m_time.group(1).replace(",", "."))
        q.time_s = value * 60 if m_time.group(2).startswith("min") else value
    m_junction = re.search(r"\b([A-H][0-9])\b", question)
    if m_junction:
        q.junction = m_junction.group(1)
    if code:
        q.intent, q.failure_code = "failure", f"F-{code.group(1)}"
        explicit.add("intent")
    elif re.search(r"importan|sur quoi|depend|quels? blocs?|s.appuie", norm):
        q.intent = "importance"
        explicit.add("intent")
    elif re.search(r"pourquoi|decision|decide|choisi", norm) or q.junction:
        q.intent = "decision"
        explicit.add("intent")
    elif re.search(r"\bcontre\b|\bvs\b|compar|par rapport|mieux que|ecart", norm):
        q.intent = "compare" if q.methods else "best"
    elif re.search(
        r"meilleur|le mieux|le plus|quel controleur|qui gere|classement|gagne|pire", norm
    ):
        q.intent = "best"
    elif q.methods:
        q.intent = "values"
    elif explicit & {"network", "scenario", "demand", "metric"}:
        q.intent = "best"
    return q, explicit


def _schema() -> dict:
    have = knowledge.available()

    def enum(values):
        return {"type": "string", "enum": [*values, UNSPECIFIED]}

    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": list(INTENTS)},
            "network": enum(have["network"]),
            "scenario": enum(have["scenario"]),
            "demand": enum(have["demand"]),
            "metric": enum(have["metric"]),
            "methods": {"type": "array", "items": {"type": "string", "enum": have["method"]}},
            "failure_code": {"type": "string"},
            "time_s": {"type": "number"},
            "junction": {"type": "string"},
        },
        "required": ["intent", "network", "scenario", "demand", "metric", "methods"],
    }


_EXAMPLES = [
    (
        "Quel est le meilleur contrôleur à la pointe sur la grille ?",
        {
            "intent": "best",
            "network": "grid4x4",
            "scenario": UNSPECIFIED,
            "demand": "peak",
            "metric": UNSPECIFIED,
            "methods": [],
        },
    ),
    (
        "COOP fait-il mieux que Max-Pressure sur le quartier ?",
        {
            "intent": "compare",
            "network": "real_district",
            "scenario": UNSPECIFIED,
            "demand": UNSPECIFIED,
            "metric": UNSPECIFIED,
            "methods": ["coop", "mp"],
        },
    ),
]
ROUTER_PROMPT = (
    "You read questions about CoTraffic, a traffic-signal control study, and return JSON "
    "only. Intents: best (which controller is best in a situation), compare (one controller "
    "against another, or against the best classical controller), values (numbers for named "
    "controllers), decision (why an agent chose a phase at a junction and time), importance "
    "(which inputs an agent relies on), failure (an entry F-0xx of the failure log), help "
    "(anything else). Controllers: ft fixed-time, act actuated, mp Max-Pressure, ev_rule and "
    "ev_rule_mp emergency preemption, ped_rule_mp pedestrian rule, ind, coop, coop_eco, "
    "coop_full, coop_forecast learned agents. Networks: grid4x4 (the grid, 16 junctions), "
    'grid8x8 (64 junctions), real_district (the Tunis district). Use "unspecified" when '
    "the question does not say. Examples:\n"
    + "\n".join(f"{q!r} -> {json.dumps(a)}" for q, a in _EXAMPLES)
)


def parse_llm(question: str, llm: LocalLLM) -> Query:
    value = llm.chat_json(
        [{"role": "system", "content": ROUTER_PROMPT}, {"role": "user", "content": question}],
        _schema(),
    )
    q = Query(intent=value["intent"], methods=list(dict.fromkeys(value.get("methods", []))))
    for name in ("network", "scenario", "demand", "metric"):
        v = value.get(name, UNSPECIFIED)
        setattr(q, name, None if v == UNSPECIFIED else v)
    q.failure_code = value.get("failure_code") or None
    q.time_s = value.get("time_s")
    q.junction = value.get("junction") or None
    return q


def read_question(question: str, llm: LocalLLM | None) -> tuple[Query, str, str]:
    """(query, who read it, note).

    Keywords first: on our 15 test questions they read 14 correctly and the 3-billion
    parameter model alone 5, because it fills fields the question does not mention (a
    network, "normal" traffic). The model is asked only when the keywords cannot tell what
    the question is about. Even then a field the user named once comes from the keywords, a
    field named several times is chosen by the model among the values mentioned, and a
    network or demand level the question does not mention is left to the defaults.
    """
    rules, explicit = parse_rules(question)
    if llm is None or rules.intent != "help":
        return rules, "mots-clés", ""
    try:
        q = parse_llm(question, llm)
    except LLMUnavailableError as err:
        return rules, "mots-clés", f"modèle local indisponible ({err})"
    for name, table in TABLES.items():
        mentioned = find_all(question, table)
        if name in explicit or (mentioned and getattr(q, name) not in mentioned):
            setattr(q, name, getattr(rules, name))
        elif not mentioned and name in ("network", "demand"):
            setattr(q, name, None)  # not in the question: a guess of the model
    if rules.methods and not set(rules.methods) <= set(q.methods):
        q.methods = rules.methods
    if "intent" in explicit:
        q.intent = rules.intent
    q.failure_code = rules.failure_code or q.failure_code
    q.time_s = rules.time_s if rules.time_s is not None else q.time_s
    q.junction = rules.junction or q.junction
    if q.intent == "help" and rules.intent != "help":
        q.intent = rules.intent
    return q, "modèle local", ""


def complete(q: Query) -> Query:
    """Fill what the question left open with the report's main cells."""
    q.network = q.network or "grid4x4"
    if q.network == "real_district_ped":
        q.network = "real_district"  # the variant with sidewalks is not evaluated
    q.scenario = q.scenario or "normal"
    q.metric = q.metric or SCENARIO_METRIC.get(q.scenario, "mean_travel_time")
    if q.demand is None:
        s = knowledge.summary()
        here = s[(s.network == q.network) & (s.scenario == q.scenario) & (s.metric == q.metric)]
        order = (
            (SCENARIO_DEMAND[q.scenario],) + DEMAND_ORDER
            if q.scenario in SCENARIO_DEMAND
            else DEMAND_ORDER
        )
        q.demand = next((d for d in order if d in set(here.demand)), "peak")
    return q


def lookup(q: Query) -> knowledge.Finding:
    if q.intent == "failure" and q.failure_code:
        return knowledge.failure(q.failure_code)
    if q.intent == "importance":
        return knowledge.importance(
            q.methods[0] if q.methods else "coop_full", q.network or "grid4x4"
        )
    if q.intent == "decision":
        agent = next((m for m in q.methods if m in ("ind", "coop", "coop_full")), "coop_full")
        return knowledge.decision(agent, q.network or "grid4x4", q.time_s, q.junction)
    if q.intent == "help":
        return knowledge.Finding(HELP)
    q = complete(q)
    if q.intent == "compare" and q.methods:
        reference = q.methods[1] if len(q.methods) > 1 else None
        return knowledge.compare(q.methods[0], q.network, q.scenario, q.demand, q.metric, reference)
    if q.intent == "values" and q.methods:
        return knowledge.ranking(q.network, q.scenario, q.demand, q.metric, q.methods)
    return knowledge.ranking(q.network, q.scenario, q.demand, q.metric)


# a number not glued to a word (so "C1" or "F-014" in a name do not count twice), with the
# French thousands separator (space) and decimal comma
_NUMBER = re.compile(r"(?<![A-Za-z_\d])(?:\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,]\d+)?")


# numbers written in words, which a model uses as freely as digits ("un"/"une" are left
# out: they are mostly articles)
NUMBER_WORDS = {
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "treize": 13,
    "quatorze": 14,
    "quinze": 15,
    "seize": 16,
    "vingt": 20,
    "trente": 30,
    "quarante": 40,
    "cinquante": 50,
    "soixante": 60,
    "cent": 100,
    "mille": 1000,
}
_WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")s?\b", re.IGNORECASE)
# names that contain numbers: network sizes, the confidence level
_NAMES = re.compile(
    r"\d+\s*[×x]\s*\d+|(?:IC|intervalle de confiance)(?: à)? 95 ?%|\b(?:7|16|64) carrefours",
    re.IGNORECASE,
)


def numbers_in(text: str, words: bool = False) -> list[tuple[float, int]]:
    """(value, decimals) of every number written in ``text``; a minus sign right before the
    number makes it negative (not the hyphen of a name such as F-014)."""
    out = []
    for match in _NUMBER.finditer(text):
        raw = match.group(0)
        before = text[max(0, match.start() - 2) : match.start()]
        negative = before[-1:] in ("-", "−") and (len(before) < 2 or not before[0].isalnum())
        raw = re.sub(r"[   ]", "", raw).replace(",", ".")
        raw = raw.rstrip(".")
        if not raw:
            continue
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        try:
            value = float(raw)
        except ValueError:
            continue
        out.append((-value if negative else value, decimals))
    if words:
        out += [(float(NUMBER_WORDS[m.group(1).lower()]), 0) for m in _WORD.finditer(text)]
    return out


def grounded(text: str, finding: knowledge.Finding, question: str) -> bool:
    """True when every number of ``text`` comes from the facts, the code's own sentence or
    the question (the same value rounded to the decimals written). A signed fact (a bound
    of an interval) must keep its sign; a magnitude (expressed in words: "3,9 % plus lent")
    may be written either way."""
    signed = [f.value for f in finding.facts if f.signed]
    signed += [v for v, _ in numbers_in(_NAMES.sub(" ", finding.summary)) if v < 0]
    magnitudes = [abs(f.value) for f in finding.facts if not f.signed]
    magnitudes += [abs(v) for v, _ in numbers_in(_NAMES.sub(" ", finding.summary)) if v >= 0]
    magnitudes += [abs(v) for v, _ in numbers_in(_NAMES.sub(" ", question), words=True)]
    text = _NAMES.sub(" ", text)  # "grille 4×4", "IC 95 %" name things, they are not results

    def close(a: float, b: float, decimals: int) -> bool:
        return abs(round(a, decimals) - b) < 10 ** (-decimals) / 2 + 1e-9

    for value, decimals in numbers_in(text, words=True):
        if any(close(s, value, decimals) for s in signed):
            continue
        if any(close(m, abs(value), decimals) for m in magnitudes) and not any(
            close(abs(s), abs(value), decimals) and value != 0 and (s < 0) != (value < 0)
            for s in signed
        ):
            continue
        return False
    return True


WRITER_PROMPT = """Tu es l'assistant du projet CoTraffic (contrôle des feux de circulation par \
agents d'apprentissage). Réponds en français, en 2 à 4 phrases claires, uniquement à partir \
des FAITS fournis. Recopie les nombres exactement comme dans les faits, avec leur signe ; \
n'invente aucun nombre, aucune méthode, aucun résultat. Si les faits ne répondent pas à la \
question, dis-le simplement. FT (feux fixes), ACT (feux actionnés), MP (Max-Pressure), \
EV-RULE, EV-RULE-MP et PED-RULE-MP sont des contrôleurs classiques ; IND, COOP, COOP-ECO, \
COOP-FULL et COOP + forecast sont des agents d'apprentissage."""


def phrase(question: str, finding: knowledge.Finding, llm: LocalLLM) -> str:
    def value(f: knowledge.Fact) -> str:
        decimals = 0 if float(f.value).is_integer() else 3 if abs(f.value) < 0.1 else 1
        return f"{knowledge.fmt(f.value, decimals)} {f.unit}".rstrip()

    facts = "\n".join(f"- {f.label} = {value(f)}" for f in finding.facts[:40])
    content = (
        f"Question : {question}\n\nRéponse de référence (exacte) : {finding.summary}\n\n"
        f"FAITS :\n{facts or '- (aucun nombre)'}"
    )
    return llm.chat(
        [{"role": "system", "content": WRITER_PROMPT}, {"role": "user", "content": content}],
        max_tokens=300,
    ).strip()


def ask(question: str, llm: LocalLLM | None = None, write: bool = True) -> Reply:
    """Answer ``question``. ``llm=None`` (or a model that is not running) uses keywords
    and the code's sentence only; ``write=False`` keeps the model for reading only."""
    q, read_by, note = read_question(question, llm)
    finding = lookup(q)
    if llm is None or not write or not finding.found or note:
        return Reply(finding.summary, finding, q, read_by, "code", note)
    try:
        text = phrase(question, finding, llm)
    except LLMUnavailableError as err:
        return Reply(finding.summary, finding, q, read_by, "code", f"rédaction impossible ({err})")
    if not text or len(text) > 1500 or not grounded(text, finding, question):
        return Reply(
            finding.summary,
            finding,
            q,
            read_by,
            "code",
            "texte du modèle écarté : un nombre ne venait pas des résultats",
        )
    return Reply(text, finding, q, read_by, "modèle local")
