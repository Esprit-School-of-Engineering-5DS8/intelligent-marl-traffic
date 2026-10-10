"""
environment/ev.py
Emergency-vehicle sensing: compact, typed EV states.

The dataclasses are pure (no TraCI), so policies over them are unit-testable;
`get_active_evs()` is the only TraCI-touching function and imports TraCI
lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

EMERGENCY_CLASS = "emergency"


@dataclass(frozen=True)
class UpcomingTLS:
    """One traffic light ahead of an EV on its current route."""

    tls_id: str
    link_index: int
    distance_m: float
    signal: str


@dataclass(frozen=True)
class EVState:
    """Snapshot of one active emergency vehicle."""

    veh_id: str
    edge_id: str
    lane_id: str
    speed_m_s: float
    next_tls: Tuple[UpcomingTLS, ...]


def get_active_evs() -> List[EVState]:
    """Read all active emergency vehicles and their upcoming traffic lights."""
    from environment._bootstrap import ensure_sumo_on_path

    ensure_sumo_on_path()
    import traci

    evs: List[EVState] = []
    for veh_id in traci.vehicle.getIDList():
        if traci.vehicle.getVehicleClass(veh_id) != EMERGENCY_CLASS:
            continue
        edge_id = traci.vehicle.getRoadID(veh_id)
        if not edge_id or edge_id.startswith(":"):
            continue
        next_tls = tuple(
            UpcomingTLS(tls_id, int(link_index), float(distance), signal)
            for tls_id, link_index, distance, signal in traci.vehicle.getNextTLS(veh_id)
        )
        evs.append(EVState(
            veh_id=veh_id,
            edge_id=edge_id,
            lane_id=traci.vehicle.getLaneID(veh_id),
            speed_m_s=float(traci.vehicle.getSpeed(veh_id)),
            next_tls=next_tls,
        ))
    return evs
