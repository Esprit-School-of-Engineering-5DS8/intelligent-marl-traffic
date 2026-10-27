"""Typed emergency-vehicle states read from a SUMO connection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UpcomingTLS:
    tls_id: str
    link_index: int
    distance_m: float
    signal: str


@dataclass(frozen=True)
class EVState:
    veh_id: str
    edge_id: str
    lane_id: str
    speed_m_s: float
    next_tls: tuple[UpcomingTLS, ...]


def read_ev_states(conn: Any, ev_ids: set[str] | frozenset[str]) -> list[EVState]:
    states: list[EVState] = []
    for veh_id in sorted(ev_ids):
        edge_id = str(conn.vehicle.getRoadID(veh_id) or "")
        if not edge_id or edge_id.startswith(":"):
            continue
        upcoming = conn.vehicle.getNextTLS(veh_id)
        if not upcoming:
            continue
        states.append(
            EVState(
                veh_id=veh_id,
                edge_id=edge_id,
                lane_id=str(conn.vehicle.getLaneID(veh_id) or ""),
                speed_m_s=float(conn.vehicle.getSpeed(veh_id)),
                next_tls=tuple(
                    UpcomingTLS(
                        tls_id=str(tls),
                        link_index=int(link),
                        distance_m=float(distance),
                        signal=str(signal),
                    )
                    for tls, link, distance, signal in upcoming
                ),
            )
        )
    return states
