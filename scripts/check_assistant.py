"""Measure how well the assistant reads requests, and how fast, on this machine.

A fixed set of questions and demo requests, each with the reading we expect, is read
three ways: keywords only, the local model only, and the combination used by the
assistant (explicit words override the model). Then a few questions are answered in full
to time the writing step and count how often the model's text passes the number guard.

    python scripts/check_assistant.py [--model qwen2.5:3b] [--no-write]
"""

from __future__ import annotations

import argparse
import time

from cotraffic.assistant.ask import Query, ask, complete, parse_llm, parse_rules, read_question
from cotraffic.assistant.llm import LLMUnavailableError, LocalLLM
from cotraffic.assistant.scenario import check
from cotraffic.assistant.scenario import parse_llm as demo_llm
from cotraffic.assistant.scenario import parse_rules as demo_rules

QUESTIONS = [
    (
        "Quel est le meilleur contrôleur à la pointe sur la grille ?",
        dict(intent="best", network="grid4x4", scenario="normal", demand="peak"),
    ),
    (
        "Compare COOP et MP sur le quartier à la pointe",
        dict(intent="compare", network="real_district", demand="peak", methods=["coop", "mp"]),
    ),
    (
        "Quel est le retard des ambulances avec EV-RULE-MP ?",
        dict(intent="values", scenario="emergency", metric="ev_delay", methods=["ev_rule_mp"]),
    ),
    (
        "Qui gère le mieux les piétons ?",
        dict(intent="best", scenario="pedestrians", metric="ped_mean_waiting_time"),
    ),
    (
        "Quel contrôleur résiste le mieux aux pannes de capteurs ?",
        dict(intent="best", scenario="sensor_noise"),
    ),
    (
        "Est-ce que l'agent coopératif complet fait mieux que Max-Pressure avec les bus ?",
        dict(intent="compare", scenario="buses", methods=["coop_full", "mp"]),
    ),
    (
        "Combien de CO2 émet IND à la pointe sur la grille ?",
        dict(
            intent="values",
            network="grid4x4",
            demand="peak",
            metric="co2_total_kg",
            methods=["ind"],
        ),
    ),
    (
        "Pourquoi COOP-FULL passe au vert au carrefour B2 vers 20 min ?",
        dict(intent="decision", junction="B2", time_s=1200.0, methods=["coop_full"]),
    ),
    (
        "L'agent qui gère aussi les piétons et les urgences est-il meilleur que MP en cas "
        "d'accident ?",
        dict(intent="compare", scenario="incident", methods=["coop_full", "mp"]),
    ),
    ("Sur quoi COOP s'appuie pour décider ?", dict(intent="importance", methods=["coop"])),
    ("Explique l'échec F-009", dict(intent="failure", failure_code="F-009")),
    (
        "Quel contrôleur est le plus rapide sur la grande grille de 64 carrefours ?",
        dict(intent="best", network="grid8x8"),
    ),
    (
        "Et sur le quartier avec un accident, qui est le meilleur ?",
        dict(intent="best", network="real_district", scenario="incident"),
    ),
    (
        "Le débit de MP et d'ACT à demande faible sur la grille",
        dict(
            intent="values",
            network="grid4x4",
            demand="low",
            metric="throughput_per_h",
            methods=["mp", "act"],
        ),
    ),
    (
        "Quel est l'écart entre feux fixes et COOP-FULL à Tunis en heure de pointe ?",
        dict(intent="compare", network="real_district", demand="peak", methods=["ft", "coop_full"]),
    ),
]
DEMOS = [
    (
        "Montre MP contre COOP-FULL à Tunis avec un accident et des piétons",
        dict(
            left="mp",
            right="coop_full",
            network="real_district_ped",
            follow_incident=True,
            has={"incident", "pedestrians"},
        ),
    ),
    (
        "Ambulances sur la grille, préemption sur MP face à COOP-FULL, caméra sur les ambulances",
        dict(
            left="ev_rule_mp",
            right="coop_full",
            network="grid4x4",
            follow_ev=True,
            has={"emergency"},
        ),
    ),
    (
        "Une démo rapide avec des bus à demande moyenne",
        dict(demand="medium", quick=True, has={"buses"}),
    ),
    ("Feux fixes contre IND sur la grande grille", dict(left="ft", right="ind", network="grid8x8")),
    (
        "Compare l'agent indépendant et le coopératif sur le quartier",
        dict(left="ind", right="coop", network="real_district"),
    ),
    (
        "Tunis à l'heure de pointe avec un accident, graine 2",
        dict(network="real_district", demand="peak", seed=2, has={"incident"}),
    ),
]


def score_query(q: Query, expected: dict) -> list[str]:
    q = complete(q) if q.intent in ("best", "compare", "values") else q
    wrong = []
    for name, value in expected.items():
        got = getattr(q, name)
        if name == "methods":
            got = got[: len(value)]
        if got != value:
            wrong.append(f"{name}={got!r}")
    return wrong


def score_demo(spec, expected: dict) -> list[str]:
    check(spec)
    wrong = []
    for name, value in expected.items():
        if name == "has":
            if not value <= set(spec.scenarios):
                wrong.append(f"scenarios={spec.scenarios}")
        elif getattr(spec, name) != value:
            wrong.append(f"{name}={getattr(spec, name)!r}")
    return wrong


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=None)
    parser.add_argument("--no-write", action="store_true", help="skip the timing of answers")
    args = parser.parse_args()
    llm = LocalLLM(model=args.model) if args.model else LocalLLM()
    usable, message = llm.status()
    print(f"model: {message}")
    if not usable:
        llm = None

    rows = []
    for text, expected in QUESTIONS:
        rules = score_query(parse_rules(text)[0], expected)
        model = combined = ["(no model)"]
        t_read = float("nan")
        if llm:
            try:
                model = score_query(parse_llm(text, llm), expected)
            except LLMUnavailableError as err:
                model = [f"failed: {err}"]
            t0 = time.perf_counter()
            combined = score_query(read_question(text, llm)[0], expected)
            t_read = time.perf_counter() - t0
        rows.append((text, rules, model, combined, t_read))
    for text, expected in DEMOS:
        rules = score_demo(demo_rules(text)[0], expected)
        model = combined = ["(no model)"]
        t_read = float("nan")
        if llm:
            try:
                model = score_demo(demo_llm(text, llm), expected)
            except LLMUnavailableError as err:
                model = [f"failed: {err}"]
            from cotraffic.assistant.scenario import plan_demo

            t0 = time.perf_counter()
            combined = score_demo(plan_demo(text, llm).spec, expected)
            t_read = time.perf_counter() - t0
        rows.append((text, rules, model, combined, t_read))

    print("\n| request | keywords | model only | assistant | reading time (s) |")
    print("|---|---|---|---|---|")
    for text, rules, model, combined, t in rows:
        cell = lambda w: "ok" if not w else ", ".join(w)  # noqa: E731
        print(f"| {text} | {cell(rules)} | {cell(model)} | {cell(combined)} | {t:.1f} |")
    n = len(rows)
    for i, name in ((1, "keywords"), (2, "model only"), (3, "assistant")):
        print(f"{name}: {sum(not r[i] for r in rows)}/{n} read correctly")

    if llm and not args.no_write:
        kept, times = 0, []
        for text, _ in QUESTIONS[:6]:
            t0 = time.perf_counter()
            reply = ask(text, llm)
            times.append(time.perf_counter() - t0)
            kept += reply.written_by == "modèle local"
            print(f"\nQ: {text}\nA ({reply.written_by}): {reply.text}")
        print(
            f"\nfull answers: {kept}/{len(times)} written by the model (the others by code), "
            f"{min(times):.0f}-{max(times):.0f} s each"
        )


if __name__ == "__main__":
    main()
