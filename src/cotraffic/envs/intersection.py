"""Runtime model of one signalised intersection.

The candidate actions of an agent are the green phases of the intersection's
default SUMO program. Switching goes through a yellow state computed from the two
green states, then the new green is set. All signal states are written with
``setRedYellowGreenState``, so SUMO's own program is bypassed while an agent is
in control.
"""

from __future__ import annotations

from dataclasses import dataclass

from cotraffic.networks.topology import SIDES, TLSGeometry

GREEN = "Gg"
STOP = "rs"


def is_green_state(state: str) -> bool:
    return "y" not in state and "u" not in state and any(c in GREEN for c in state)


def _vehicle_part(state: str, crossings: frozenset[int]) -> str:
    return "".join(c for i, c in enumerate(state) if i not in crossings)


def green_states(phase_states: list[str], crossings: frozenset[int] = frozenset()) -> list[str]:
    """Distinct green states of a program, in program order.

    SUMO programs with pedestrian crossings contain, for each vehicle phase, a
    short variant where only the crossings are red (pedestrian clearance). Those
    variants are not separate decisions, so states whose vehicle signals are
    identical are merged, keeping the variant with the most green signals.
    """
    out: list[str] = []
    for s in phase_states:
        if not is_green_state(s):
            continue
        key = _vehicle_part(s, crossings)
        same = [i for i, kept in enumerate(out) if _vehicle_part(kept, crossings) == key]
        if not same:
            out.append(s)
        elif sum(c in GREEN for c in s) > sum(c in GREEN for c in out[same[0]]):
            out[same[0]] = s
    return out


def yellow_state(old: str, new: str, crossings: frozenset[int] = frozenset()) -> str:
    """Transition state: vehicle links that lose their green turn yellow.

    Links that are red in ``old`` stay red during the transition even if they are
    green in ``new``; they only turn green when the new phase starts. Crossings
    that lose their green turn red at once, so no pedestrian starts crossing
    during the vehicle yellow.
    """
    if len(old) != len(new):
        raise ValueError("states of different length")
    out = []
    for i, (o, n) in enumerate(zip(old, new, strict=True)):
        if o in GREEN and n not in GREEN:
            out.append("r" if i in crossings else "y")
        elif o in GREEN:
            out.append(o)
        else:
            out.append("r")
    return "".join(out)


@dataclass(frozen=True)
class Link:
    """One controlled signal. For a pedestrian crossing SUMO reports the link as
    walking area -> crossing, so ``crossing`` holds the crossing edge id."""

    index: int
    in_lane: str
    out_lane: str
    crossing: str | None = None


class Intersection:
    """Phase bookkeeping for one traffic light; all times are simulation seconds."""

    def __init__(
        self,
        conn,
        tls_id: str,
        geometry: TLSGeometry,
        crossing_edges: set[str],
        yellow_time: float,
        lanes_per_side: int,
    ):
        self.conn = conn
        self.id = tls_id
        self.geometry = geometry
        self.yellow_time = yellow_time

        self.links: list[Link] = []
        for index, group in enumerate(conn.trafficlight.getControlledLinks(tls_id)):
            if not group:
                continue
            in_lane, out_lane, _via = group[0]
            in_edge, out_edge = in_lane.rsplit("_", 1)[0], out_lane.rsplit("_", 1)[0]
            crossing = next((e for e in (out_edge, in_edge) if e in crossing_edges), None)
            self.links.append(Link(index, in_lane, out_lane, crossing))
        self.n_signals = len(conn.trafficlight.getRedYellowGreenState(tls_id))

        program = conn.trafficlight.getProgram(tls_id)
        logic = next(
            lg for lg in conn.trafficlight.getAllProgramLogics(tls_id) if lg.programID == program
        )
        self.program_id = program
        self.crossing_signals = frozenset(link.index for link in self.links if link.crossing)
        self.green_states = green_states([p.state for p in logic.phases], self.crossing_signals)
        if not self.green_states:
            raise ValueError(f"traffic light {tls_id} has no green phase")
        self.n_phases = len(self.green_states)
        self.phase_links = [
            frozenset(link.index for link in self.links if s[link.index] in GREEN)
            for s in self.green_states
        ]

        vehicle_links = [link for link in self.links if not link.crossing]
        self.crossing_links = [link for link in self.links if link.crossing]
        self.in_lanes = _unique(link.in_lane for link in vehicle_links)
        self.out_lanes = _unique(link.out_lane for link in vehicle_links)
        self.crossings = sorted(
            _unique(link.crossing for link in self.crossing_links),
            key=lambda c: (SIDES.index(geometry.crossing_side.get(c, "north")), c),
        )
        self.link_by_index = {link.index: link for link in self.links}
        self.lane_side = {
            lane: geometry.edge_side.get(lane.rsplit("_", 1)[0], "north") for lane in self.in_lanes
        }
        self.side_lanes = {side: [] for side in SIDES}
        for lane in sorted(self.in_lanes, key=lambda ln: int(ln.rsplit("_", 1)[1])):
            self.side_lanes[self.lane_side[lane]].append(lane)
        self.lanes_per_side = lanes_per_side
        self.phase_lanes = [
            frozenset(link.in_lane for link in vehicle_links if link.index in links)
            for links in self.phase_links
        ]
        self.lane_links = {
            lane: [lk for lk in vehicle_links if lk.in_lane == lane] for lane in self.in_lanes
        }

        self.phase = 0
        self.next_phase: int | None = None
        self.yellow_left = 0.0
        self.green_since = 0.0
        self.link_last_green: dict[int, float] = {}

    # ------------------------------------------------------------------ control
    def start(self, now: float, phase: int = 0) -> None:
        self.phase = phase
        self.next_phase = None
        self.yellow_left = 0.0
        self.green_since = now
        self.link_last_green = {link.index: now for link in self.links}
        self.conn.trafficlight.setRedYellowGreenState(self.id, self.green_states[phase])

    @property
    def in_yellow(self) -> bool:
        return self.next_phase is not None

    def switch(self, phase: int, now: float) -> bool:
        """Start the transition to ``phase``; returns True if the phase changes."""
        if self.in_yellow or phase == self.phase:
            return False
        old = self.green_states[self.phase]
        for index in self.phase_links[self.phase]:
            self.link_last_green[index] = now
        self.next_phase = phase
        self.yellow_left = self.yellow_time
        transition = yellow_state(old, self.green_states[phase], self.crossing_signals)
        self.conn.trafficlight.setRedYellowGreenState(self.id, transition)
        return True

    def tick(self, now: float, step: float) -> None:
        """Advance the yellow timer by one simulation step (called after each step)."""
        if self.next_phase is None:
            return
        self.yellow_left -= step
        if self.yellow_left <= 1e-9:
            self.phase = self.next_phase
            self.next_phase = None
            self.green_since = now
            self.conn.trafficlight.setRedYellowGreenState(self.id, self.green_states[self.phase])

    # ------------------------------------------------------------------ queries
    def green_elapsed(self, now: float) -> float:
        return 0.0 if self.in_yellow else now - self.green_since

    def link_red_time(self, now: float) -> dict[int, float]:
        green = set() if self.in_yellow else self.phase_links[self.phase]
        return {
            link.index: (0.0 if link.index in green else now - self.link_last_green[link.index])
            for link in self.links
        }


def _unique(items) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out
