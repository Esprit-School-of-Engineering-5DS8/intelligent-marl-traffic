"""
environment/topology.py
Network topology derived from the TLS programs, not from lane-ID strings.

`build_topology` is a pure function over (phase durations/states, controlled
links), so it is unit-testable without SUMO. `discover_topology` is the thin
TraCI wrapper used at runtime.

Conventions:
- The first green phase in the program is North-South (action 0), the second
  is East-West (action 1) — matches the 2x2/3x3 grids.
- Green phases are held with a very long phase duration so SUMO's built-in
  program timer can never advance a phase behind the controller's back.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Sequence, Tuple

GREEN_CHARS = "Gg"
YELLOW_CHARS = "yY"
GREEN_HOLD_S = 100000.0


@dataclass(frozen=True)
class Phase:
    """One phase of a TLS program."""

    index: int
    duration: float
    state: str

    @property
    def is_green(self) -> bool:
        return any(c in GREEN_CHARS for c in self.state)

    @property
    def is_yellow(self) -> bool:
        return any(c in YELLOW_CHARS for c in self.state)

    @property
    def is_clearance(self) -> bool:
        """All-red / pedestrian-clearance phase between two green phases."""
        return not self.is_green and not self.is_yellow


@dataclass
class TLSTopology:
    """Per-intersection signal layout discovered from its TLS program."""

    tls_id: str
    phases: Tuple[Phase, ...]
    ns_lanes: FrozenSet[str]
    ew_lanes: FrozenSet[str]
    ns_green_phase: int
    ew_green_phase: int

    @property
    def controlled_lanes(self) -> FrozenSet[str]:
        return self.ns_lanes | self.ew_lanes

    def green_phase_for_action(self, action: int) -> int:
        """Map the binary action space (0 = NS, 1 = EW) to a green phase index."""
        return self.ns_green_phase if action % 2 == 0 else self.ew_green_phase

    def action_for_link(self, link_index: int) -> Optional[int]:
        """
        Action (0 = NS, 1 = EW) whose green phase serves this signal link,
        or None if neither green phase serves it.

        Used to translate an emergency vehicle's upcoming TLS link into the
        phase it needs — exact even when the vehicle turns.
        """
        for action, phase_index in ((0, self.ns_green_phase), (1, self.ew_green_phase)):
            state = self.phases[phase_index].state
            if 0 <= link_index < len(state) and state[link_index] in GREEN_CHARS:
                return action
        return None

    def phase(self, index: int) -> Phase:
        return self.phases[index]

    def is_green_phase(self, index: int) -> bool:
        return self.phases[index].is_green

    def transition_path(self, from_phase: int, to_phase: int) -> Tuple[int, ...]:
        """
        Phases to apply, in order, to move from one phase to another.

        Walks the program cyclically, preserving clearance/yellow intermediates
        (green -> clearance -> yellow -> target). Includes the target phase,
        excludes the starting phase.
        """
        path: List[int] = []
        index = from_phase
        for _ in range(len(self.phases)):
            index = (index + 1) % len(self.phases)
            path.append(index)
            if index == to_phase:
                return tuple(path)
        raise ValueError(f"{self.tls_id}: phase {to_phase} unreachable from {from_phase}")


def _lanes_green_in(state: str, links: Sequence[Sequence[Tuple[str, ...]]]) -> FrozenSet[str]:
    lanes = set()
    for i, link in enumerate(links):
        if i < len(state) and state[i] in GREEN_CHARS and link:
            lanes.add(link[0][0])
    return frozenset(lanes)


def build_topology(
    tls_id: str,
    phases: Sequence[Tuple[float, str]],
    links: Sequence[Sequence[Tuple[str, ...]]],
) -> TLSTopology:
    """Build a TLSTopology from raw program data (pure, no SUMO needed)."""
    parsed = tuple(Phase(i, float(duration), state) for i, (duration, state) in enumerate(phases))
    green_phases = [p for p in parsed if p.is_green]
    if len(green_phases) != 2:
        raise ValueError(
            f"{tls_id}: expected exactly 2 green phases (NS, EW), found {len(green_phases)}"
        )

    ns_green, ew_green = green_phases[0].index, green_phases[1].index
    ns_lanes = _lanes_green_in(parsed[ns_green].state, links)
    ew_lanes = _lanes_green_in(parsed[ew_green].state, links) - ns_lanes
    return TLSTopology(
        tls_id=tls_id,
        phases=parsed,
        ns_lanes=ns_lanes,
        ew_lanes=ew_lanes,
        ns_green_phase=ns_green,
        ew_green_phase=ew_green,
    )


def discover_topology(tls_id: str) -> TLSTopology:
    """Read the active program of a live TLS through TraCI and build its topology."""
    from environment._bootstrap import ensure_sumo_on_path

    ensure_sumo_on_path()
    import traci

    program = traci.trafficlight.getAllProgramLogics(tls_id)[0]
    phases = [(p.duration, p.state) for p in program.phases]
    links = traci.trafficlight.getControlledLinks(tls_id)
    return build_topology(tls_id, phases, links)


def net_file_from_sumocfg(sumocfg_path: str) -> str:
    """Resolve the <net-file> entry of a .sumocfg to an absolute path."""
    root = ET.parse(sumocfg_path).getroot()
    node = root.find(".//net-file")
    if node is None or not node.get("value"):
        raise ValueError(f"{sumocfg_path}: no <net-file> entry found")
    base_dir = os.path.dirname(os.path.abspath(sumocfg_path))
    return os.path.normpath(os.path.join(base_dir, node.get("value")))


def neighbor_map_from_net(net_file: str, tls_ids: Iterable[str]) -> Dict[str, Dict[str, str]]:
    """
    Map each TLS to its directly connected TLS neighbors by compass direction.

    An edge whose `from` and `to` junctions are both TLS marks a neighbor; the
    direction is derived from junction coordinates (SUMO y grows north).
    """
    root = ET.parse(net_file).getroot()
    tls_set = set(tls_ids)
    coords = {
        junction.get("id"): (float(junction.get("x")), float(junction.get("y")))
        for junction in root.findall("junction")
    }

    sources: Dict[str, set] = {}
    for edge in root.findall("edge"):
        if edge.get("function") == "internal":
            continue
        from_node, to_node = edge.get("from"), edge.get("to")
        if to_node in tls_set and from_node in tls_set:
            sources.setdefault(to_node, set()).add(from_node)

    neighbors: Dict[str, Dict[str, str]] = {}
    for tls_id, from_nodes in sources.items():
        if tls_id not in coords:
            continue
        x, y = coords[tls_id]
        labeled: Dict[str, str] = {}
        for from_node in from_nodes:
            if from_node not in coords:
                continue
            dx = coords[from_node][0] - x
            dy = coords[from_node][1] - y
            if abs(dx) >= abs(dy):
                label = "E" if dx > 0 else "W"
            else:
                label = "N" if dy > 0 else "S"
            labeled[label] = from_node
        neighbors[tls_id] = labeled
    return neighbors
