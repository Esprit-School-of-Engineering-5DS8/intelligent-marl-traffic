"""
environment/topology.py
Network topology derived from the TLS programs, not from lane-ID strings.

`build_topology` is a pure function over (phase durations/states, controlled
links), so it is unit-testable without SUMO. `discover_topology` is the thin
TraCI wrapper used at runtime.

Conventions:
- Programs with up to two distinct **vehicle-green lane sets** (all grid and
  pedestrian nets) behave exactly as before: the first set in program order is
  North-South (action 0), the second is East-West (action 1).
- Programs with three or more sets (real cities: separate protected-turn or
  one-way phases, e.g. MoST Monaco) are clustered into the same two axes by
  lane heading (lane -> edge direction), and each *set* keeps its own action:
  the base controller may select any group, while the axis labels only drive
  the LLM/directive layer. When a heading vote cannot fill both axes, the set
  with the fewest lanes is moved to the empty axis (deterministic tie-break).
- The first green phase in a program is pinned by default; all canonical green
  phases are held with a very long phase duration so SUMO's built-in program
  timer can never advance a phase behind the controller's back.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

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


@dataclass(frozen=True)
class GreenGroup:
    """
    One selectable controller action: the phases that run the exact same set
    of vehicle-green lanes (main phase plus end-of-green grace twins) and the
    axis this set was clustered into ("NS" / "EW").
    """

    lanes: FrozenSet[str]
    phases: Tuple[int, ...]
    canonical_phase: int
    axis: str


@dataclass
class TLSTopology:
    """Per-intersection signal layout discovered from its TLS program."""

    tls_id: str
    phases: Tuple[Phase, ...]
    ns_lanes: FrozenSet[str]
    ew_lanes: FrozenSet[str]
    ns_green_phase: int
    ew_green_phase: int
    # All phases whose *vehicle* links are green, per axis. On pedestrian nets
    # the program has six phases: e.g. NS green, NS green with pedestrian
    # signals red (end-of-green grace), NS yellow, EW green, ... — so several
    # phases share an axis's green movements.
    ns_green_phases: FrozenSet[int] = frozenset()
    ew_green_phases: FrozenSet[int] = frozenset()
    # Selectable actions, in program order. Two groups on the 2x2/3x3 grids
    # (identical to the binary NS/EW model); up to three on N-phase real
    # networks, where the axis of each group still labels the LLM interface.
    groups: Tuple[GreenGroup, ...] = ()

    @property
    def controlled_lanes(self) -> FrozenSet[str]:
        return self.ns_lanes | self.ew_lanes

    @property
    def group_lanes(self) -> Tuple[FrozenSet[str], ...]:
        """Lane set served by each action (in action order)."""
        return tuple(group.lanes for group in self.groups)

    @property
    def group_phases(self) -> Tuple[Tuple[int, ...], ...]:
        """All green phases of each action (in action order)."""
        return tuple(group.phases for group in self.groups)

    @property
    def axis_by_action(self) -> Tuple[str, ...]:
        return tuple(group.axis for group in self.groups)

    def axis_for_action(self, action: int) -> str:
        return self.groups[action].axis

    def group_phase_for_action(self, action: int) -> int:
        """
        Canonical (pinned) green phase of one action/group.

        Two-group programs keep the historical modulo convention
        (even -> NS, odd -> EW) used by the binary policies.
        """
        if len(self.groups) == 2:
            return self.ns_green_phase if action % 2 == 0 else self.ew_green_phase
        return self.groups[action].canonical_phase

    def green_phase_for_action(self, action: int) -> int:
        """Backwards-compatible alias of `group_phase_for_action`."""
        return self.group_phase_for_action(action)

    def is_green_phase(self, index: int) -> bool:
        """True when the phase runs green vehicle movements (either axis)."""
        return index in self.ns_green_phases or index in self.ew_green_phases

    def is_hold_phase(self, index: int) -> bool:
        """Canonical green phases the controller pins with a long duration."""
        return any(group.canonical_phase == index for group in self.groups) \
            or index == self.ns_green_phase or index == self.ew_green_phase

    def axis_for_phase(self, index: int) -> Optional[str]:
        """Axis whose vehicles are green in this phase, or None."""
        for group in self.groups:
            if index in group.phases:
                return group.axis
        if index in self.ns_green_phases:
            return "NS"
        if index in self.ew_green_phases:
            return "EW"
        return None

    def action_for_link(self, link_index: int) -> Optional[int]:
        """
        Action (group index) whose canonical green phase serves this signal
        link, or None if no green phase serves it.

        Used to translate an emergency vehicle's upcoming TLS link into the
        exact phase it needs — precise even when the vehicle turns, and exact
        across the multiple green sets of an N-phase program.
        """
        for action, phase_index in enumerate(self._canonical_phases()):
            state = self.phases[phase_index].state
            if 0 <= link_index < len(state) and state[link_index] in GREEN_CHARS:
                return action
        return None

    def axis_for_link(self, link_index: int) -> Optional[str]:
        """Axis of the action serving this link, or None."""
        action = self.action_for_link(link_index)
        if action is None or action >= len(self.groups):
            return None
        return self.groups[action].axis

    def _canonical_phases(self) -> List[int]:
        if self.groups:
            return [group.canonical_phase for group in self.groups]
        return [self.ns_green_phase, self.ew_green_phase]

    def phase(self, index: int) -> Phase:
        return self.phases[index]

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


def _is_vehicle_lane(lane: object) -> bool:
    """Internal lanes (walkingareas, crossings) are not vehicle approaches."""
    return bool(lane) and not str(lane).startswith(":")


def _vehicle_green_lanes(state: str, links: Sequence[Sequence[Tuple[str, ...]]]) -> FrozenSet[str]:
    """Lanes with a green *vehicle* link in this phase (pedestrian links excluded)."""
    lanes = set()
    for i, link in enumerate(links):
        if i < len(state) and state[i] in GREEN_CHARS and link and _is_vehicle_lane(link[0][0]):
            lanes.add(link[0][0])
    return frozenset(lanes)


def _vote_axis(lanes: FrozenSet[str], lane_headings: Mapping[str, Tuple[float, float]]) -> Tuple[int, int]:
    """Count lanes heading north/south vs east/west in one green set."""
    ns_votes = ew_votes = 0
    for lane in sorted(lanes):
        heading = lane_headings.get(lane)
        if heading is None:
            continue
        dx, dy = heading
        if abs(dy) >= abs(dx):
            ns_votes += 1
        else:
            ew_votes += 1
    return ns_votes, ew_votes


def _assign_axes(sets: Sequence[Tuple[FrozenSet[str], Sequence[int]]],
                 lane_headings: Optional[Mapping[str, Tuple[float, float]]]) -> List[str]:
    """
    Cluster the distinct vehicle-green lane sets into two axes.

    - 1 or 2 sets: keep the legacy phase-order convention (first = NS,
      second = EW) — grids and pedestrian nets never need geometry.
    - 3+ sets: vote each set's lane headings onto NS/EW. If an axis ends up
      empty (e.g. every phase of a diagonal junction heads east-west), the set
      with the fewest lanes moves there (ties: the latest set in program
      order). Deterministic and unit-testable.
    """
    count = len(sets)
    if count == 1:
        return ["NS"]
    if count == 2:
        return ["NS", "EW"]
    if lane_headings is None:
        return ["NS"] + ["EW"] * (count - 1)

    axes = []
    votes = []
    for lanes, _ in sets:
        ns_votes, ew_votes = _vote_axis(lanes, lane_headings)
        votes.append((ns_votes, ew_votes))
        axes.append("NS" if ns_votes >= ew_votes else "EW")

    for missing in ("NS", "EW"):
        if missing in axes:
            continue
        victim = min(
            range(count),
            key=lambda i: (len(sets[i][0]), -min(sets[i][1])),
        )
        axes[victim] = missing
    return axes


def build_topology(
    tls_id: str,
    phases: Sequence[Tuple[float, str]],
    links: Sequence[Sequence[Tuple[str, ...]]],
    lane_headings: Optional[Mapping[str, Tuple[float, float]]] = None,
) -> TLSTopology:
    """
    Build a TLSTopology from raw program data (pure, no SUMO needed).

    `lane_headings` maps vehicle lane id -> (dx, dy) of the lane's travel
    direction (first -> last shape point); it is only consulted for N-phase
    programs (3+ green sets) to label each set's axis.
    """
    parsed = tuple(Phase(i, float(duration), state) for i, (duration, state) in enumerate(phases))

    # Group phases by the set of vehicle lanes they run green. Plain grids have
    # two groups (NS, EW); pedestrian programs add extra phases that repeat a
    # group's vehicle movements while the pedestrian signals change (e.g. the
    # 5 s end-of-green grace where crossings turn red before the vehicle
    # yellow). Real networks can have three sets — protected turns or separate
    # one-way phases — which stay separate controller actions.
    sets: Dict[FrozenSet[str], List[int]] = {}
    for phase in parsed:
        lanes = _vehicle_green_lanes(phase.state, links)
        if lanes:
            sets.setdefault(lanes, []).append(phase.index)
    if not sets:
        raise ValueError(f"{tls_id}: no vehicle green phases found")
    if len(sets) < 2:
        raise ValueError(
            f"{tls_id}: expected at least 2 distinct vehicle green phases "
            f"(NS, EW), found {len(sets)}"
        )

    set_items = list(sets.items())
    axes = _assign_axes(set_items, lane_headings)
    groups = tuple(
        GreenGroup(
            lanes=lanes,
            phases=tuple(indices),
            canonical_phase=min(indices),
            axis=axis,
        )
        for (lanes, indices), axis in zip(set_items, axes)
    )

    ns_groups = [group for group in groups if group.axis == "NS"]
    ew_groups = [group for group in groups if group.axis == "EW"]
    ns_lanes = frozenset().union(*(group.lanes for group in ns_groups)) if ns_groups else frozenset()
    ew_lanes = frozenset().union(*(group.lanes for group in ew_groups)) if ew_groups else frozenset()
    ns_phases = frozenset().union(*(group.phases for group in ns_groups)) if ns_groups else frozenset()
    ew_phases = frozenset().union(*(group.phases for group in ew_groups)) if ew_groups else frozenset()

    return TLSTopology(
        tls_id=tls_id,
        phases=parsed,
        ns_lanes=ns_lanes,
        ew_lanes=ew_lanes - ns_lanes,
        ns_green_phase=ns_groups[0].canonical_phase if ns_groups else groups[0].canonical_phase,
        ew_green_phase=ew_groups[0].canonical_phase if ew_groups else groups[-1].canonical_phase,
        ns_green_phases=ns_phases,
        ew_green_phases=ew_phases,
        groups=groups,
    )


def discover_topology(tls_id: str) -> TLSTopology:
    """Read the active program of a live TLS through TraCI and build its topology."""
    from environment._bootstrap import ensure_sumo_on_path

    ensure_sumo_on_path()
    import traci

    program = traci.trafficlight.getAllProgramLogics(tls_id)[0]
    phases = [(p.duration, p.state) for p in program.phases]
    links = traci.trafficlight.getControlledLinks(tls_id)
    topology = build_topology(tls_id, phases, links)
    if len(topology.groups) <= 2:
        # Two-set programs follow the fixed phase-order convention; no
        # geometry is consulted and grid behavior stays byte-identical.
        return topology

    lane_headings: Dict[str, Tuple[float, float]] = {}
    for group in topology.groups:
        for lane in sorted(group.lanes):
            if lane in lane_headings:
                continue
            shape = traci.lane.getShape(lane)
            if len(shape) >= 2:
                lane_headings[lane] = (shape[-1][0] - shape[0][0],
                                       shape[-1][1] - shape[0][1])
    return build_topology(tls_id, phases, links, lane_headings)


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
    # sorted(): set iteration order depends on per-process string hashing, and
    # this map ends up in LLM prompts; unsorted it breaks record/replay.
    for tls_id, from_nodes in sorted(sources.items()):
        if tls_id not in coords:
            continue
        x, y = coords[tls_id]
        labeled: Dict[str, str] = {}
        for from_node in sorted(from_nodes):
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
