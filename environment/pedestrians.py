"""
environment/pedestrians.py
Pedestrian sensing: compact, typed waiting states per TLS crossing.

The aggregation is a pure function over `(person_id, crossing_id, waiting_s)`
records plus a crossing -> (TLS, axis) map, so it is unit-testable without
SUMO. `get_pedestrian_states()` is the thin TraCI reader.

Mapping (verified on the generated ped net):
- a person waiting at a crossing stands on a walkingarea (`:A1_w3`) with
  `getNextEdge()` pointing at the crossing edge (`:A1_c2`);
- `crossing_axis_map()` resolves each crossing edge to the TLS and to the
  axis whose vehicle green serves it, from the controlled links and the
  discovered topology (`TLSTopology.action_for_link`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# Binary action -> axis (same convention as the fast layer / directive schema).
_AXIS_BY_ACTION = {0: "NS", 1: "EW"}


@dataclass(frozen=True)
class PedestrianWaiting:
    """One person currently waiting at a crossing."""

    person_id: str
    crossing_id: str
    waiting_s: float


@dataclass(frozen=True)
class PedestrianState:
    """Aggregated waiting pedestrians at one crossing of one TLS."""

    tls_id: str
    axis: str               # "NS"/"EW": the green phase serving the crossing
    crossing_id: str
    waiting: int
    max_wait_s: float
    mean_wait_s: float


def is_crossing_edge(edge_id: str) -> bool:
    """:A1_c2 style crossing edges (internal, vClass pedestrian) only."""
    if not edge_id or not edge_id.startswith(":"):
        return False
    parts = edge_id[1:].split("_")
    return len(parts) == 2 and parts[1].startswith("c") and parts[1][1:].isdigit()


def crossing_tls(crossing_id: str) -> Optional[str]:
    if not is_crossing_edge(crossing_id):
        return None
    return crossing_id[1:].split("_", 1)[0] or None


def aggregate_waiting(
    records: Iterable[PedestrianWaiting],
    crossing_axis: Mapping[str, Tuple[str, str]],
) -> List[PedestrianState]:
    """Group waiting persons into per-(TLS, axis, crossing) states."""
    groups: Dict[Tuple[str, str, str], List[float]] = {}
    for record in records:
        mapping = crossing_axis.get(record.crossing_id)
        if mapping is None:
            continue
        tls_id, axis = mapping
        groups.setdefault((tls_id, axis, record.crossing_id), []).append(record.waiting_s)
    states: List[PedestrianState] = []
    for (tls_id, axis, crossing_id), waits in sorted(groups.items()):
        states.append(PedestrianState(
            tls_id=tls_id, axis=axis, crossing_id=crossing_id,
            waiting=len(waits), max_wait_s=max(waits),
            mean_wait_s=sum(waits) / len(waits),
        ))
    return states


def crossing_axis_map(topologies: Mapping[str, Any]) -> Dict[str, Tuple[str, str]]:
    """crossing edge id -> (TLS, axis) from the live controlled links."""
    from environment._bootstrap import ensure_sumo_on_path

    ensure_sumo_on_path()
    import traci

    mapping: Dict[str, Tuple[str, str]] = {}
    for tls_id, topology in topologies.items():
        for link_index, link in enumerate(traci.trafficlight.getControlledLinks(tls_id)):
            if not link or len(link[0]) < 2:
                continue
            from_lane, to_lane = str(link[0][0]), str(link[0][1])
            if not from_lane.startswith(":"):
                continue  # vehicle link
            crossing_id = to_lane.rsplit("_", 1)[0]
            if not is_crossing_edge(crossing_id):
                continue
            action = topology.action_for_link(link_index)
            if action is None:
                continue
            mapping[crossing_id] = (tls_id, _AXIS_BY_ACTION[action])
    return mapping


def _waiting_crossing(pid: str, traci_module: Any) -> Optional[str]:
    candidates = (traci_module.person.getNextEdge(pid), traci_module.person.getRoadID(pid))
    for candidate in candidates:
        candidate = str(candidate or "")
        if is_crossing_edge(candidate):
            return candidate
    return None


def get_pedestrian_states(topologies: Mapping[str, Any],
                          min_wait_s: float = 3.0,
                          crossing_axis: Optional[Mapping[str, Tuple[str, str]]] = None,
                          ) -> List[PedestrianState]:
    """Read all waiting pedestrians and aggregate them per crossing.

    `crossing_axis` may be precomputed once per run (`crossing_axis_map`) to
    avoid re-reading the controlled links every step.
    """
    from environment._bootstrap import ensure_sumo_on_path

    ensure_sumo_on_path()
    import traci

    if crossing_axis is None:
        crossing_axis = crossing_axis_map(topologies)
    records: List[PedestrianWaiting] = []
    for pid in traci.person.getIDList():
        waiting = float(traci.person.getWaitingTime(pid))
        if waiting < min_wait_s:
            continue
        crossing = _waiting_crossing(pid, traci)
        if crossing is None or crossing not in crossing_axis:
            continue
        records.append(PedestrianWaiting(pid, crossing, waiting))
    return aggregate_waiting(records, crossing_axis)
