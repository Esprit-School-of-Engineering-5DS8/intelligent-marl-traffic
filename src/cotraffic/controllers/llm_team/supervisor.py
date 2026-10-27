"""Cadence, snapshot building and agent orchestration for the LLM team."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cotraffic.controllers.llm_team.agent import AgentCall, LLMAgent
from cotraffic.controllers.llm_team.arbiter import Arbiter, ArbiterResult
from cotraffic.controllers.llm_team.blackboard import Blackboard
from cotraffic.controllers.llm_team.client import CallLogger
from cotraffic.controllers.llm_team.schemas import SchemaError
from cotraffic.controllers.llm_team.snapshot import build_snapshot

COMPLEXITY_QUIET = "quiet"
COMPLEXITY_NORMAL = "normal"
COMPLEXITY_CONGESTED = "congested"


@dataclass
class SupervisorConfig:
    delta_s: float = 30.0
    quiet_delta_s: float = 60.0
    congested_delta_s: float = 15.0
    ev_replan_s: float = 10.0
    pedestrian_interval_s: float = 30.0
    feedback_ttl_s: float = 60.0
    max_calls: int = 0
    quiet_queue_threshold: int = 8
    congested_queue_threshold: int = 15
    base_effort: str = ""
    escalate_effort: str = "low"
    ev_event_triggers: bool = True
    ev_event_min_gap_s: float = 3.0
    ev_eta_thresholds: tuple[float, ...] = (25.0, 15.0, 5.0)
    ev_eta_min_speed_m_s: float = 1.0
    ped_trigger_wait_s: float = 20.0
    ped_event_min_gap_s: float = 5.0


class Supervisor:
    def __init__(
        self,
        agents: Mapping[str, LLMAgent],
        arbiter: Arbiter,
        blackboard: Blackboard | None = None,
        config: SupervisorConfig | None = None,
        logger: CallLogger | None = None,
        neighbors: Mapping[str, Mapping[str, str]] | None = None,
        pedestrian_trigger: bool = False,
        network: str = "",
    ) -> None:
        self.agents = dict(agents)
        self.arbiter = arbiter
        self.blackboard = blackboard if blackboard is not None else Blackboard()
        self.config = config or SupervisorConfig()
        self.logger = logger
        self.neighbors = dict(neighbors or {})
        self.pedestrian_trigger = bool(pedestrian_trigger)
        self.network = network
        self._last_run: dict[str, float] = {}
        self._budget_logged = False
        self._ev_seen: dict[str, dict[str, Any]] = {}
        self._last_ev_event_t: float = float("-inf")
        self._ped_seen: dict[tuple[str, str], float] = {}
        self._last_ped_event_t: float = float("-inf")
        self.stats: dict[str, int] = {
            "calls": 0,
            "fallbacks": 0,
            "retries": 0,
            "escalated": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "tokens_cached": 0,
            "tokens_reasoning": 0,
        }

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
                max_queue = max(
                    max_queue,
                    int(state.get("ns_queue", 0) or 0),
                    int(state.get("ew_queue", 0) or 0),
                )
        return max_queue

    @staticmethod
    def _field(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, Mapping):
            return obj.get(name, default)
        return getattr(obj, name, default)

    def classify(
        self,
        t: float,
        states: Mapping[str, Mapping[str, Any]],
        evs: Sequence[Any] = (),
        alerts: Sequence[Mapping[str, Any]] = (),
        pedestrians: Sequence[Any] = (),
    ) -> str:
        if evs or alerts:
            return COMPLEXITY_CONGESTED
        if any(
            float(self._field(p, "max_wait_s", 0.0) or 0.0)
            >= self.config.ped_trigger_wait_s
            for p in pedestrians
        ):
            return COMPLEXITY_CONGESTED
        traffic_messages = [
            m for m in self.blackboard.active(t) if m.kind != "arbiter_result"
        ]
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

    def _agent_due(
        self,
        role: str,
        t: float,
        evs: Sequence[Any],
        complexity: str,
        ev_event: bool = False,
        pedestrians: Sequence[Any] = (),
        ped_event: bool = False,
    ) -> bool:
        if role == "emergency":
            return bool(evs) and (ev_event or self._due(role, t, complexity))
        if role == "pedestrian":
            return (
                self.pedestrian_trigger
                and bool(pedestrians)
                and (ped_event or self._due(role, t, complexity))
            )
        return self._due(role, t, complexity)

    def _ev_signature(self, evs: Sequence[Any]) -> dict[str, dict[str, Any]]:
        signature: dict[str, dict[str, Any]] = {}
        for ev in evs:
            veh_id = str(self._field(ev, "veh_id", "") or "")
            speed = max(
                float(self._field(ev, "speed_m_s", 0.0) or 0.0),
                self.config.ev_eta_min_speed_m_s,
            )
            next_tls = tuple(self._field(ev, "next_tls", ()) or ())
            tls_ids = tuple(str(self._field(nxt, "tls_id", "")) for nxt in next_tls)
            etas = [
                float(self._field(nxt, "distance_m", 0.0) or 0.0) / speed
                for nxt in next_tls
            ]
            signature[veh_id] = {"tls": tls_ids, "min_eta": min(etas) if etas else None}
        return signature

    def _ev_event(self, t: float, evs: Sequence[Any]) -> bool:
        if not self.config.ev_event_triggers or not evs:
            return False
        if t - self._last_ev_event_t < self.config.ev_event_min_gap_s:
            return False
        for veh_id, now in self._ev_signature(evs).items():
            before = self._ev_seen.get(veh_id)
            if before is None:
                return True
            if now["tls"] != before["tls"]:
                return True
            if (
                before["min_eta"] is not None
                and now["min_eta"] is not None
                and any(
                    before["min_eta"] > threshold >= now["min_eta"]
                    for threshold in self.config.ev_eta_thresholds
                )
            ):
                return True
        return False

    def _ped_event(self, t: float, pedestrians: Sequence[Any]) -> bool:
        if not pedestrians or not self.pedestrian_trigger:
            return False
        if t - self._last_ped_event_t < self.config.ped_event_min_gap_s:
            return False
        for state in pedestrians:
            key = (
                str(self._field(state, "tls_id", "")),
                str(self._field(state, "axis", "")),
            )
            wait = float(self._field(state, "max_wait_s", 0.0) or 0.0)
            previous = self._ped_seen.get(key)
            if previous is None:
                return True
            if previous < self.config.ped_trigger_wait_s <= wait:
                return True
        return False

    def _ped_signature(
        self, pedestrians: Sequence[Any]
    ) -> dict[tuple[str, str], float]:
        return {
            (
                str(self._field(state, "tls_id", "")),
                str(self._field(state, "axis", "")),
            ): float(self._field(state, "max_wait_s", 0.0) or 0.0)
            for state in pedestrians
        }

    def _budget_available(self) -> bool:
        return self.config.max_calls <= 0 or self.stats["calls"] < self.config.max_calls

    def should_run(
        self,
        t: float,
        states: Mapping[str, Mapping[str, Any]],
        evs: Sequence[Any] = (),
        alerts: Sequence[Mapping[str, Any]] = (),
        pedestrians: Sequence[Any] = (),
    ) -> bool:
        if not self._budget_available():
            return False
        complexity = self.classify(t, states, evs, alerts, pedestrians)
        if "emergency" in self.agents and self._ev_event(t, evs):
            return True
        ped_event = "pedestrian" in self.agents and self._ped_event(t, pedestrians)
        return any(
            self._agent_due(role, t, evs, complexity, False, pedestrians, ped_event)
            for role in self.agents
        )

    def run(
        self,
        t: float,
        states: Mapping[str, Mapping[str, Any]],
        evs: Sequence[Any] = (),
        alerts: Sequence[Mapping[str, Any]] = (),
        force_roles: Sequence[str] = (),
        pedestrians: Sequence[Any] = (),
    ) -> list[ArbiterResult]:
        if not self._budget_available():
            self._log_budget_once(t)
            return []
        complexity = self.classify(t, states, evs, alerts, pedestrians)
        ev_event = "emergency" in self.agents and self._ev_event(t, evs)
        self._ev_seen = self._ev_signature(evs)
        if ev_event:
            self._last_ev_event_t = t
        ped_event = "pedestrian" in self.agents and self._ped_event(t, pedestrians)
        self._ped_seen = self._ped_signature(pedestrians)
        if ped_event:
            self._last_ped_event_t = t
        effort = self._effort_for(complexity)
        messages = self.blackboard.active(t)
        snapshot = build_snapshot(
            t,
            states,
            self.neighbors,
            evs,
            alerts,
            messages,
            pedestrians,
            self.network,
        )
        results: list[ArbiterResult] = []
        for role, agent in self.agents.items():
            if not self._budget_available():
                self._log_budget_once(t)
                break
            if role not in force_roles and not self._agent_due(
                role, t, evs, complexity, ev_event, pedestrians, ped_event
            ):
                continue
            self._last_run[role] = t
            call = agent.ask(t, snapshot, messages, effort=effort)
            result, envelope_error = self._submit(role, call, t, states, complexity)
            self._log(t, call, result, envelope_error, complexity)
            if result is not None:
                results.append(result)
                self.blackboard.post_message(
                    "arbiter_result",
                    "arbiter",
                    t,
                    payload=result.feedback_payload(),
                    ttl_s=self.config.feedback_ttl_s,
                )
                for alert in result.alerts:
                    self.blackboard.post_message(
                        str(alert.get("kind", "alert")),
                        role,
                        t,
                        payload={k: v for k, v in alert.items() if k != "kind"},
                        ttl_s=self.config.feedback_ttl_s,
                    )
        return results

    def _log_budget_once(self, t: float) -> None:
        if self._budget_logged or self.logger is None:
            return
        self._budget_logged = True
        self.logger.log(
            {
                "t": t,
                "agent": "supervisor",
                "error": f"max_calls={self.config.max_calls} reached; slow layer disabled",
            }
        )

    def _submit(
        self,
        role: str,
        call: AgentCall,
        t: float,
        states: Mapping[str, Mapping[str, Any]],
        complexity: str,
    ) -> tuple[ArbiterResult | None, str | None]:
        self.stats["calls"] += 1
        self.stats[f"{role}_calls"] = self.stats.get(f"{role}_calls", 0) + 1
        if complexity == COMPLEXITY_CONGESTED and self.config.escalate_effort:
            self.stats["escalated"] += 1
        if call.response is not None:
            self.stats["tokens_in"] += call.response.tokens_in or 0
            self.stats["tokens_out"] += call.response.tokens_out or 0
            self.stats["tokens_cached"] += call.response.tokens_cached or 0
            self.stats["tokens_reasoning"] += call.response.tokens_reasoning or 0
        if call.attempts > 1:
            self.stats["retries"] += 1
        if call.failed:
            self.stats["fallbacks"] += 1
        try:
            return self.arbiter.submit(role, call.envelope, t, states), None
        except SchemaError as exc:
            return None, str(exc)

    def _log(
        self,
        t: float,
        call: AgentCall,
        result: ArbiterResult | None,
        envelope_error: str | None,
        complexity: str,
    ) -> None:
        if self.logger is None:
            return
        response = call.response
        self.logger.log(
            {
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
        )
