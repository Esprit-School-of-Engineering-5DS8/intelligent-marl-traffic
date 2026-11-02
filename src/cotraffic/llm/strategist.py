"""The LLM in the decision loop: the network's strategy, chosen by the language model.

Every window (``window_s``, 300 s), the local model reads a short summary of the network
(halted vehicles, vehicles waiting to enter, queues, pedestrians, events) and chooses the
mode of the whole network for the next window, among three modes validated beforehand:

* ``equilibre``: the final candidate, COOP-FULL with a bias of ``beta`` towards Max-Pressure;
* ``fluidite``: Max-Pressure at every junction;
* ``agent``: COOP-FULL alone.

In every mode the emergency-vehicle rule (EV-RULE) and the shield of the environment stay
in force, so no answer of the model can produce an unsafe signal. The choice applies after
the time the model really took to answer (as for the advisor, llm/advised.py); an invalid
answer gets one correction attempt, then the current mode is kept. Every call is logged:
the state the model read, its answer, its reason, its latency and when it applied.

This is the role whose ceiling the strategy oracle measured on the validation seed
(scripts/strategy_oracle.py): the same three modes and the same window, so that the model
can be compared with the oracle (a perfect choice) and with its placebo (random choices).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

from cotraffic.controllers.combined import EvRuleGuide
from cotraffic.controllers.hybrid import HybridPolicy, insertion_backlog
from cotraffic.llm.client import LLMError, Ollama
from cotraffic.llm.prompts import PROMPTS, wrap
from cotraffic.llm.situation import events as network_events

MODES = ("equilibre", "fluidite", "agent")
DEFAULT_MODE = "equilibre"
LONG_QUEUE = 10  # halted vehicles from which a junction counts as having a long queue


@dataclass
class StrategistPrompt:
    version: str
    system: str
    reason_max: int = 120

    @classmethod
    def load(cls, version: str = "strategist-v1") -> StrategistPrompt:
        cfg = yaml.safe_load((PROMPTS / f"{version}.yaml").read_text(encoding="utf-8"))
        return cls(cfg["version"], cfg["system"].rstrip(), int(cfg.get("reason_max", 120)))

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(MODES)},
                "reason": {"type": "string", "maxLength": self.reason_max},
            },
            "required": ["mode", "reason"],
        }


@dataclass
class StrategyCall:
    time: float
    latency_s: float
    applies_at: float
    mode_before: str
    mode: str
    valid: bool
    reason: str = ""
    state: str = ""
    raw: str = ""
    error: str = ""
    attempts: int = 1
    prompt_tokens: int = 0
    output_tokens: int = 0


@dataclass
class _Snapshot:
    time: float = 0.0
    halted: float = 0.0
    backlog: float = 0.0


def network_state(env) -> dict[str, Any]:
    """What the strategist reads: network-level counts, from the controllers' own sensors."""
    halted_by = {
        tid: float(sum(env.meas.halting.get(ln, 0.0) for ln in inter.in_lanes))
        for tid, inter in env.intersections.items()
    }
    peds = {
        tid: int(sum(env.ped_waiting.get(c, 0.0) for c in inter.crossings))
        for tid, inter in env.intersections.items()
    }
    worst = max(halted_by, key=halted_by.get) if halted_by else ""
    return {
        "junctions": len(halted_by),
        "vehicles": int(env.conn.vehicle.getIDCount()),
        "halted": round(sum(halted_by.values())),
        "backlog": insertion_backlog(env),
        "queue_mean": round(sum(halted_by.values()) / max(1, len(halted_by)), 1),
        "queue_max": round(halted_by.get(worst, 0.0)),
        "queue_max_at": worst,
        "long_queues": sum(v >= LONG_QUEUE for v in halted_by.values()),
        "pedestrians": sum(peds.values()),
        "events": network_events(env),
    }


def state_text(s: dict[str, Any], now: float, end: float, mode: str, since: float,
               before: _Snapshot | None) -> str:  # fmt: skip
    """The summary sent to the model: a few lines, so that the answer comes fast."""
    ago = (lambda k: f" (5 min ago: {round(getattr(before, k))})") if before else (lambda k: "")
    kinds: dict[str, int] = {}
    for e in s["events"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    labels = {"emergency": "EMERGENCY VEHICLE", "incident": "INCIDENT (lane blocked)",
              "detector_fault": "DETECTOR FAULT", "message_loss": "MESSAGE LOSS",
              "pedestrians": "PEDESTRIAN CROWD"}  # fmt: skip
    events = ", ".join(f"{labels.get(k, k.upper())} x{n}" for k, n in kinds.items()) or "none"
    return "\n".join([
        f"t={int(now)}s of {int(end)}s; current mode: {mode} (since t={int(since)}s)",
        f"network: {s['junctions']} junctions, {s['vehicles']} vehicles, "
        f"{s['halted']} halted{ago('halted')}",
        f"vehicles waiting to enter the network: {s['backlog']}{ago('backlog')}",
        f"halted per junction: mean {s['queue_mean']}, max {s['queue_max']} at "
        f"{s['queue_max_at']}; junctions with >= {LONG_QUEUE} halted: {s['long_queues']} "
        f"of {s['junctions']}",
        f"pedestrians waiting: {s['pedestrians']}",
        f"events: {events}",
    ])  # fmt: skip


class LlmStrategist:
    """The strategy layer of HybridPolicy, driven by the language model."""

    name = "llm_strategist"

    def __init__(self, client: Ollama, prompt: StrategistPrompt, window_s: float = 300.0):
        self.client, self.prompt, self.window_s = client, prompt, float(window_s)

    def reset(self, env) -> None:
        self.current, self.since = DEFAULT_MODE, 0.0
        self.pending: tuple[str, float] | None = None
        self.next_call = 0.0
        self.before: _Snapshot | None = None
        self.calls: list[StrategyCall] = []
        self.decisions = dict.fromkeys(MODES, 0)
        self.switches = 0
        self.end = float(env.episode.end_time)

    def update(self, env) -> None:
        """Apply a decision whose time has come; ask the model when a window starts."""
        now = env.now
        if self.pending is not None and self.pending[1] <= now:
            mode, _ = self.pending
            if mode != self.current:
                self.switches += 1
                self.current, self.since = mode, now
            self.pending = None
        if now >= self.next_call:
            self.next_call = now + self.window_s
            self._ask(env)
        self.decisions[self.current] += 1

    def _ask(self, env) -> None:
        now = env.now
        s = network_state(env)
        text = state_text(s, now, self.end or now, self.current, self.since, self.before)
        self.before = _Snapshot(now, s["halted"], s["backlog"])
        messages = [{"role": "system", "content": self.prompt.system},
                    {"role": "user", "content": wrap(text)}]  # fmt: skip
        call = StrategyCall(now, 0.0, now, self.current, self.current, False, state=text)
        for attempt in range(2):
            call.attempts = attempt + 1
            try:
                reply = self.client.chat(messages, self.prompt.schema())
            except LLMError as err:  # server down or timeout: the current mode stays
                call.error = str(err)[:200]
                break
            call.latency_s += reply.latency_s
            call.prompt_tokens += reply.prompt_tokens
            call.output_tokens += reply.output_tokens
            call.raw = reply.text[:400]
            try:
                answer = json.loads(reply.text)
                mode = str(answer["mode"])
                if mode not in MODES:
                    raise ValueError(f"unknown mode {mode!r}")
                call.mode, call.reason, call.valid = mode, str(answer.get("reason", ""))[:200], True
                break
            except (ValueError, KeyError, TypeError) as err:
                call.error = str(err)[:200]
                messages = [*messages, {"role": "assistant", "content": reply.text[:400]},
                            {"role": "user", "content": "Not valid. Answer again with JSON "
                             "only, in the requested format."}]  # fmt: skip
        call.applies_at = now + call.latency_s
        if call.valid:
            self.pending = (call.mode, call.applies_at)
        self.calls.append(call)

    def modes(self, env) -> dict[str, str]:
        return dict.fromkeys(env.intersections, "mp") if self.current == "fluidite" else {}

    def summary(self) -> dict[str, Any]:
        n = max(1, sum(self.decisions.values()))
        lat = sorted(c.latency_s for c in self.calls if c.valid)
        return {
            "llm_calls": len(self.calls),
            "llm_valid_rate": round(sum(c.valid for c in self.calls) / max(1, len(self.calls)), 4),
            "llm_latency_p50_s": round(lat[len(lat) // 2], 3) if lat else float("nan"),
            "llm_latency_max_s": round(lat[-1], 3) if lat else float("nan"),
            "llm_mode_switches": self.switches,
            **{f"llm_share_{m}": round(self.decisions[m] / n, 4) for m in MODES},
            "llm_schedule": " ".join(c.mode if c.valid else "-" for c in self.calls),
        }


class LlmStrategyPolicy(HybridPolicy):
    """The candidate's layers, with the language model choosing the mode of the network."""

    def __init__(self, base, strategist: LlmStrategist, beta: float = 4.0, name: str = ""):
        super().__init__(base, strategist, mp_beta=beta, ev_guide=EvRuleGuide(),
                         name=name or "hybrid_h2_llmstrat")  # fmt: skip
        self.beta = float(beta)

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        self.strategy.update(env)
        self.mp_beta = self.beta if self.strategy.current == "equilibre" else 0.0
        return super().act(env, obs)

    def call_log(self) -> list[dict[str, Any]]:
        return [asdict(c) for c in self.strategy.calls]


@dataclass
class StrategistInfo:
    """What the result rows record about the model and the prompt."""

    model: str
    prompt: str
    window_s: float
    beta: float
    extra: dict[str, Any] = field(default_factory=dict)
