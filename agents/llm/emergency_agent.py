"""
agents/llm/emergency_agent.py
Emergency agent (plan Phase 4 -> 4.5, section 4.5): LLM corridor planning with
a deterministic reviewer/scheduler on top of the shared LLM transport.

The agent is a `LLMAgent` with four role-specific additions:

1. **Corridor view.** `build_user_message` enriches the shared snapshot with,
   per active EV, the next `lookahead` traffic lights annotated with the exact
   approach axis (`needed_phase`, derived from the TLS program via
   `TLSTopology.action_for_link`) and the queue on each axis, so the model
   never has to infer a phase from lane-id strings.
2. **Reviewer** (iLLM-TSC / REG-TSC pattern). After every call it pins `phase`
   to the EV's actual approach, recomputes `eta_s` from the sensed distance and
   speed, and enforces the queue-aware lead time from the literature
   (Obrusnik 2020, MLEVP): the preemption must not start later than the time
   needed to switch the phase and discharge the standing queue:
   `start_in_s <= eta_s - 15 - 2*queue_needed`.
3. **Scheduler** (MMITSS/ORiON conflict handling). Directives are tracked as
   absolute windows per (EV, TLS). When two EVs need *conflicting* phases at
   the same TLS, the later arrival is delayed until the earlier window ends
   (FCFS with one transition per EV instead of greedy thrash), then `hold_s` is
   recomputed so the window still covers the ETA (`eta_s - start_in_s + 8`).
   The schedule is republished every tick and exposed in the call log.
4. **Corridor memory + rule fallback.** Corridor pairs stay valid for a grace
   window (default 6 s) after the EV disappears into a junction's internal
   lanes, mirroring `RuleBasedEVPreemption.release_grace_steps`, so refreshes
   are not dropped and gaps do not open. Pairs whose EV has passed are
   explicitly released. When the call fails or no preempt is proposed, the A3
   rule source (plan Appendix B) proposes the corridor instead.

No TraCI in this module: everything works on snapshot dicts and topologies.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from agents.ev_preemption import PreemptionConfig, RuleBasedEVPreemption
from agents.llm.agent import AgentCall, LLMAgent
from agents.llm.schemas import ACTION_TO_AXIS
from environment.ev import EVState, UpcomingTLS
from environment.topology import TLSTopology

LEAD_TIME_S = 15.0          # fixed switching cost (min-green + yellow + margin)
DISCHARGE_PER_VEH_S = 2.0   # saturation-headway discharge estimate per queued veh
RELEASE_MARGIN_S = 8.0      # hold until ETA + margin (plan Appendix B)
MAX_ETA_S = 25.0            # trigger horizon: do not reserve far-away TLS
MAX_HOLD_S = 40.0           # schema cap for hold_s
MAX_TTL_S = 60.0            # schema cap for ttl_s
CORRIDOR_LOOKAHEAD = 3      # next TLS per EV, as in the A3 baseline
GRACE_S = 6.0               # corridor memory while an EV crosses a junction

CorridorKey = Tuple[str, str]


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


class EmergencyAgent(LLMAgent):
    def __init__(self, client, system_prompt: Optional[str] = None,
                 max_retries: int = 1,
                 topologies: Optional[Mapping[str, TLSTopology]] = None,
                 lead_time_s: float = LEAD_TIME_S,
                 discharge_per_veh_s: float = DISCHARGE_PER_VEH_S,
                 release_margin_s: float = RELEASE_MARGIN_S,
                 max_eta_s: float = MAX_ETA_S,
                 grace_s: float = GRACE_S,
                 lookahead: int = CORRIDOR_LOOKAHEAD,
                 rule_fallback: bool = True,
                 rule_config: Optional[PreemptionConfig] = None):
        super().__init__("emergency", client, system_prompt, max_retries)
        self.topologies = dict(topologies or {})
        self.lead_time_s = float(lead_time_s)
        self.discharge_per_veh_s = float(discharge_per_veh_s)
        self.release_margin_s = float(release_margin_s)
        self.max_eta_s = float(max_eta_s)
        self.grace_s = float(grace_s)
        self.lookahead = max(1, int(lookahead))
        self.rule_source = None
        if rule_fallback and self.topologies:
            self.rule_source = RuleBasedEVPreemption(self.topologies, rule_config)
        # (ev, tls) -> {"eta_s", "axis", "queue_needed", "seen"}: corridor memory
        # so an EV on an internal lane does not lose its plan (rule-source grace).
        self._tracked: Dict[CorridorKey, Dict[str, Any]] = {}
        # (ev, tls) -> scheduled absolute window, the scheduler's state.
        self._plan: Dict[CorridorKey, Dict[str, Any]] = {}

    # ── corridor view ───────────────────────────────────────────────────────

    def _axis_for(self, tls_id: Any, link_index: Any) -> Optional[str]:
        topology = self.topologies.get(tls_id)
        if topology is None or not isinstance(link_index, (int, float)) or link_index < 0:
            return None
        action = topology.action_for_link(int(link_index))
        return ACTION_TO_AXIS.get(action) if action is not None else None

    def _ev_view(self, ev: Mapping[str, Any],
                 snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        corridor: List[Dict[str, Any]] = []
        for nxt in list(ev.get("next_tls") or ())[: self.lookahead]:
            tls_id = nxt.get("tls")
            axis = self._axis_for(tls_id, nxt.get("link_index"))
            state = (snapshot.get("intersections") or {}).get(tls_id, {})
            queue = state.get("queue") or {}
            row: Dict[str, Any] = {
                "tls": tls_id,
                "dist_m": nxt.get("dist_m"),
                "eta_s": nxt.get("eta_s"),
                "signal": nxt.get("signal"),
                "needed_phase": axis or "unknown",
                "current_phase": state.get("phase", "transition"),
                "time_in_phase_s": state.get("time_in_phase_s"),
            }
            if axis is not None:
                row["queue_needed"] = queue.get(axis.lower(), 0)
                row["queue_other"] = queue.get("ew" if axis == "NS" else "ns", 0)
            corridor.append(row)
        return {"id": ev.get("id"), "edge": ev.get("edge"),
                "speed": ev.get("speed"), "corridor": corridor}

    def build_user_message(self, t: float, snapshot: Mapping[str, Any],
                           blackboard: Iterable[Any] = ()) -> str:
        enriched: Dict[str, Any] = dict(snapshot)
        enriched["lead_time_s"] = self.lead_time_s
        enriched["evs"] = [self._ev_view(ev, snapshot)
                           for ev in (snapshot.get("evs") or ())]
        context = {
            "blackboard": [
                message.to_dict() if hasattr(message, "to_dict") else dict(message)
                for message in (blackboard or ())
            ]
        }
        return json.dumps({"tick": t, "snapshot": enriched, "context": context},
                          ensure_ascii=False, sort_keys=True, default=str)

    # ── corridor memory & reviewer ──────────────────────────────────────────

    def _corridor_index(self, snapshot: Mapping[str, Any]) -> Dict[CorridorKey, Dict[str, Any]]:
        index: Dict[CorridorKey, Dict[str, Any]] = {}
        states = snapshot.get("intersections") or {}
        for ev in (snapshot.get("evs") or ()):
            for nxt in (ev.get("next_tls") or ()):
                tls_id = nxt.get("tls")
                axis = self._axis_for(tls_id, nxt.get("link_index"))
                queue = 0
                if axis is not None:
                    state = states.get(tls_id) or {}
                    queue = (state.get("queue") or {}).get(axis.lower(), 0)
                index[(ev.get("id"), tls_id)] = {
                    "eta_s": _as_float(nxt.get("eta_s")),
                    "axis": axis,
                    "queue_needed": queue,
                }
        return index

    def _lookup(self, key: CorridorKey, corridor: Mapping[CorridorKey, Dict[str, Any]],
                t: float) -> Tuple[Optional[Mapping[str, Any]], float]:
        """Corridor info for a pair, falling back to the grace-tracked state."""
        info = corridor.get(key)
        if info is not None:
            return info, _as_float(info.get("eta_s"))
        tracked = self._tracked.get(key)
        if tracked is not None and t - tracked["seen"] <= self.grace_s:
            eta = max(0.0, _as_float(tracked.get("eta_s")) - (t - tracked["seen"]))
            return tracked, eta
        return None, 0.0

    def _lead_limit(self, eta: float, queue_needed: Any) -> float:
        queue = max(0.0, _as_float(queue_needed))
        return max(0.0, eta - self.lead_time_s - self.discharge_per_veh_s * queue)

    def _review_preempt(self, raw: Mapping[str, Any], info: Mapping[str, Any],
                        eta: float, notes: List[str]) -> Optional[Dict[str, Any]]:
        tls_id = raw.get("tls")
        if eta > self.max_eta_s:
            notes.append(f"{tls_id}: dropped, ETA {eta:.1f}s > {self.max_eta_s:.0f}s horizon")
            return None

        fixed = dict(raw)
        fixed["type"] = "preempt"
        axis = info.get("axis")
        if axis and fixed.get("phase") != axis:
            notes.append(f"{tls_id}: phase {fixed.get('phase')!r} -> {axis} (EV approach)")
            fixed["phase"] = axis
        fixed["eta_s"] = round(eta, 1)

        # Queue-aware lead: the preemption must not start later than the time
        # needed to switch the phase and discharge the standing queue. The
        # scheduler may still delay it for multi-EV sequencing; ETA coverage
        # is (re)applied there, after the final start is known.
        start = max(0.0, _as_float(fixed.get("start_in_s")))
        limit = self._lead_limit(eta, info.get("queue_needed"))
        if start - limit > 1e-6:
            notes.append(f"{tls_id}: start_in_s {start:.1f} -> {limit:.1f} (lead + queue)")
            start = limit
        fixed["start_in_s"] = round(start, 1)

        hold = min(max(_as_float(fixed.get("hold_s")), 0.0), MAX_HOLD_S)
        fixed["hold_s"] = round(hold, 1)

        ttl = _as_float(fixed.get("ttl_s"), 30.0)
        ttl = min(MAX_TTL_S, max(ttl, start + hold + 5.0))
        fixed["ttl_s"] = round(ttl, 1)
        return fixed

    def _release_allowed(self, key: CorridorKey, active_evs: Iterable[str]) -> bool:
        return (key[0] in set(active_evs) or key in self._plan or key in self._tracked)

    @staticmethod
    def _release_directive(key: CorridorKey, plan: Mapping[str, Any]) -> Dict[str, Any]:
        return {"tls": key[1], "type": "preempt", "phase": plan.get("phase") or "NS",
                "ev": key[0], "hold_s": 0, "ttl_s": 10.0}

    # ── scheduler ───────────────────────────────────────────────────────────

    def _schedule(self, t: float, requests: Dict[CorridorKey, Dict[str, Any]],
                  notes: List[str]) -> List[Dict[str, Any]]:
        """FCFS sequencing of conflicting preempts per TLS (MMITSS-style)."""
        by_tls: Dict[str, List[Tuple[CorridorKey, Dict[str, Any]]]] = {}
        for key, request in sorted(requests.items()):
            by_tls.setdefault(request["tls"], []).append((key, request))

        scheduled: List[Dict[str, Any]] = []
        for tls_id, items in sorted(by_tls.items()):
            placed: List[Dict[str, Any]] = []
            for key, request in sorted(items, key=lambda kv: (kv[1]["eta_s"], kv[0])):
                eta_abs = t + request["eta_s"]
                start_abs = t + _as_float(request.get("start_in_s"))
                end_abs = start_abs + _as_float(request.get("hold_s"))
                conflict_end = start_abs
                for other in placed:
                    if (other["phase"] != request["phase"]
                            and start_abs < other["end_abs"] and other["start_abs"] < end_abs):
                        conflict_end = max(conflict_end, other["end_abs"])
                if conflict_end - start_abs > 1e-6:
                    notes.append(f"{tls_id}: {key[0]} start delayed to {conflict_end - t:.1f}s "
                                 f"(serve the earlier arrival first)")
                    start_abs = conflict_end

                hold = max(_as_float(request.get("hold_s")),
                           eta_abs - start_abs + self.release_margin_s)
                hold = min(hold, MAX_HOLD_S)
                start_rel = max(0.0, start_abs - t)
                if start_rel + hold > MAX_TTL_S:
                    hold = max(0.0, MAX_TTL_S - start_rel)
                    notes.append(f"{tls_id}: {key[0]} window clipped to the 60s TTL cap")
                if hold <= 0.0:
                    notes.append(f"{tls_id}: {key[0]} dropped, no room inside the TTL cap")
                    continue

                ttl = min(MAX_TTL_S, max(_as_float(request.get("ttl_s"), 30.0),
                                         start_rel + hold + 5.0))
                directive = {k: v for k, v in request.items() if not k.startswith("_")}
                directive.update({
                    "start_in_s": round(start_rel, 1),
                    "hold_s": round(hold, 1),
                    "ttl_s": round(ttl, 1),
                    "eta_s": round(request["eta_s"], 1),
                })
                placed.append({
                    "key": key, "tls": tls_id, "phase": request["phase"],
                    "eta_abs": eta_abs, "start_abs": start_abs, "end_abs": start_abs + hold,
                    "hold": hold, "directive": directive,
                })
            scheduled.extend(placed)
        return scheduled

    def review(self, t: float, snapshot: Mapping[str, Any], call: AgentCall) -> AgentCall:
        notes: List[str] = []
        corridor = self._corridor_index(snapshot)
        active_evs = {ev.get("id") for ev in (snapshot.get("evs") or ())}
        for key, info in corridor.items():
            self._tracked[key] = {**info, "seen": t}

        incoming: Dict[CorridorKey, Dict[str, Any]] = {}
        releases: Dict[CorridorKey, Dict[str, Any]] = {}
        passthrough: List[Any] = []

        for raw in (call.envelope.get("directives") or ()):
            if not isinstance(raw, Mapping) or raw.get("type") != "preempt":
                # Wrong types are the arbiter's to reject and log.
                passthrough.append(raw)
                continue
            key = (raw.get("ev"), raw.get("tls"))
            info, eta = self._lookup(key, corridor, t)
            if info is not None:
                fixed = self._review_preempt(raw, info, eta, notes)
                if fixed is not None:
                    incoming[key] = fixed
            elif _as_float(raw.get("hold_s")) == 0.0 and self._release_allowed(key, active_evs):
                releases[key] = dict(raw)
                self._plan.pop(key, None)
            else:
                notes.append(f"dropped preempt for non-corridor pair {key}")

        # Keep still-relevant scheduled windows alive even if the model omitted
        # them this tick (or its refresh was dropped while the EV was invisible).
        requests: Dict[CorridorKey, Dict[str, Any]] = dict(incoming)
        for key, plan in sorted(self._plan.items()):
            if key in requests:
                continue
            info, eta = self._lookup(key, corridor, t)
            if info is None or eta <= 0.0 or eta > self.max_eta_s:
                continue
            start_abs = max(t, plan["start_abs"])
            end_abs = min(max(plan["end_abs"], t + eta + self.release_margin_s),
                          start_abs + MAX_HOLD_S)
            requests[key] = {
                "tls": key[1], "type": "preempt", "phase": plan["phase"],
                "ev": key[0], "eta_s": round(eta, 1),
                "start_in_s": round(max(0.0, start_abs - t), 1),
                "hold_s": round(max(0.0, end_abs - start_abs), 1),
                "ttl_s": MAX_TTL_S, "_from_plan": True,
            }

        # Rule-based fallback when the LLM failed or proposed nothing usable.
        fallback_added = 0
        if call.failed or not requests:
            for proposal in self._fallback_proposals(t, snapshot):
                key = (proposal.get("ev"), proposal.get("tls"))
                if key in requests:
                    continue
                info, eta = self._lookup(key, corridor, t)
                if info is None:
                    continue
                fixed = self._review_preempt(proposal, info, eta, notes)
                if fixed is not None:
                    requests[key] = fixed
                    fallback_added += 1

        # Explicit releases for pairs the EV has passed (or that went stale).
        for key, plan in sorted(self._plan.items()):
            if key in requests or key in releases:
                continue
            tracked = self._tracked.get(key)
            if tracked is None:
                if plan["end_abs"] <= t:
                    releases[key] = self._release_directive(key, plan)
                continue
            eta = _as_float(tracked.get("eta_s")) - (t - tracked["seen"])
            if eta <= 0.0 or (t - tracked["seen"] > self.grace_s and key[0] not in active_evs):
                releases[key] = self._release_directive(key, plan)
                self._plan.pop(key, None)

        scheduled = self._schedule(t, requests, notes)

        # Persist the schedule (drop released/expired pairs, keep untouched ones).
        new_plan: Dict[CorridorKey, Dict[str, Any]] = {}
        for entry in scheduled:
            new_plan[entry["key"]] = {
                "phase": entry["phase"], "tls": entry["tls"],
                "start_abs": entry["start_abs"], "end_abs": entry["end_abs"],
                "hold": entry["hold"],
            }
        for key, plan in self._plan.items():
            if key not in new_plan and key not in releases and plan["end_abs"] > t:
                new_plan[key] = plan
        self._plan = new_plan

        source = "llm"
        if fallback_added and (call.failed or not incoming):
            source = "rules"

        directives: List[Any] = list(passthrough)
        directives.extend(entry["directive"] for entry in sorted(scheduled, key=lambda e: e["key"]))
        directives.extend(releases[key] for key in sorted(releases))

        envelope = dict(call.envelope)
        envelope["directives"] = directives
        if source == "rules" and not envelope.get("explanation"):
            envelope["explanation"] = "rule-based pre-emption fallback"

        # Inter-agent communication (plan 4.5/4.2): publish the active corridor
        # so the Operator never biases against the TLSs serving an EV.
        alerts = [a for a in (call.envelope.get("alerts") or ())
                  if not (isinstance(a, Mapping) and a.get("kind") == "ev_corridor")]
        corridors: Dict[str, List[str]] = {}
        for directive in directives:
            if (isinstance(directive, Mapping)
                    and directive.get("type") == "preempt"
                    and _as_float(directive.get("hold_s")) > 0
                    and isinstance(directive.get("ev"), str)):
                corridors.setdefault(directive["ev"], []).append(str(directive.get("tls")))
        for ev_id in sorted(corridors):
            alerts.append({"kind": "ev_corridor", "ev": ev_id,
                           "tls": sorted(set(corridors[ev_id]))})
        envelope["alerts"] = alerts

        schedule_log = [
            {"tls": entry["tls"], "ev": entry["key"][0], "phase": entry["phase"],
             "start_s": round(max(0.0, entry["start_abs"] - t), 1),
             "end_s": round(max(0.0, entry["end_abs"] - t), 1)}
            for entry in sorted(scheduled, key=lambda e: e["key"])
        ]
        return AgentCall(
            role=call.role, envelope=envelope, response=call.response,
            error=call.error, prompt_hash=call.prompt_hash,
            attempts=call.attempts, effort=call.effort,
            review={"source": source, "notes": notes,
                    "n_directives": len(directives), "schedule": schedule_log},
        )

    def ask(self, t: float, snapshot: Mapping[str, Any],
            blackboard: Iterable[Any] = (),
            effort: Optional[str] = None) -> AgentCall:
        call = super().ask(t, snapshot, blackboard, effort)
        return self.review(t, snapshot, call)

    # ── rule fallback ───────────────────────────────────────────────────────

    def _fallback_proposals(self, t: float,
                            snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
        if self.rule_source is None:
            return []
        envelopes = self.rule_source.propose(self._evstates(snapshot), t)
        if not envelopes:
            return []
        return list(envelopes[0].get("directives", []))

    @staticmethod
    def _evstates(snapshot: Mapping[str, Any]) -> List[EVState]:
        evs: List[EVState] = []
        for ev in (snapshot.get("evs") or ()):
            next_tls = tuple(
                UpcomingTLS(
                    tls_id=str(nxt.get("tls")),
                    link_index=int(_as_float(nxt.get("link_index"), -1.0)),
                    distance_m=_as_float(nxt.get("dist_m")),
                    signal=str(nxt.get("signal", "")),
                )
                for nxt in (ev.get("next_tls") or ())
            )
            evs.append(EVState(
                veh_id=str(ev.get("id", "")),
                edge_id=str(ev.get("edge", "")),
                lane_id="",
                speed_m_s=_as_float(ev.get("speed")),
                next_tls=next_tls,
            ))
        return evs
