"""Where advice comes from. The three sources share one interface, so that comparing them
changes only the source of the advice (same mechanism, frequency and latency):

* LlmSource - the local language model;
* RuleSource - hand-written rules applying the same principles as the prompt;
* RandomSource - placebo: random advice with the frequency and amplitude of the LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cotraffic.llm.advice import (
    MAX_ITEMS,
    Advice,
    AdviceError,
    Item,
    parse,
    schema_for,
    weight_of,
)
from cotraffic.llm.client import LLMError, Ollama
from cotraffic.llm.prompts import Prompt
from cotraffic.llm.situation import Situation

MAX_TEXT = 4000  # longer replies are refused before parsing (resource bound)


@dataclass
class SourceReply:
    advice: Advice | None
    latency_s: float
    meta: dict[str, Any] = field(default_factory=dict)


class AdviceSource:
    name = "none"

    def reset(self, seed: int) -> None:
        return None

    def advise(self, situation: Situation) -> SourceReply:
        return SourceReply(None, 0.0)


class LlmSource(AdviceSource):
    """One model call; if the reply is not a valid advice, one correction attempt, then
    nothing (the policy decides alone)."""

    def __init__(self, client: Ollama, prompt: Prompt):
        self.client = client
        self.prompt = prompt
        self.name = f"llm:{client.model}:{prompt.technique}"

    def advise(self, situation: Situation) -> SourceReply:
        n_phases = situation.n_phases()
        schema = schema_for(list(n_phases), max(n_phases.values()) - 1, self.prompt.reason_max)
        messages = self.prompt.messages(situation.to_text())
        meta: dict[str, Any] = {"attempts": 0, "prompt_tokens": 0, "output_tokens": 0}
        latency = 0.0
        for attempt in range(2):
            meta["attempts"] = attempt + 1
            try:
                reply = self.client.chat(messages, schema)
            except LLMError as err:
                meta["error"] = str(err)[:200]
                return SourceReply(None, latency, meta)
            latency += reply.latency_s
            meta["prompt_tokens"] += reply.prompt_tokens
            meta["output_tokens"] += reply.output_tokens
            meta["raw"] = reply.text[:600]
            if len(reply.text) > MAX_TEXT:
                meta["error"] = "reply too long"
                return SourceReply(None, latency, meta)
            try:
                return SourceReply(parse(reply.text), latency, meta)
            except AdviceError as err:
                meta["error"] = str(err)[:200]
                messages = [
                    *messages,
                    {"role": "assistant", "content": reply.text[:MAX_TEXT]},
                    {
                        "role": "user",
                        "content": "That reply is not valid. Answer again with JSON only, "
                        "matching the requested format and bounds.",
                    },
                ]
        return SourceReply(None, latency, meta)


class RuleSource(AdviceSource):
    """The prompt's principles as fixed rules (control: same mechanism, no language model)."""

    name = "rules"

    def __init__(self, crowd: int = 3, queue_ratio: float = 3.0, queue_min: int = 12):
        self.crowd = crowd
        self.queue_ratio = queue_ratio
        self.queue_min = queue_min

    def advise(self, situation: Situation) -> SourceReply:
        items: dict[str, Item] = {}

        def add(j: str, p: int, w: float, s: int) -> None:
            if j not in items or w > items[j].w:
                items[j] = Item(j=j, p=p, w=w, s=s)

        junctions = {j.id: j for j in situation.junctions}
        for e in situation.events:
            if e["kind"] == "emergency":
                for step in e["next"][:3]:  # green wave on the next junctions
                    add(step["j"], step["p"], weight_of(3), 60)
            elif e["kind"] == "incident":
                # drain the queue in front of the blocked lane: favour, at the junction it
                # leads to, the phase serving the most halted vehicles
                j = junctions.get(e["to"])
                if j is not None:
                    add(j.id, int(np.argmax(j.queues)), weight_of(2), 60)
            elif e["kind"] == "detector_fault":
                for approach in e["approaches"]:  # serve blind approaches from time to time
                    jid, side = approach.split(":")
                    j = junctions.get(jid)
                    if j is not None:
                        for p, sides in enumerate(j.phases):
                            if side in sides and p != j.phase and j.green_s >= 20:
                                add(jid, p, weight_of(2), 20)
            elif e["kind"] == "pedestrians":
                for crowd in e["crowds"]:
                    if crowd["n"] >= self.crowd:
                        j = junctions[crowd["j"]]
                        add(j.id, (j.phase + 1) % len(j.phases), weight_of(2), 20)
        for j in situation.junctions:  # a clearly neglected queue
            if len(j.queues) > 1:
                served = j.queues[j.phase]
                best = int(np.argmax(j.queues))
                if (
                    best != j.phase
                    and j.queues[best] >= self.queue_min
                    and (j.queues[best] >= self.queue_ratio * max(served, 1))
                ):
                    add(j.id, best, weight_of(1), 30)
        ranked = sorted(items.values(), key=lambda i: -i.w)
        advice = Advice(a=ranked[:MAX_ITEMS], r="rules")
        return SourceReply(advice, 0.0, {"items": len(advice.a)})


class RandomSource(AdviceSource):
    """Placebo: as many items, as strong and as long as the LLM's advice (distributions
    measured on validation), on random junctions and phases."""

    name = "random"

    def __init__(self, counts: list[int], weights: list[float], validities: list[int]):
        self.counts = counts or [0]
        self.weights = weights or [0.5]
        self.validities = validities or [60]
        self.rng = np.random.default_rng(0)

    def reset(self, seed: int) -> None:
        self.rng = np.random.default_rng(10_000 + seed)

    def advise(self, situation: Situation) -> SourceReply:
        n = int(self.rng.choice(self.counts))
        chosen = self.rng.choice(
            len(situation.junctions), size=min(n, len(situation.junctions)), replace=False
        )
        items = []
        for idx in chosen:
            j = situation.junctions[int(idx)]
            items.append(
                Item(
                    j=j.id,
                    p=int(self.rng.integers(len(j.phases))),
                    w=float(self.rng.choice(self.weights)),
                    s=int(self.rng.choice(self.validities)),
                )
            )
        return SourceReply(Advice(a=items, r="placebo"), 0.0, {"items": len(items)})


class FixedSource(AdviceSource):
    """Always the same advice (used to replay one advice in rollouts)."""

    name = "fixed"

    def __init__(self, advice: Advice, latency_s: float = 0.0):
        self.advice = advice
        self.latency_s = latency_s

    def advise(self, situation: Situation) -> SourceReply:
        return SourceReply(
            self.advice, self.latency_s, {"fixed": json.dumps(self.advice.model_dump())}
        )
