"""
agents/supervisor/supervisor.py
Orchestrates the slow layer (plan sections 4.1, 4.5):

- decides which agents are due (periodic tick, EV replan, pedestrian surge),
- builds one compact snapshot per tick (agents see the same world),
- calls each due agent through its LLM client with the blackboard context,
- runs every envelope through the arbiter,
- posts arbiter feedback and agent alerts to the blackboard,
- logs every call and outcome to JSONL.

No TraCI: the supervisor consumes the controller states the fast layer
already collected and returns accepted directives for the DirectiveLayer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from agents.llm.agent import AgentCall, LLMAgent
from agents.llm.client import CallLogger
from agents.llm.schemas import SchemaError
from agents.supervisor.arbiter import Arbiter, ArbiterResult
from agents.supervisor.blackboard import Blackboard
from environment.snapshot import build_snapshot


@dataclass
class SupervisorConfig:
    delta_s: float = 30.0           # periodic Operator tick
    ev_replan_s: float = 10.0       # Emergency replan while an EV is active
    pedestrian_interval_s: float = 30.0  # placeholder until S4 exists
    feedback_ttl_s: float = 60.0


class Supervisor:
    def __init__(self, agents: Mapping[str, LLMAgent], arbiter: Arbiter,
                 blackboard: Optional[Blackboard] = None,
                 config: Optional[SupervisorConfig] = None,
                 logger: Optional[CallLogger] = None,
                 neighbors: Optional[Mapping[str, Mapping[str, str]]] = None,
                 pedestrian_trigger: bool = False):
        self.agents = dict(agents)
        self.arbiter = arbiter
        self.blackboard = blackboard if blackboard is not None else Blackboard()
        self.config = config or SupervisorConfig()
        self.logger = logger
        self.neighbors = dict(neighbors or {})
        self.pedestrian_trigger = bool(pedestrian_trigger)
        self._last_run: Dict[str, float] = {}
        self.stats: Dict[str, int] = {"calls": 0, "fallbacks": 0, "tokens_in": 0, "tokens_out": 0}

    def _interval(self, role: str) -> float:
        if role == "emergency":
            return self.config.ev_replan_s
        if role == "pedestrian":
            return self.config.pedestrian_interval_s
        return self.config.delta_s

    def _due(self, role: str, t: float) -> bool:
        if role not in self.agents:
            return False
        last = self._last_run.get(role)
        return last is None or (t - last) >= self._interval(role)

    def _agent_due(self, role: str, t: float, evs: Sequence[Any]) -> bool:
        if role == "emergency":
            return bool(evs) and self._due(role, t)
        if role == "pedestrian":
            return self.pedestrian_trigger and self._due(role, t)
        return self._due(role, t)

    def should_run(self, t: float, evs: Sequence[Any] = ()) -> bool:
        return any(self._agent_due(role, t, evs) for role in self.agents)

    def run(self, t: float, states: Mapping[str, Mapping[str, Any]],
            evs: Sequence[Any] = (), alerts: Sequence[Mapping[str, Any]] = ()) -> List[ArbiterResult]:
        """Run every due agent once; returns successful arbiter results."""
        messages = self.blackboard.active(t)
        snapshot = build_snapshot(t, states, self.neighbors, evs, alerts, messages)
        results: List[ArbiterResult] = []

        for role, agent in self.agents.items():
            if not self._agent_due(role, t, evs):
                continue
            self._last_run[role] = t
            call = agent.ask(t, snapshot, messages)
            result, envelope_error = self._submit(role, call, t, states)
            self._log(t, call, result, envelope_error)
            if result is not None:
                results.append(result)
                self.blackboard.post_message(
                    "arbiter_result", "arbiter", t,
                    payload=result.feedback_payload(),
                    ttl_s=self.config.feedback_ttl_s)
                for alert in result.alerts:
                    self.blackboard.post_message(
                        str(alert.get("kind", "alert")), role, t,
                        payload={k: v for k, v in alert.items() if k != "kind"},
                        ttl_s=self.config.feedback_ttl_s)
        return results

    def _submit(self, role: str, call: AgentCall, t: float,
                states: Mapping[str, Mapping[str, Any]]):
        self.stats["calls"] += 1
        if call.response is not None:
            self.stats["tokens_in"] += call.response.tokens_in or 0
            self.stats["tokens_out"] += call.response.tokens_out or 0
        if call.failed:
            self.stats["fallbacks"] += 1
        try:
            return self.arbiter.submit(role, call.envelope, t, states), None
        except SchemaError as exc:
            return None, str(exc)

    def _log(self, t: float, call: AgentCall, result: Optional[ArbiterResult],
             envelope_error: Optional[str]) -> None:
        if self.logger is None:
            return
        response = call.response
        record: Dict[str, Any] = {
            "t": t,
            "agent": call.role,
            "prompt_hash": call.prompt_hash,
            "attempts": call.attempts,
            "error": call.error or envelope_error,
            "tokens_in": getattr(response, "tokens_in", None) if response else None,
            "tokens_out": getattr(response, "tokens_out", None) if response else None,
            "latency_s": getattr(response, "latency_s", None) if response else None,
            "raw_response": getattr(response, "raw", None) if response else None,
            "parsed": call.envelope,
            "arbiter": result.to_record() if result is not None else None,
        }
        self.logger.log(record)
