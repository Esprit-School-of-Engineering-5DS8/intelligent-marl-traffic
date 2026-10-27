"""Cadence, snapshot building and agent orchestration for the LLM team."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from cotraffic.controllers.llm_team.agent import AgentCall, LLMAgent
from cotraffic.controllers.llm_team.arbiter import Arbiter, ArbiterResult
from cotraffic.controllers.llm_team.blackboard import Blackboard
from cotraffic.controllers.llm_team.client import CallLogger
from cotraffic.controllers.llm_team.schemas import EMPTY_ENVELOPE, SchemaError
from cotraffic.controllers.llm_team.snapshot import PhaseMap, build_snapshot

COMPLEXITY_QUIET = "quiet"
COMPLEXITY_NORMAL = "normal"
COMPLEXITY_CONGESTED = "congested"
ROLE_ORDER = ("operator", "emergency", "pedestrian")


@dataclass
class SupervisorConfig:
    delta_s: float = 30.0
    quiet_delta_s: float = 60.0
    congested_delta_s: float = 20.0
    ev_replan_s: float = 60.0
    pedestrian_interval_s: float = 30.0
    feedback_ttl_s: float = 60.0
    max_calls: int = 0
    quiet_queue_threshold: int = 8
    congested_queue_threshold: int = 15
    base_effort: str = ""
    escalate_effort: str = "low"
    ev_event_triggers: bool = True
    ev_event_min_gap_s: float = 5.0
    ev_eta_thresholds: tuple[float, ...] = ()
    ev_eta_min_speed_m_s: float = 1.0
    ped_trigger_wait_s: float = 20.0
    ped_event_min_gap_s: float = 20.0
    ped_group_min_gap_s: float = 30.0
    parallel: bool = True
    parallel_workers: int = 3
    max_alerts: int = 5
    max_blackboard_messages: int = 6
    ev_horizon_s: float = 60.0
    ev_lookahead: int = 3
    price_input_per_1m: float = 0.0
    price_output_per_1m: float = 0.0
    price_cached_per_1m: float = 0.0


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
        phase_maps: Mapping[str, PhaseMap] | None = None,
    ) -> None:
        self.agents = dict(agents)
        self.arbiter = arbiter
        self.blackboard = blackboard if blackboard is not None else Blackboard()
        self.config = config or SupervisorConfig()
        self.logger = logger
        self.neighbors = dict(neighbors or {})
        self.pedestrian_trigger = bool(pedestrian_trigger)
        self.network = network
        self.phase_maps = dict(phase_maps or {})
        self._last_run: dict[str, float] = {}
        self._budget_logged = False
        self._ev_seen: dict[str, dict[str, Any]] = {}
        self._last_ev_event_t: float = float("-inf")
        self._ped_seen: dict[tuple[str, str], float] = {}
        self._last_ped_event_t: float = float("-inf")
        self._last_ped_tls: dict[str, float] = {}
        self._conflict_seen: tuple[Any, ...] = ()
        self._latencies: dict[str, list[float]] = {}
        self.wall_time_s = 0.0
        self.stats: dict[str, int] = {
            "calls": 0,
            "fallbacks": 0,
            "retries": 0,
            "escalated": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "tokens_cached": 0,
            "tokens_reasoning": 0,
            "code_updates": 0,
            "releases": 0,
            "skipped_operator": 0,
            "skipped_emergency": 0,
            "skipped_pedestrian": 0,
            "skipped_budget": 0,
        }
        for role in ROLE_ORDER:
            for name in (
                "calls",
                "fallbacks",
                "retries",
                "tokens_in",
                "tokens_out",
                "tokens_cached",
                "tokens_reasoning",
            ):
                self.stats.setdefault(f"{role}_{name}", 0)

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

    def _effort_for(
        self,
        complexity: str,
        role: str,
        evs: Sequence[Any] = (),
        pedestrians: Sequence[Any] = (),
    ) -> str:
        if role == "emergency" and evs and self.config.escalate_effort:
            return self.config.escalate_effort
        if (
            role == "pedestrian"
            and self.config.escalate_effort
            and any(
                float(self._field(state, "max_wait_s", 0.0) or 0.0)
                >= self.config.ped_trigger_wait_s
                for state in pedestrians
            )
        ):
            return self.config.escalate_effort
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
            fallback = self.config.ev_replan_s > 0 and self._due(role, t, complexity)
            return bool(evs) and (ev_event or fallback)
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

    def _conflict_signature(self, evs: Sequence[Any]) -> tuple[Any, ...]:
        if not self.phase_maps:
            return ()
        by_tls: dict[str, set[str]] = {}
        for ev in evs:
            for nxt in self._field(ev, "next_tls", ()) or ():
                tls_id = str(self._field(nxt, "tls_id", "") or "")
                phase_map = self.phase_maps.get(tls_id)
                if phase_map is None:
                    continue
                link = self._field(nxt, "link_index", -1)
                if not isinstance(link, (int, float)) or link < 0:
                    continue
                axis = phase_map.axis_for_link(int(link))
                if axis is not None:
                    by_tls.setdefault(tls_id, set()).add(axis)
        return tuple(
            sorted(
                (tls_id, tuple(sorted(axes)))
                for tls_id, axes in by_tls.items()
                if len(axes) > 1
            )
        )

    def _ev_event(self, t: float, evs: Sequence[Any]) -> bool:
        if not self.config.ev_event_triggers or not evs:
            return False
        if t - self._last_ev_event_t < self.config.ev_event_min_gap_s:
            return False
        conflicts = self._conflict_signature(evs)
        if conflicts and conflicts != self._conflict_seen:
            return True
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
            tls_id = str(self._field(state, "tls_id", "") or "")
            if t - self._last_ped_tls.get(tls_id, float("-inf")) < self.config.ped_group_min_gap_s:
                continue
            key = (tls_id, str(self._field(state, "axis", "") or ""))
            wait = float(self._field(state, "max_wait_s", 0.0) or 0.0)
            previous = self._ped_seen.get(key)
            if previous is None:
                if wait >= self.config.ped_trigger_wait_s:
                    return True
            elif previous < self.config.ped_trigger_wait_s <= wait:
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

    def _prepare(
        self,
        t: float,
        states: Mapping[str, Mapping[str, Any]],
        evs: Sequence[Any],
        alerts: Sequence[Mapping[str, Any]],
        pedestrians: Sequence[Any],
    ) -> tuple[str, bool, bool, tuple[Any, ...], list[Any], dict[str, Any]]:
        complexity = self.classify(t, states, evs, alerts, pedestrians)
        ev_event = "emergency" in self.agents and self._ev_event(t, evs)
        ped_event = "pedestrian" in self.agents and self._ped_event(t, pedestrians)
        conflicts = self._conflict_signature(evs)
        messages = self.blackboard.compact(t, self.config.max_blackboard_messages)
        snapshot = build_snapshot(
            t,
            states,
            self.neighbors,
            evs,
            alerts,
            messages,
            pedestrians,
            self.network,
            max_alerts=self.config.max_alerts,
            max_messages=self.config.max_blackboard_messages,
            ev_horizon_s=self.config.ev_horizon_s,
            ev_lookahead=self.config.ev_lookahead,
        )
        return complexity, ev_event, ped_event, conflicts, messages, snapshot

    def _mark_events(
        self,
        t: float,
        evs: Sequence[Any],
        pedestrians: Sequence[Any],
        conflict_signature: tuple[Any, ...],
        ev_event: bool,
        ped_event: bool,
    ) -> None:
        self._ev_seen = self._ev_signature(evs)
        self._conflict_seen = conflict_signature
        self._ped_seen = self._ped_signature(pedestrians)
        if ev_event:
            self._last_ev_event_t = t
        if ped_event:
            self._last_ped_event_t = t
            for key in self._ped_seen:
                if key[0]:
                    self._last_ped_tls[key[0]] = t

    def _ordered_roles(self) -> list[str]:
        return [role for role in ROLE_ORDER if role in self.agents]

    def _due_roles(
        self,
        t: float,
        evs: Sequence[Any],
        complexity: str,
        ev_event: bool,
        pedestrians: Sequence[Any],
        ped_event: bool,
        force_roles: Sequence[str],
    ) -> list[str]:
        return [
            role
            for role in self._ordered_roles()
            if role in force_roles
            or self._agent_due(
                role, t, evs, complexity, ev_event, pedestrians, ped_event
            )
        ]

    def _count_skips(
        self,
        roles: Sequence[str],
        due: Sequence[str],
        evs: Sequence[Any],
        pedestrians: Sequence[Any],
    ) -> None:
        for role in roles:
            if role in due:
                continue
            if role == "emergency" and evs:
                self.stats["skipped_emergency"] += 1
            elif role == "pedestrian" and pedestrians:
                self.stats["skipped_pedestrian"] += 1
            elif role == "operator":
                self.stats["skipped_operator"] += 1

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
            for role in self._ordered_roles()
        )

    def tick(
        self,
        t: float,
        states: Mapping[str, Mapping[str, Any]],
        evs: Sequence[Any] = (),
        alerts: Sequence[Mapping[str, Any]] = (),
        pedestrians: Sequence[Any] = (),
        force_roles: Sequence[str] = (),
    ) -> list[ArbiterResult]:
        """Maintain persisted plans, then run due roles once."""
        if not self._budget_available():
            self._log_budget_once(t)
            return []
        complexity, ev_event, ped_event, conflicts, messages, snapshot = self._prepare(
            t, states, evs, alerts, pedestrians
        )
        results: list[ArbiterResult] = []
        started = time.perf_counter()
        emergency = self.agents.get("emergency")
        if emergency is not None and hasattr(emergency, "maintain"):
            call = emergency.maintain(t, snapshot)
            if call is not None:
                result = self._submit_code("emergency", call, t, states)
                if result is not None:
                    results.append(result)
        self.wall_time_s += time.perf_counter() - started

        due = self._due_roles(
            t, evs, complexity, ev_event, pedestrians, ped_event, force_roles
        )
        self._mark_events(t, evs, pedestrians, conflicts, ev_event, ped_event)
        self._count_skips(self._ordered_roles(), due, evs, pedestrians)
        results.extend(
            self._execute(due, t, states, snapshot, messages, complexity, evs, pedestrians)
        )
        return results

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
        complexity, ev_event, ped_event, conflicts, messages, snapshot = self._prepare(
            t, states, evs, alerts, pedestrians
        )
        due = self._due_roles(
            t, evs, complexity, ev_event, pedestrians, ped_event, force_roles
        )
        self._mark_events(t, evs, pedestrians, conflicts, ev_event, ped_event)
        self._count_skips(self._ordered_roles(), due, evs, pedestrians)
        return self._execute(
            due, t, states, snapshot, messages, complexity, evs, pedestrians
        )

    def _execute(
        self,
        due: Sequence[str],
        t: float,
        states: Mapping[str, Mapping[str, Any]],
        snapshot: Mapping[str, Any],
        messages: Sequence[Any],
        complexity: str,
        evs: Sequence[Any],
        pedestrians: Sequence[Any],
    ) -> list[ArbiterResult]:
        roles = [role for role in due if role in self.agents]
        if self.config.max_calls > 0:
            remaining = max(0, self.config.max_calls - self.stats["calls"])
            if len(roles) > remaining:
                self.stats["skipped_budget"] += len(roles) - remaining
                roles = roles[:remaining]
        if not roles:
            return []
        efforts = {
            role: self._effort_for(complexity, role, evs, pedestrians) for role in roles
        }
        for role in roles:
            self._last_run[role] = t
        calls: dict[str, AgentCall] = {}
        started = time.perf_counter()
        workers = max(1, int(self.config.parallel_workers))
        if len(roles) > 1 and self.config.parallel and workers > 1:
            with ThreadPoolExecutor(max_workers=min(workers, len(roles))) as pool:
                futures = {
                    role: pool.submit(
                        self.agents[role].ask,
                        t,
                        snapshot,
                        messages,
                        effort=efforts[role],
                    )
                    for role in roles
                }
                for role in roles:
                    try:
                        calls[role] = futures[role].result()
                    except Exception as error:  # noqa: BLE001 - keep the tick alive
                        calls[role] = AgentCall(
                            role=role,
                            envelope=dict(EMPTY_ENVELOPE),
                            error=f"{type(error).__name__}: {error}",
                        )
        else:
            for role in roles:
                calls[role] = self.agents[role].ask(
                    t, snapshot, messages, effort=efforts[role]
                )
        self.wall_time_s += time.perf_counter() - started

        results: list[ArbiterResult] = []
        for role in roles:
            call = calls[role]
            result, envelope_error = self._submit(role, call, t, states, complexity)
            self._log(t, call, result, envelope_error, complexity)
            if result is None:
                continue
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
        self.stats[f"{role}_calls"] += 1
        if complexity == COMPLEXITY_CONGESTED and self.config.escalate_effort:
            self.stats["escalated"] += 1
        response = call.response
        if response is not None:
            self.stats["tokens_in"] += response.tokens_in or 0
            self.stats["tokens_out"] += response.tokens_out or 0
            self.stats["tokens_cached"] += response.tokens_cached or 0
            self.stats["tokens_reasoning"] += response.tokens_reasoning or 0
            self.stats[f"{role}_tokens_in"] += response.tokens_in or 0
            self.stats[f"{role}_tokens_out"] += response.tokens_out or 0
            self.stats[f"{role}_tokens_cached"] += response.tokens_cached or 0
            self.stats[f"{role}_tokens_reasoning"] += response.tokens_reasoning or 0
            if response.latency_s:
                self._latencies.setdefault(role, []).append(float(response.latency_s))
        if call.attempts > 1:
            self.stats["retries"] += 1
            self.stats[f"{role}_retries"] += 1
        if call.failed:
            self.stats["fallbacks"] += 1
            self.stats[f"{role}_fallbacks"] += 1
        try:
            return self.arbiter.submit(role, call.envelope, t, states), None
        except SchemaError as exc:
            return None, str(exc)

    def _submit_code(
        self,
        role: str,
        call: AgentCall,
        t: float,
        states: Mapping[str, Mapping[str, Any]],
    ) -> ArbiterResult | None:
        try:
            result = self.arbiter.submit(role, call.envelope, t, states)
        except SchemaError:
            return None
        self.stats["code_updates"] += 1
        self.stats["releases"] += sum(
            1
            for directive in result.accepted
            if directive.type == "preempt" and not directive.hold_s
        )
        if self.logger is not None:
            self.logger.log(
                {
                    "t": t,
                    "agent": role,
                    "source": "code",
                    "review": call.review,
                    "arbiter": result.to_record(),
                }
            )
        return result

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

    @staticmethod
    def _percentile(values: Sequence[float], quantile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
        return round(float(ordered[index]), 3)

    def _role_metrics(self, role: str) -> dict[str, Any]:
        latencies = self._latencies.get(role, [])
        calls = int(self.stats.get(f"{role}_calls", 0))
        return {
            f"llm_team_{role}_calls": calls,
            f"llm_team_{role}_latency_mean_s": round(sum(latencies) / len(latencies), 3)
            if latencies
            else 0.0,
            f"llm_team_{role}_latency_p50_s": self._percentile(latencies, 0.5),
            f"llm_team_{role}_latency_p90_s": self._percentile(latencies, 0.9),
            f"llm_team_{role}_tokens_in": int(self.stats.get(f"{role}_tokens_in", 0)),
            f"llm_team_{role}_tokens_out": int(self.stats.get(f"{role}_tokens_out", 0)),
            f"llm_team_{role}_tokens_reasoning": int(
                self.stats.get(f"{role}_tokens_reasoning", 0)
            ),
            f"llm_team_{role}_tokens_cached": int(
                self.stats.get(f"{role}_tokens_cached", 0)
            ),
            f"llm_team_{role}_retries": int(self.stats.get(f"{role}_retries", 0)),
            f"llm_team_{role}_fallbacks": int(self.stats.get(f"{role}_fallbacks", 0)),
            f"llm_team_{role}_skipped": int(
                self.stats.get(f"skipped_{role}", 0)
            ),
        }

    def metrics(self) -> dict[str, Any]:
        latencies = [value for values in self._latencies.values() for value in values]
        tokens_in = int(self.stats["tokens_in"])
        tokens_out = int(self.stats["tokens_out"])
        tokens_cached = int(self.stats["tokens_cached"])
        cost = (
            max(0, tokens_in - tokens_cached) * self.config.price_input_per_1m
            + tokens_cached * self.config.price_cached_per_1m
            + tokens_out * self.config.price_output_per_1m
        ) / 1_000_000
        metrics: dict[str, Any] = {
            "llm_team_calls": int(self.stats["calls"]),
            "llm_team_max_calls": int(self.config.max_calls),
            "llm_team_fallbacks": int(self.stats["fallbacks"]),
            "llm_team_retries": int(self.stats["retries"]),
            "llm_team_escalated": int(self.stats["escalated"]),
            "llm_team_tokens_in": tokens_in,
            "llm_team_tokens_out": tokens_out,
            "llm_team_tokens_cached": tokens_cached,
            "llm_team_tokens_reasoning": int(self.stats["tokens_reasoning"]),
            "llm_team_latency_mean_s": round(sum(latencies) / len(latencies), 3)
            if latencies
            else 0.0,
            "llm_team_latency_p50_s": self._percentile(latencies, 0.5),
            "llm_team_latency_p90_s": self._percentile(latencies, 0.9),
            "llm_team_skipped_calls": sum(
                int(self.stats.get(f"skipped_{role}", 0)) for role in ROLE_ORDER
            ),
            "llm_team_skipped_budget": int(self.stats["skipped_budget"]),
            "llm_team_code_updates": int(self.stats["code_updates"]),
            "llm_team_releases": int(self.stats["releases"]),
            "llm_team_wall_time_s": round(self.wall_time_s, 3),
            "llm_team_estimated_cost_usd": round(cost, 6),
        }
        for role in ROLE_ORDER:
            metrics.update(self._role_metrics(role))
        return metrics
