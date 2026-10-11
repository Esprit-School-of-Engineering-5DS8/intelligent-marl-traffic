"""
environment/snapshot.py
Compact, LLM-friendly observation snapshot (plan section 4.2).

Pure functions over plain dicts/sequences: no TraCI, no SUMO import, fully
unit-testable. `build_snapshot` turns the controller states (plus EVs, code
alerts and blackboard messages) into a small JSON-ready document.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

ETA_MIN_SPEED_M_S = 1.0


def _eta_s(distance_m: float, speed_m_s: float) -> float:
    return round(distance_m / max(speed_m_s, ETA_MIN_SPEED_M_S), 1)


def _axis_sums(state: Mapping[str, Any], key: str, lanes: Iterable[str]) -> float:
    values = state.get(key) or {}
    return round(sum(float(values.get(lane, 0) or 0) for lane in lanes), 1)


def _intersection(state: Mapping[str, Any],
                  neighbors: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    ns_lanes = tuple(state.get("ns_lanes") or ())
    ew_lanes = tuple(state.get("ew_lanes") or ())
    axis = state.get("current_axis")
    entry: Dict[str, Any] = {
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


def _ev(ev: Any) -> Dict[str, Any]:
    speed = float(getattr(ev, "speed_m_s", 0.0))
    return {
        "id": getattr(ev, "veh_id", ""),
        "edge": getattr(ev, "edge_id", ""),
        "speed": round(speed, 1),
        "next_tls": [
            {
                "tls": upcoming.tls_id,
                # Raw signal-link index: lets topology-aware agents derive the
                # exact approach axis (Phase 4 Emergency agent).
                "link_index": int(getattr(upcoming, "link_index", -1)),
                "dist_m": round(float(upcoming.distance_m), 1),
                "eta_s": _eta_s(float(upcoming.distance_m), speed),
                "signal": getattr(upcoming, "signal", ""),
            }
            for upcoming in getattr(ev, "next_tls", ())
        ],
    }


def build_snapshot(t: float,
                   states: Mapping[str, Mapping[str, Any]],
                   neighbors: Optional[Mapping[str, Mapping[str, str]]] = None,
                   evs: Iterable[Any] = (),
                   alerts: Iterable[Mapping[str, Any]] = (),
                   blackboard: Iterable[Any] = ()) -> Dict[str, Any]:
    """One JSON-ready document shared by all slow-layer agents."""
    neighbor_map = neighbors or {}
    messages = [
        message.to_dict() if hasattr(message, "to_dict") else dict(message)
        for message in (blackboard or ())
    ]
    return {
        "t": round(float(t), 1),
        "intersections": {
            tls_id: _intersection(states[tls_id], neighbor_map.get(tls_id))
            for tls_id in sorted(states)
        },
        "alerts": [dict(alert) for alert in (alerts or ())],
        "evs": [_ev(ev) for ev in (evs or ())],
        "blackboard": messages,
    }
