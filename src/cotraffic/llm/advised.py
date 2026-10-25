"""A learned policy that receives bounded advice from a strategic source.

At each decision (every 5 s):
1. advice whose activation time has come becomes active; expired advice is dropped;
2. if an event is new, or the period has elapsed, and no call happened in the last
   ``min_gap_s`` seconds, the source is asked; its reply is checked against the network
   and queued to become active ``delay`` seconds later (the measured latency of the call,
   or a fixed or zero delay for the sensitivity analysis);
3. the policy's logits receive ``beta * w`` on each advised phase, and the phase with the
   highest biased logit is requested. The shield then decides, as for every controller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cotraffic.controllers.base import Controller
from cotraffic.llm.advice import check
from cotraffic.llm.situation import observe
from cotraffic.llm.sources import AdviceSource


@dataclass
class Active:
    junction: str
    phase: int
    weight: float
    start: float
    end: float
    call: int


@dataclass
class AdvisorConfig:
    beta: float = 2.0  # largest logit bias (weight 1)
    period_s: float = 300.0  # periodic call (5 min)
    min_gap_s: float = 30.0  # rate limit between two calls
    latency: str = "measured"  # measured | zero | double | fixed:<seconds>


@dataclass
class CallLog:
    call: int
    time: float
    trigger: str
    latency_s: float
    delay_s: float
    valid: bool
    accepted: int
    rejected: list[str]
    meta: dict[str, Any] = field(default_factory=dict)
    advice: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


class AdvisedPolicy(Controller):
    needs_observations = True

    def __init__(
        self, base, source: AdviceSource, cfg: AdvisorConfig | None = None, name: str = ""
    ):
        super().__init__()
        self.base = base
        self.source = source
        self.cfg = cfg or AdvisorConfig()
        self.agent_cfg = base.agent_cfg
        self.name = name or f"{base.name}+{source.name}"
        self.calls: list[CallLog] = []
        self.active: list[Active] = []
        self.pending: list[Active] = []
        self.biased_decisions = 0
        self.changed_decisions = 0

    # ---------------------------------------------------------------- lifecycle
    def reset(self, env) -> None:
        self.base.reset(env)
        self.source.reset(int(getattr(env.episode, "sumo_seed", 0)))
        self.calls, self.active, self.pending = [], [], []
        self.biased_decisions = self.changed_decisions = 0
        self._last_call = -math.inf
        self._next_periodic = 0.0
        self._seen: set[str] = set()

    # ---------------------------------------------------------------- triggers
    def _trigger(self, env, situation_events: list[dict[str, Any]]) -> str | None:
        now = env.now
        if now - self._last_call < self.cfg.min_gap_s:
            return None
        for e in situation_events:
            key = e["kind"] if e["kind"] != "emergency" else f"emergency:{e['id']}"
            if e["kind"] == "pedestrians":
                key = "pedestrians:" + ",".join(sorted(c["j"] for c in e["crowds"]))
            if key not in self._seen:
                self._seen.add(key)
                return key
        if now >= self._next_periodic:
            return "periodic"
        return None

    def _delay(self, latency: float) -> float:
        mode = self.cfg.latency
        if mode == "measured":
            return latency
        if mode == "zero":
            return 0.0
        if mode == "double":
            return 2.0 * latency
        if mode.startswith("fixed:"):
            return float(mode.split(":", 1)[1])
        raise ValueError(f"unknown latency mode {mode!r}")

    def _ask(self, env, trigger: str) -> None:
        now = env.now
        situation = observe(env, trigger)
        reply = self.source.advise(situation)
        self._last_call = now
        if trigger == "periodic" or now >= self._next_periodic:
            self._next_periodic = now + self.cfg.period_s
        call = len(self.calls)
        delay = self._delay(reply.latency_s)
        log = CallLog(
            call, now, trigger, reply.latency_s, delay, reply.advice is not None, 0, [], reply.meta
        )
        if reply.advice is not None:
            checked = check(reply.advice, situation.n_phases())
            log.accepted = len(checked.items)
            log.rejected = checked.rejected
            log.reason = reply.advice.r
            log.advice = [i.model_dump() for i in checked.items]
            start = now + delay
            for item in checked.items:
                self.pending.append(Active(item.j, item.p, item.w, start, start + item.s, call))
        self.calls.append(log)

    # ---------------------------------------------------------------- decision
    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        import torch

        now = env.now
        ready = [a for a in self.pending if a.start <= now]
        self.pending = [a for a in self.pending if a.start > now]
        self.active = [a for a in self.active + ready if a.end > now]
        # a newer advice for a junction replaces the older one
        latest: dict[str, Active] = {}
        for a in self.active:
            if a.junction not in latest or a.call >= latest[a.junction].call:
                latest[a.junction] = a
        self.active = list(latest.values())

        from cotraffic.llm.situation import events

        trigger = self._trigger(env, events(env))
        if trigger is not None:
            self._ask(env, trigger)

        agents = list(obs)
        batch = np.stack([obs[a] for a in agents])
        policy = self.base.model.policy
        with torch.no_grad():
            logits = policy.get_distribution(policy.obs_to_tensor(batch)[0]).distribution.logits
        logits = logits.numpy().copy()
        plain = logits.argmax(axis=1)
        index = {a: i for i, a in enumerate(agents)}
        for a in self.active:
            i = index.get(a.junction)
            if i is not None and a.phase < logits.shape[1]:
                logits[i, a.phase] += self.cfg.beta * a.weight
                self.biased_decisions += 1
        chosen = logits.argmax(axis=1)
        self.changed_decisions += int((chosen != plain).sum())
        return {a: int(chosen[i]) for a, i in index.items()}

    def summary(self) -> dict[str, Any]:
        """LLM metrics of the episode, stored in the run's result row."""
        lat = [c.latency_s for c in self.calls if c.latency_s > 0]
        return {
            "llm_calls": len(self.calls),
            "llm_valid_rate": (sum(c.valid for c in self.calls) / len(self.calls))
            if self.calls
            else math.nan,
            "llm_fallbacks": sum(not c.valid for c in self.calls),
            "llm_items_accepted": sum(c.accepted for c in self.calls),
            "llm_items_rejected": sum(len(c.rejected) for c in self.calls),
            "llm_latency_p50_s": float(np.median(lat)) if lat else 0.0,
            "llm_latency_p95_s": float(np.percentile(lat, 95)) if lat else 0.0,
            "llm_prompt_tokens": sum(int(c.meta.get("prompt_tokens", 0)) for c in self.calls),
            "llm_output_tokens": sum(int(c.meta.get("output_tokens", 0)) for c in self.calls),
            "llm_biased_decisions": self.biased_decisions,
            "llm_changed_decisions": self.changed_decisions,
        }
