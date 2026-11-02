"""Snapshots and phase maps adapted to the integration environment."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from cotraffic.controllers.ev_preemption import phase_for
from cotraffic.controllers.pedestrian_rule import longest_waits

ETA_MIN_SPEED_M_S = 1.0
EV_HORIZON_S = 60.0
EV_LOOKAHEAD = 3
MAX_ALERTS = 5
MAX_BLACKBOARD = 6


@dataclass(frozen=True)
class PhaseMap:
    tls_id: str
    axis_by_action: tuple[str, ...]
    group_lanes: tuple[frozenset[str], ...]
    group_phases: tuple[tuple[int, ...], ...]
    link_phase: dict[int, int]
    crossing_axis: dict[str, str]
    crossing_phase: dict[str, int]
    ns_lanes: frozenset[str]
    ew_lanes: frozenset[str]

    def axis_for_link(self, link_index: int) -> str | None:
        phase = self.link_phase.get(int(link_index))
        if phase is None or phase >= len(self.axis_by_action):
            return None
        return self.axis_by_action[phase]

    def action_for_link(self, link_index: int) -> int | None:
        return self.link_phase.get(int(link_index))

    def multi_group(self, axis: str | None) -> bool:
        if axis is None:
            return False
        return sum(1 for label in self.axis_by_action if label == axis) > 1


@dataclass(frozen=True)
class PedestrianState:
    tls_id: str
    axis: str
    crossing_id: str
    waiting: int
    max_wait_s: float
    mean_wait_s: float
    phase_index: int | None = None


def _vote_axis(inter, phase: int) -> tuple[int, int]:
    ns = ew = 0
    for link in inter.links:
        if link.crossing or link.index not in inter.phase_links[phase]:
            continue
        side = inter.lane_side.get(link.in_lane, "north")
        if side in ("north", "south"):
            ns += 1
        else:
            ew += 1
    return ns, ew


def _axes(inter) -> tuple[str, ...]:
    count = len(inter.green_states)
    if count <= 1:
        return tuple("NS" for _ in range(count))
    if count == 2:
        return ("NS", "EW")
    axes = []
    for phase in range(count):
        ns, ew = _vote_axis(inter, phase)
        axes.append("NS" if ns >= ew else "EW")
    for missing in ("NS", "EW"):
        if missing in axes:
            continue
        victim = min(
            range(count),
            key=lambda i: (len(inter.phase_lanes[i]), -i),
        )
        axes[victim] = missing
    return tuple(axes)


def build_phase_map(inter) -> PhaseMap:
    axes = _axes(inter)
    link_phase = {
        index: phase_for(inter, index) for index in inter.link_by_index
    }
    crossing_axis: dict[str, str] = {}
    crossing_phase: dict[str, int] = {}
    for link in inter.crossing_links:
        phase = link_phase.get(link.index, 0)
        if link.crossing is not None:
            crossing_axis[link.crossing] = axes[phase]
            crossing_phase[link.crossing] = phase
    ns_lanes = frozenset(
        lane
        for phase, lanes in enumerate(inter.phase_lanes)
        if axes[phase] == "NS"
        for lane in lanes
    )
    ew_lanes = frozenset(
        lane
        for phase, lanes in enumerate(inter.phase_lanes)
        if axes[phase] == "EW"
        for lane in lanes
    )
    return PhaseMap(
        tls_id=inter.id,
        axis_by_action=axes,
        group_lanes=tuple(frozenset(lanes) for lanes in inter.phase_lanes),
        group_phases=tuple((phase,) for phase in range(len(axes))),
        link_phase=link_phase,
        crossing_axis=crossing_axis,
        crossing_phase=crossing_phase,
        ns_lanes=ns_lanes,
        ew_lanes=ew_lanes,
    )


def build_phase_maps(env) -> dict[str, PhaseMap]:
    return {tid: build_phase_map(inter) for tid, inter in env.intersections.items()}


def build_states(env, maps: Mapping[str, PhaseMap] | None = None) -> dict[str, dict[str, Any]]:
    maps = maps or build_phase_maps(env)
    measurable = getattr(env, "meas", None)
    halting = getattr(measurable, "halting", {}) or {}
    waiting = getattr(measurable, "waiting", {}) or {}
    now = float(getattr(env, "now", 0.0))
    states: dict[str, dict[str, Any]] = {}
    for tid, inter in sorted(env.intersections.items()):
        pm = maps[tid]
        lane_queues = {lane: int(halting.get(lane, 0) or 0) for lane in inter.in_lanes}
        lane_waiting = {lane: float(waiting.get(lane, 0.0) or 0.0) for lane in inter.in_lanes}
        in_transition = bool(inter.in_yellow)
        current_phase = int(inter.phase)
        ns_queue = sum(lane_queues.get(lane, 0) for lane in pm.ns_lanes)
        ew_queue = sum(lane_queues.get(lane, 0) for lane in pm.ew_lanes)
        states[tid] = {
            "tls_id": tid,
            "current_phase": current_phase,
            "current_axis": None if in_transition else pm.axis_by_action[current_phase],
            "time_in_phase": float(inter.green_elapsed(now)),
            "is_yellow": in_transition,
            "in_transition": in_transition,
            "total_queue": ns_queue + ew_queue,
            "total_waiting_time": sum(lane_waiting.values()),
            "ns_queue": ns_queue,
            "ew_queue": ew_queue,
            "ns_lanes": pm.ns_lanes,
            "ew_lanes": pm.ew_lanes,
            "group_lanes": pm.group_lanes,
            "group_phases": pm.group_phases,
            "axis_by_action": pm.axis_by_action,
            "lane_queues": lane_queues,
            "lane_waiting": lane_waiting,
        }
    return states


def build_evs(env) -> list[Any]:
    return list(getattr(env, "ev_states", ()) or ())


def build_pedestrians(
    env, maps: Mapping[str, PhaseMap] | None = None
) -> list[PedestrianState]:
    counts = getattr(env, "ped_waiting", {}) or {}
    if not counts:
        return []
    maps = maps or build_phase_maps(env)
    try:
        waits = longest_waits(env)
    except Exception:  # noqa: BLE001 - a PID-less test env has no person API
        waits = {}
    totals = getattr(env, "ped_wait_sum", {}) or {}
    owner = getattr(env, "crossing_owner", {}) or {}
    states: list[PedestrianState] = []
    for crossing, count in sorted(counts.items()):
        tls_id = owner.get(crossing)
        if tls_id is None:
            continue
        pm = maps.get(tls_id)
        if pm is None:
            continue
        axis = pm.crossing_axis.get(crossing)
        if axis is None:
            continue
        waiting = int(count or 0)
        max_wait = float(waits.get(crossing, 0.0) or 0.0)
        total_wait = float(totals.get(crossing, max_wait) or max_wait)
        mean_wait = total_wait / waiting if waiting else max_wait
        phase = pm.crossing_phase.get(crossing)
        states.append(
            PedestrianState(
                tls_id=tls_id,
                axis=axis,
                crossing_id=crossing,
                waiting=waiting,
                max_wait_s=max_wait,
                mean_wait_s=mean_wait,
                phase_index=phase if pm.multi_group(axis) else None,
            )
        )
    return states


def _eta_s(distance_m: float, speed_m_s: float) -> float:
    return round(distance_m / max(speed_m_s, ETA_MIN_SPEED_M_S), 1)


def _axis_sums(state: Mapping[str, Any], key: str, lanes: Iterable[str]) -> float:
    values = state.get(key) or {}
    return round(sum(float(values.get(lane, 0) or 0) for lane in lanes), 1)


def _intersection(
    state: Mapping[str, Any], neighbors: Mapping[str, str] | None = None
) -> dict[str, Any]:
    ns_lanes = tuple(state.get("ns_lanes") or ())
    ew_lanes = tuple(state.get("ew_lanes") or ())
    axis = state.get("current_axis")
    entry: dict[str, Any] = {
        "phase": axis if axis else "transition",
        "time_in_phase_s": round(float(state.get("time_in_phase", 0.0)), 1),
        "queue": {
            "ns": int(_axis_sums(state, "lane_queues", ns_lanes)),
            "ew": int(_axis_sums(state, "lane_queues", ew_lanes)),
        },
        "wait_s": {
            "ns": _axis_sums(state, "lane_waiting", ns_lanes),
            "ew": _axis_sums(state, "lane_waiting", ew_lanes),
        },
    }
    if neighbors:
        entry["neighbors"] = dict(neighbors)
    return entry


def _hot_ev(
    ev: Any, horizon_s: float = EV_HORIZON_S, lookahead: int = EV_LOOKAHEAD
) -> dict[str, Any] | None:
    speed = float(getattr(ev, "speed_m_s", 0.0))
    rows = list(getattr(ev, "next_tls", ()) or ())[: max(1, int(lookahead))]
    if not rows:
        return None
    etas = [float(row.distance_m) / max(speed, ETA_MIN_SPEED_M_S) for row in rows]
    if min(etas) > horizon_s:
        return None
    return {
        "id": getattr(ev, "veh_id", ""),
        "edge": getattr(ev, "edge_id", ""),
        "speed": round(speed, 1),
        "next_tls": [
            {
                "tls": upcoming.tls_id,
                "link_index": int(getattr(upcoming, "link_index", -1)),
                "dist_m": round(float(upcoming.distance_m), 1),
                "eta_s": _eta_s(float(upcoming.distance_m), speed),
                "signal": getattr(upcoming, "signal", ""),
            }
            for upcoming in rows
        ],
    }


def _pedestrian(state: Any) -> dict[str, Any]:
    def get(name: str, default: Any = None) -> Any:
        if isinstance(state, Mapping):
            return state.get(name, default)
        return getattr(state, name, default)

    row = {
        "tls": get("tls_id", ""),
        "axis": get("axis", ""),
        "waiting": int(get("waiting", 0) or 0),
        "max_wait_s": round(float(get("max_wait_s", 0.0) or 0.0), 1),
        "mean_wait_s": round(float(get("mean_wait_s", 0.0) or 0.0), 1),
    }
    phase = get("phase_index")
    if phase is not None:
        row["phase_index"] = int(phase)
    return row


def build_snapshot(
    t: float,
    states: Mapping[str, Mapping[str, Any]],
    neighbors: Mapping[str, Mapping[str, str]] | None = None,
    evs: Iterable[Any] = (),
    alerts: Iterable[Mapping[str, Any]] = (),
    blackboard: Iterable[Any] = (),
    pedestrians: Iterable[Any] = (),
    network: str = "",
    max_alerts: int = MAX_ALERTS,
    max_messages: int = MAX_BLACKBOARD,
    ev_horizon_s: float = EV_HORIZON_S,
    ev_lookahead: int = EV_LOOKAHEAD,
) -> dict[str, Any]:
    neighbor_map = neighbors or {}
    messages = [
        message.to_dict() if hasattr(message, "to_dict") else dict(message)
        for message in (blackboard or ())
    ][-max(0, int(max_messages)) :]
    alert_rows = [dict(alert) for alert in (alerts or ())][-max(0, int(max_alerts)) :]
    ev_rows = [
        row
        for row in (
            _hot_ev(ev, float(ev_horizon_s), int(ev_lookahead)) for ev in (evs or ())
        )
        if row is not None
    ]
    snapshot: dict[str, Any] = {
        "t": round(float(t), 1),
        "network": network,
        "tls_ids": sorted(states),
        "intersections": {
            tls_id: _intersection(states[tls_id], neighbor_map.get(tls_id))
            for tls_id in sorted(states)
        },
        "alerts": alert_rows,
        "evs": ev_rows,
        "blackboard": messages,
    }
    pedestrian_states = [_pedestrian(state) for state in (pedestrians or ())]
    if pedestrian_states:
        snapshot["pedestrians"] = pedestrian_states
    return snapshot
