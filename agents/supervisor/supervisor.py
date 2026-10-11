"""
agents/supervisor/supervisor.py
Orchestrates the slow layer (plan sections 4.1, 4.5):

- classifies the network state (quiet / normal / congested) and adapts the
  invocation cadence accordingly (HiLLTS-style: 60 s stable, 30 s normal,
  15 s congested, immediate on code alerts),
- builds one compact snapshot per tick (agents see the same world),
- calls each due agent through its LLM client with the blackboard context,
  escalating the reasoning effort on congested snapshots,
- runs every envelope through the arbiter,
- posts arbiter feedback and agent alerts to the blackboard,
- logs every call and outcome to JSONL.

No TraCI: the supervisor consumes the controller states the fast layer
already collected and returns accepted directives for the DirectiveLayer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from agents.llm.agent import AgentCall, LLMAgent
from agents.llm.client import CallLogger
from agents.llm.schemas import SchemaError
from agents.supervisor.arbiter import Arbiter, ArbiterResult
from agents.supervisor.blackboard import Blackboard
from environment.snapshot import build_snapshot

COMPLEXITY_QUIET = "quiet"
COMPLEXITY_NORMAL = "normal"
COMPLEXITY_CONGESTED = "congested"


@dataclass
class SupervisorConfig:
    delta_s: float = 30.0           # periodic Operator tick (normal traffic)
    quiet_delta_s: float = 60.0     # tick when the whole grid is quiet
    congested_delta_s: float = 15.0  # tick while congested
    ev_replan_s: float = 10.0       # Emergency replan while an EV is active
    pedestrian_interval_s: float = 30.0  # placeholder until S4 exists
    feedback_ttl_s: float = 60.0
    max_calls: int = 0              # hard cap per run (0 = unlimited)
    quiet_queue_threshold: int = 8  # every axis below this = quiet
    congested_queue_threshold: int = 15  # any axis at/above this = congested
    base_effort: str = ""           # "" = client/provider default
    escalate_effort: str = "medium"  # used on congested snapshots ("" disables)
    # EV event triggers: run the Emergency agent immediately (not only on the
    # 10 s cadence) when a new EV appears, an EV's upcoming-TLS list changes
    # (it crossed a light or emerged from a junction) or its minimum ETA
    # crosses a threshold. Debounced by `ev_event_min_gap_s`.
    ev_event_triggers: bool = True
    ev_event_min_gap_s: float = 3.0
    ev_eta_thresholds: Tuple[float, ...] = (25.0, 15.0, 5.0)
    ev_eta_min_speed_m_s: float = 1.0  # ETA floor, matches the snapshot


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
        self._budget_logged = False
        self._ev_seen: Dict[str, Dict[str, Any]] = {}
        self._last_ev_event_t: float = float("-inf")
        self.stats: Dict[str, int] = {
            "calls": 0, "fallbacks": 0, "retries": 0, "escalated": 0,
            "tokens_in": 0, "tokens_out": 0, "tokens_cached": 0,
        }

    # ── complexity & cadence ────────────────────────────────────────────────

    @staticmethod
    def _max_axis_queue(states: Mapping[str, Mapping[str, Any]]) -> int:
        max_queue = 0
        for state in states.values():
            queues = state.get("lane_queues") or {}
            if queues:
                ns_lanes = state.get("ns_lanes") or ()
                ew_lanes = state.get("ew_lanes") or ()
                ns = sum(queues.get(lane, 0) or 0 for lane in ns_lanes)
                ew = sum(queues.get(lane, 0) or 0 for lane in ew_lanes)
                max_queue = max(max_queue, int(ns), int(ew))
            else:
                max_queue = max(max_queue,
                                int(state.get("ns_queue", 0) or 0),
                                int(state.get("ew_queue", 0) or 0))
        return max_queue

    def classify(self, t: float, states: Mapping[str, Mapping[str, Any]],
                 evs: Sequence[Any] = (), alerts: Sequence[Mapping[str, Any]] = ()) -> str:
        """quiet / normal / congested for cadence and effort selection."""
        if evs or alerts:
            return COMPLEXITY_CONGESTED
        traffic_messages = [m for m in self.blackboard.active(t) if m.kind != "arbiter_result"]
        if traffic_messages:
            return COMPLEXITY_CONGESTED
        max_queue = self._max_axis_queue(states)
        if max_queue >= self.config.congested_queue_threshold:
            return COMPLEXITY_CONGESTED
        if max_queue < self.config.quiet_queue_threshold:
            return COMPLEXITY_QUIET
        return COMPLEXITY_NORMAL

    def _interval(self, role: str, complexity: str) -> float:
        if role == "emergency":
            return self.config.ev_replan_s
        if role == "pedestrian":
            return self.config.pedestrian_interval_s
        if complexity == COMPLEXITY_QUIET:
            return self.config.quiet_delta_s
        if complexity == COMPLEXITY_CONGESTED:
            return self.config.congested_delta_s
        return self.config.delta_s

    def _effort_for(self, complexity: str) -> str:
        if complexity == COMPLEXITY_CONGESTED and self.config.escalate_effort:
            return self.config.escalate_effort
        return self.config.base_effort

    def _due(self, role: str, t: float, complexity: str) -> bool:
        if role not in self.agents:
            return False
        last = self._last_run.get(role)
        return last is None or (t - last) >= self._interval(role, complexity)

    def _agent_due(self, role: str, t: float, evs: Sequence[Any],
                   complexity: str, ev_event: bool = False) -> bool:
        if role == "emergency":
            return bool(evs) and (ev_event or self._due(role, t, complexity))
        if role == "pedestrian":
            return self.pedestrian_trigger and self._due(role, t, complexity)
        return self._due(role, t, complexity)

    # ── EV event triggers ────────────────────────────────────────────────────

    @staticmethod
    def _ev_field(ev: Any, name: str, default: Any = None) -> Any:
        if isinstance(ev, Mapping):
            return ev.get(name, default)
        return getattr(ev, name, default)

    def _ev_signature(self, evs: Sequence[Any]) -> Dict[str, Dict[str, Any]]:
        signature: Dict[str, Dict[str, Any]] = {}
        for ev in evs:
            veh_id = str(self._ev_field(ev, "veh_id", "") or "")
            speed = max(float(self._ev_field(ev, "speed_m_s", 0.0) or 0.0),
                        self.config.ev_eta_min_speed_m_s)
            next_tls = tuple(self._ev_field(ev, "next_tls", ()) or ())
            tls_ids = tuple(str(self._ev_field(nxt, "tls_id", "")) for nxt in next_tls)
            etas = [float(self._ev_field(nxt, "distance_m", 0.0) or 0.0) / speed
                    for nxt in next_tls]
            signature[veh_id] = {"tls": tls_ids,
                                 "min_eta": min(etas) if etas else None}
        return signature

    def _ev_event(self, t: float, evs: Sequence[Any]) -> bool:
        """True when the Emergency agent should run off-cadence (non-mutating)."""
        if not self.config.ev_event_triggers or not evs:
            return False
        if t - self._last_ev_event_t < self.config.ev_event_min_gap_s:
            return False
        for veh_id, now in self._ev_signature(evs).items():
            before = self._ev_seen.get(veh_id)
            if before is None:
                return True        # new EV entered the network
            if now["tls"] != before["tls"]:
                return True        # crossed a light / emerged from a junction
            if before["min_eta"] is not None and now["min_eta"] is not None:
                crossed = any(before["min_eta"] > threshold >= now["min_eta"]
                              for threshold in self.config.ev_eta_thresholds)
                if crossed:
                    return True    # ETA crossed 25 s / 15 s / 5 s
        return False

    # ── orchestration ───────────────────────────────────────────────────────

    def _budget_available(self) -> bool:
        return self.config.max_calls <= 0 or self.stats["calls"] < self.config.max_calls

    def should_run(self, t: float, states: Mapping[str, Mapping[str, Any]],
                   evs: Sequence[Any] = (), alerts: Sequence[Mapping[str, Any]] = ()) -> bool:
        if not self._budget_available():
            return False
        complexity = self.classify(t, states, evs, alerts)
        if "emergency" in self.agents and self._ev_event(t, evs):
            return True
        return any(self._agent_due(role, t, evs, complexity) for role in self.agents)

    def run(self, t: float, states: Mapping[str, Mapping[str, Any]],
            evs: Sequence[Any] = (), alerts: Sequence[Mapping[str, Any]] = (),
            force_roles: Sequence[str] = ()) -> List[ArbiterResult]:
        """
        Run every due agent once; returns successful arbiter results.
        `force_roles` bypasses the cadence for event-triggered runs (e.g. a
        detector alert fires the Operator immediately), still respecting the
        budget.
        """
        if not self._budget_available():
            self._log_budget_once(t)
            return []
        complexity = self.classify(t, states, evs, alerts)
        ev_event = "emergency" in self.agents and self._ev_event(t, evs)
        self._ev_seen = self._ev_signature(evs)
        if ev_event:
            self._last_ev_event_t = t
        effort = self._effort_for(complexity)
        messages = self.blackboard.active(t)
        snapshot = build_snapshot(t, states, self.neighbors, evs, alerts, messages)
        results: List[ArbiterResult] = []

        for role, agent in self.agents.items():
            if not self._budget_available():
                self._log_budget_once(t)
                break
            if role not in force_roles and not self._agent_due(role, t, evs, complexity,
                                                              ev_event):
                continue
            self._last_run[role] = t
            call = agent.ask(t, snapshot, messages, effort=effort)
            result, envelope_error = self._submit(role, call, t, states, complexity)
            self._log(t, call, result, envelope_error, complexity)
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

    def _log_budget_once(self, t: float) -> None:
        if self._budget_logged or self.logger is None:
            return
        self._budget_logged = True
        self.logger.log({
            "t": t,
            "agent": "supervisor",
            "error": f"max_calls={self.config.max_calls} reached; slow layer disabled",
        })

    def _submit(self, role: str, call: AgentCall, t: float,
                states: Mapping[str, Mapping[str, Any]], complexity: str):
        self.stats["calls"] += 1
        self.stats[f"{role}_calls"] = self.stats.get(f"{role}_calls", 0) + 1
        if complexity == COMPLEXITY_CONGESTED and self.config.escalate_effort:
            self.stats["escalated"] += 1
        if call.response is not None:
            self.stats["tokens_in"] += call.response.tokens_in or 0
            self.stats["tokens_out"] += call.response.tokens_out or 0
            self.stats["tokens_cached"] += call.response.tokens_cached or 0
        if call.attempts > 1:
            self.stats["retries"] += 1
        if call.failed:
            self.stats["fallbacks"] += 1
        try:
            return self.arbiter.submit(role, call.envelope, t, states), None
        except SchemaError as exc:
            return None, str(exc)

    def _log(self, t: float, call: AgentCall, result: Optional[ArbiterResult],
             envelope_error: Optional[str], complexity: str) -> None:
        if self.logger is None:
            return
        response = call.response
        record: Dict[str, Any] = {
            "t": t,
            "agent": call.role,
            "prompt_hash": call.prompt_hash,
            "attempts": call.attempts,
            "complexity": complexity,
            "effort": call.effort,
            "error": call.error or envelope_error,
            "tokens_in": getattr(response, "tokens_in", None) if response else None,
            "tokens_out": getattr(response, "tokens_out", None) if response else None,
            "tokens_cached": getattr(response, "tokens_cached", None) if response else None,
            "latency_s": getattr(response, "latency_s", None) if response else None,
            "raw_response": getattr(response, "raw", None) if response else None,
            "parsed": call.envelope,
            "review": call.review,
            "arbiter": result.to_record() if result is not None else None,
        }
        self.logger.log(record)
