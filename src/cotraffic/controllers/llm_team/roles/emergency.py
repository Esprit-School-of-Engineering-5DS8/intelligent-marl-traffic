"""Emergency role: corridor planning with a deterministic reviewer and scheduler."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from cotraffic.controllers.llm_team.agent import AgentCall, LLMAgent
from cotraffic.controllers.llm_team.snapshot import PhaseMap

LEAD_TIME_S = 15.0
DISCHARGE_PER_VEH_S = 2.0
RELEASE_MARGIN_S = 8.0
MAX_ETA_S = 25.0
MAX_HOLD_S = 40.0
MAX_TTL_S = 60.0
CORRIDOR_LOOKAHEAD = 3
GRACE_S = 6.0
REACTIVE_DISTANCE_M = 60.0

CorridorKey = tuple[str, str]


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


class EmergencyAgent(LLMAgent):
    def __init__(
        self,
        client,
        system_prompt: str | None = None,
        max_retries: int = 1,
        phase_maps: Mapping[str, PhaseMap] | None = None,
        lead_time_s: float = LEAD_TIME_S,
        discharge_per_veh_s: float = DISCHARGE_PER_VEH_S,
        release_margin_s: float = RELEASE_MARGIN_S,
        max_eta_s: float = MAX_ETA_S,
        grace_s: float = GRACE_S,
        lookahead: int = CORRIDOR_LOOKAHEAD,
        rule_fallback: bool = True,
        max_tokens: int = 500,
    ) -> None:
        super().__init__(
            "emergency", client, system_prompt, max_retries, max_tokens=max_tokens
        )
        self.phase_maps = dict(phase_maps or {})
        self.lead_time_s = float(lead_time_s)
        self.discharge_per_veh_s = float(discharge_per_veh_s)
        self.release_margin_s = float(release_margin_s)
        self.max_eta_s = float(max_eta_s)
        self.grace_s = float(grace_s)
        self.lookahead = max(1, int(lookahead))
        self.rule_fallback = bool(rule_fallback)
        self._tracked: dict[CorridorKey, dict[str, Any]] = {}
        self._plan: dict[CorridorKey, dict[str, Any]] = {}

    def _axis_for(self, tls_id: Any, link_index: Any) -> str | None:
        phase_map = self.phase_maps.get(str(tls_id))
        if phase_map is None or not isinstance(link_index, (int, float)) or link_index < 0:
            return None
        return phase_map.axis_for_link(int(link_index))

    def _group_for(self, tls_id: Any, link_index: Any) -> int | None:
        phase_map = self.phase_maps.get(str(tls_id))
        if phase_map is None or not isinstance(link_index, (int, float)) or link_index < 0:
            return None
        return phase_map.action_for_link(int(link_index))

    def _axis_is_multi_group(self, tls_id: Any, axis: str | None) -> bool:
        phase_map = self.phase_maps.get(str(tls_id))
        return phase_map.multi_group(axis) if phase_map is not None else False

    def _ev_view(
        self, ev: Mapping[str, Any], snapshot: Mapping[str, Any]
    ) -> dict[str, Any]:
        corridor: list[dict[str, Any]] = []
        for nxt in list(ev.get("next_tls") or ())[: self.lookahead]:
            tls_id = nxt.get("tls")
            axis = self._axis_for(tls_id, nxt.get("link_index"))
            state = (snapshot.get("intersections") or {}).get(tls_id, {})
            queue = state.get("queue") or {}
            row: dict[str, Any] = {
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
        return {
            "id": ev.get("id"),
            "edge": ev.get("edge"),
            "speed": ev.get("speed"),
            "corridor": corridor,
        }

    def build_user_message(
        self,
        t: float,
        snapshot: Mapping[str, Any],
        blackboard: Iterable[Any] = (),
    ) -> str:
        import json

        enriched: dict[str, Any] = dict(snapshot)
        enriched["lead_time_s"] = self.lead_time_s
        enriched["evs"] = [
            self._ev_view(ev, snapshot) for ev in (snapshot.get("evs") or ())
        ]
        context = {
            "blackboard": [
                message.to_dict() if hasattr(message, "to_dict") else dict(message)
                for message in (blackboard or ())
            ]
        }
        return json.dumps(
            {"tick": t, "snapshot": enriched, "context": context},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def _corridor_index(
        self, snapshot: Mapping[str, Any]
    ) -> dict[CorridorKey, dict[str, Any]]:
        index: dict[CorridorKey, dict[str, Any]] = {}
        states = snapshot.get("intersections") or {}
        for ev in snapshot.get("evs") or ():
            for nxt in ev.get("next_tls") or ():
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
                    "group": self._group_for(tls_id, nxt.get("link_index")),
                    "multi_group": self._axis_is_multi_group(tls_id, axis),
                }
        return index

    def _lookup(
        self,
        key: CorridorKey,
        corridor: Mapping[CorridorKey, dict[str, Any]],
        t: float,
    ) -> tuple[Mapping[str, Any] | None, float]:
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

    def _review_preempt(
        self,
        raw: Mapping[str, Any],
        info: Mapping[str, Any],
        eta: float,
        notes: list[str],
    ) -> dict[str, Any] | None:
        tls_id = raw.get("tls")
        if not info.get("axis"):
            notes.append(f"{tls_id}: dropped, no mapped green phase for the EV approach")
            return None
        if eta > self.max_eta_s:
            notes.append(f"{tls_id}: dropped, ETA {eta:.1f}s > {self.max_eta_s:.0f}s horizon")
            return None
        fixed = dict(raw)
        fixed["type"] = "preempt"
        axis = info.get("axis")
        if axis and fixed.get("phase") != axis:
            notes.append(f"{tls_id}: phase {fixed.get('phase')!r} -> {axis} (EV approach)")
            fixed["phase"] = axis
        if info.get("multi_group") and info.get("group") is not None:
            fixed["phase_index"] = int(info["group"])
        else:
            fixed.pop("phase_index", None)
        fixed["eta_s"] = round(eta, 1)

        start = max(0.0, _as_float(fixed.get("start_in_s")))
        limit = self._lead_limit(eta, info.get("queue_needed"))
        if start - limit > 1e-6:
            notes.append(f"{tls_id}: start_in_s {start:.1f} -> {limit:.1f} (lead + queue)")
            start = limit
        fixed["start_in_s"] = round(start, 1)

        hold = min(max(_as_float(fixed.get("hold_s")), 0.0), MAX_HOLD_S)
        fixed["hold_s"] = round(hold, 1)
        ttl = _as_float(fixed.get("ttl_s"), 30.0)
        fixed["ttl_s"] = round(min(MAX_TTL_S, max(ttl, start + hold + 5.0)), 1)
        return fixed

    def _release_allowed(self, key: CorridorKey, active_evs: Iterable[str]) -> bool:
        return key[0] in set(active_evs) or key in self._plan or key in self._tracked

    @staticmethod
    def _release_directive(key: CorridorKey, plan: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "tls": key[1],
            "type": "preempt",
            "phase": plan.get("phase") or "NS",
            "ev": key[0],
            "hold_s": 0,
            "ttl_s": 10.0,
        }

    def _schedule(
        self,
        t: float,
        requests: dict[CorridorKey, dict[str, Any]],
        notes: list[str],
    ) -> list[dict[str, Any]]:
        by_tls: dict[str, list[tuple[CorridorKey, dict[str, Any]]]] = {}
        for key, request in sorted(requests.items()):
            by_tls.setdefault(request["tls"], []).append((key, request))
        scheduled: list[dict[str, Any]] = []
        for tls_id, items in sorted(by_tls.items()):
            placed: list[dict[str, Any]] = []
            for key, request in sorted(items, key=lambda kv: (kv[1]["eta_s"], kv[0])):
                eta_abs = t + request["eta_s"]
                start_abs = t + _as_float(request.get("start_in_s"))
                end_abs = start_abs + _as_float(request.get("hold_s"))
                conflict_end = start_abs
                for other in placed:
                    same_phase = (
                        other["phase"] == request["phase"]
                        and other.get("phase_index") == request.get("phase_index")
                    )
                    if (
                        not same_phase
                        and start_abs < other["end_abs"]
                        and other["start_abs"] < end_abs
                    ):
                        conflict_end = max(conflict_end, other["end_abs"])
                if conflict_end - start_abs > 1e-6:
                    notes.append(
                        f"{tls_id}: {key[0]} start delayed to {conflict_end - t:.1f}s "
                        f"(serve the earlier arrival first)"
                    )
                    start_abs = conflict_end
                hold = max(
                    _as_float(request.get("hold_s")),
                    eta_abs - start_abs + self.release_margin_s,
                )
                hold = min(hold, MAX_HOLD_S)
                start_rel = max(0.0, start_abs - t)
                if start_rel + hold > MAX_TTL_S:
                    hold = max(0.0, MAX_TTL_S - start_rel)
                    notes.append(f"{tls_id}: {key[0]} window clipped to the 60s TTL cap")
                if hold <= 0.0:
                    notes.append(f"{tls_id}: {key[0]} dropped, no room inside the TTL cap")
                    continue
                ttl = min(
                    MAX_TTL_S,
                    max(
                        _as_float(request.get("ttl_s"), 30.0),
                        start_rel + hold + 5.0,
                    ),
                )
                directive = {
                    k: v for k, v in request.items() if not k.startswith("_")
                }
                directive.update(
                    {
                        "start_in_s": round(start_rel, 1),
                        "hold_s": round(hold, 1),
                        "ttl_s": round(ttl, 1),
                        "eta_s": round(request["eta_s"], 1),
                    }
                )
                placed.append(
                    {
                        "key": key,
                        "tls": tls_id,
                        "phase": request["phase"],
                        "phase_index": request.get("phase_index"),
                        "eta_abs": eta_abs,
                        "start_abs": start_abs,
                        "end_abs": start_abs + hold,
                        "hold": hold,
                        "directive": directive,
                    }
                )
            scheduled.extend(placed)
        return scheduled

    def review(self, t: float, snapshot: Mapping[str, Any], call: AgentCall) -> AgentCall:
        notes: list[str] = []
        corridor = self._corridor_index(snapshot)
        active_evs = {ev.get("id") for ev in (snapshot.get("evs") or ())}
        for key, info in corridor.items():
            self._tracked[key] = {**info, "seen": t}

        incoming: dict[CorridorKey, dict[str, Any]] = {}
        releases: dict[CorridorKey, dict[str, Any]] = {}
        passthrough: list[Any] = []
        for raw in call.envelope.get("directives") or ():
            if not isinstance(raw, Mapping) or raw.get("type") != "preempt":
                passthrough.append(raw)
                continue
            key = (raw.get("ev"), raw.get("tls"))
            info, eta = self._lookup(key, corridor, t)
            if info is not None:
                fixed = self._review_preempt(raw, info, eta, notes)
                if fixed is not None:
                    incoming[key] = fixed
            elif _as_float(raw.get("hold_s")) == 0.0 and self._release_allowed(
                key, active_evs
            ):
                releases[key] = dict(raw)
                self._plan.pop(key, None)
            else:
                notes.append(f"dropped preempt for non-corridor pair {key}")

        requests: dict[CorridorKey, dict[str, Any]] = dict(incoming)
        for key, plan in sorted(self._plan.items()):
            if key in requests:
                continue
            info, eta = self._lookup(key, corridor, t)
            if info is None or eta <= 0.0 or eta > self.max_eta_s:
                continue
            start_abs = max(t, plan["start_abs"])
            end_abs = min(
                max(plan["end_abs"], t + eta + self.release_margin_s),
                start_abs + MAX_HOLD_S,
            )
            request = {
                "tls": key[1],
                "type": "preempt",
                "phase": plan["phase"],
                "phase_index": plan.get("phase_index"),
                "ev": key[0],
                "eta_s": round(eta, 1),
                "start_in_s": round(max(0.0, start_abs - t), 1),
                "hold_s": round(max(0.0, end_abs - start_abs), 1),
                "ttl_s": MAX_TTL_S,
                "_from_plan": True,
            }
            if request["phase_index"] is None:
                request.pop("phase_index")
            requests[key] = request

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
        new_plan: dict[CorridorKey, dict[str, Any]] = {}
        for entry in scheduled:
            new_plan[entry["key"]] = {
                "phase": entry["phase"],
                "tls": entry["tls"],
                "phase_index": entry.get("phase_index"),
                "start_abs": entry["start_abs"],
                "end_abs": entry["end_abs"],
                "hold": entry["hold"],
            }
        for key, plan in self._plan.items():
            if key not in new_plan and key not in releases and plan["end_abs"] > t:
                new_plan[key] = plan
        self._plan = new_plan

        source = "llm"
        if fallback_added and (call.failed or not incoming):
            source = "rules"

        directives: list[Any] = list(passthrough)
        directives.extend(
            entry["directive"] for entry in sorted(scheduled, key=lambda e: e["key"])
        )
        directives.extend(releases[key] for key in sorted(releases))

        envelope = dict(call.envelope)
        envelope["directives"] = directives
        if source == "rules" and not envelope.get("explanation"):
            envelope["explanation"] = "rule-based pre-emption fallback"

        alerts = [
            a
            for a in (call.envelope.get("alerts") or ())
            if not (isinstance(a, Mapping) and a.get("kind") == "ev_corridor")
        ]
        corridors: dict[str, list[str]] = {}
        for directive in directives:
            if (
                isinstance(directive, Mapping)
                and directive.get("type") == "preempt"
                and _as_float(directive.get("hold_s")) > 0
                and isinstance(directive.get("ev"), str)
            ):
                corridors.setdefault(directive["ev"], []).append(
                    str(directive.get("tls"))
                )
        for ev_id in sorted(corridors):
            alerts.append(
                {
                    "kind": "ev_corridor",
                    "ev": ev_id,
                    "tls": sorted(set(corridors[ev_id])),
                }
            )
        envelope["alerts"] = alerts

        schedule_log = []
        for entry in sorted(scheduled, key=lambda e: e["key"]):
            log_entry = {
                "tls": entry["tls"],
                "ev": entry["key"][0],
                "phase": entry["phase"],
                "start_s": round(max(0.0, entry["start_abs"] - t), 1),
                "end_s": round(max(0.0, entry["end_abs"] - t), 1),
            }
            if entry.get("phase_index") is not None:
                log_entry["phase_index"] = entry["phase_index"]
            schedule_log.append(log_entry)
        return AgentCall(
            role=call.role,
            envelope=envelope,
            response=call.response,
            error=call.error,
            prompt_hash=call.prompt_hash,
            attempts=call.attempts,
            effort=call.effort,
            review={
                "source": source,
                "notes": notes,
                "n_directives": len(directives),
                "schedule": schedule_log,
            },
        )

    def ask(
        self,
        t: float,
        snapshot: Mapping[str, Any],
        blackboard: Iterable[Any] = (),
        effort: str | None = None,
    ) -> AgentCall:
        return self.review(t, snapshot, super().ask(t, snapshot, blackboard, effort))

    def _fallback_proposals(
        self, t: float, snapshot: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        if not self.rule_fallback:
            return []
        corridor = self._corridor_index(snapshot)
        best: dict[str, tuple[float, dict[str, Any]]] = {}
        for ev in snapshot.get("evs") or ():
            ev_id = ev.get("id")
            for nxt in (ev.get("next_tls") or ())[: self.lookahead]:
                tls_id = nxt.get("tls")
                info = corridor.get((ev_id, tls_id))
                if info is None or info.get("axis") is None:
                    continue
                eta = _as_float(nxt.get("eta_s"))
                dist = _as_float(nxt.get("dist_m"))
                if eta > self.max_eta_s and dist > REACTIVE_DISTANCE_M:
                    continue
                proposal = {
                    "tls": tls_id,
                    "type": "preempt",
                    "phase": info.get("axis") or "NS",
                    "ev": ev_id,
                    "start_in_s": 0.0,
                    "hold_s": min(MAX_HOLD_S, eta + self.release_margin_s),
                    "eta_s": round(eta, 1),
                    "ttl_s": min(MAX_TTL_S, eta + self.release_margin_s + 5.0),
                }
                if info.get("multi_group") and info.get("group") is not None:
                    proposal["phase_index"] = int(info["group"])
                current = best.get(str(tls_id))
                if current is None or eta < current[0]:
                    best[str(tls_id)] = (eta, proposal)
        return [proposal for _, proposal in sorted(best.values(), key=lambda item: item[1]["tls"])]
