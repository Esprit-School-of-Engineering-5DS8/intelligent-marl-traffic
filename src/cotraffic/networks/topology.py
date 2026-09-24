"""Static analysis of a SUMO network.

Gives the demand generator its entry/exit edges and gives the agents their
neighbourhood: for every signalised intersection, which other signalised
intersection feeds each of its approaches, and through which edges.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from cotraffic.utils.sumo import find_sumo_home

SIDES = ("north", "east", "south", "west")
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}


def angle_to_side(angle_deg: float) -> str:
    """Map a bearing (0 = east, counter-clockwise) to one of four sides."""
    a = angle_deg % 360.0
    if a < 45.0 or a >= 315.0:
        return "east"
    if a < 135.0:
        return "north"
    if a < 225.0:
        return "west"
    return "south"


def bearing(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


@lru_cache(maxsize=8)
def load_net(net_file: str):
    """Read a network with sumolib (cached, the object is treated as read-only)."""
    find_sumo_home()
    import sumolib

    return sumolib.net.readNet(str(net_file), withInternal=True, withPedestrianConnections=True)


def _is_turnaround(a, b) -> bool:
    return a.getFromNode() == b.getToNode() and a.getToNode() == b.getFromNode()


def is_road(edge, vclass: str = "passenger") -> bool:
    return edge.getFunction() == "" and edge.allows(vclass)


@dataclass(frozen=True)
class FringeEdge:
    edge_id: str
    side: str
    lanes: int
    x: float
    y: float


def network_center(net) -> tuple[float, float]:
    (xmin, ymin), (xmax, ymax) = net.getBBoxXY()
    return (xmin + xmax) / 2.0, (ymin + ymax) / 2.0


def fringe_edges(net, vclass: str = "passenger") -> tuple[list[FringeEdge], list[FringeEdge]]:
    """Edges where vehicles can enter (no upstream road) and leave (no downstream road).

    Sides are assigned from the bearing of the fringe node seen from the network centre.
    Results are sorted by side then by position along the side, so indices are stable.
    """
    cx, cy = network_center(net)
    entries: list[FringeEdge] = []
    exits: list[FringeEdge] = []
    for edge in net.getEdges(withInternal=False):
        if not is_road(edge, vclass):
            continue
        upstream = [
            e for e in edge.getIncoming() if is_road(e, vclass) and not _is_turnaround(e, edge)
        ]
        downstream = [
            e for e in edge.getOutgoing() if is_road(e, vclass) and not _is_turnaround(edge, e)
        ]
        lanes = sum(1 for lane in edge.getLanes() if lane.allows(vclass))
        if not upstream:
            x, y = edge.getFromNode().getCoord()
            entries.append(
                FringeEdge(edge.getID(), angle_to_side(bearing(cx, cy, x, y)), lanes, x, y)
            )
        if not downstream:
            x, y = edge.getToNode().getCoord()
            exits.append(
                FringeEdge(edge.getID(), angle_to_side(bearing(cx, cy, x, y)), lanes, x, y)
            )

    def along_side(f: FringeEdge) -> tuple[int, float]:
        # west/east sides are ordered south to north, north/south sides west to east
        return SIDES.index(f.side), (f.y if f.side in ("west", "east") else f.x)

    return sorted(entries, key=along_side), sorted(exits, key=along_side)


def lane_approach_side(net, lane_id: str) -> str:
    """Side of the intersection a lane arrives from, using the last segment of its shape."""
    shape = net.getLane(lane_id).getShape()
    (x0, y0), (x1, y1) = shape[-2], shape[-1]
    return angle_to_side(bearing(x1, y1, x0, y0))


@dataclass(frozen=True)
class NeighbourLink:
    tls_id: str  # the upstream signalised intersection
    side: str  # side of *this* intersection where it sits
    path_edges: tuple[str, ...]  # driving order, from the neighbour to this intersection
    distance: float


@dataclass
class TLSGeometry:
    tls_id: str
    x: float
    y: float
    incoming_edges: list[str] = field(default_factory=list)
    edge_side: dict[str, str] = field(default_factory=dict)
    neighbours: dict[str, NeighbourLink] = field(default_factory=dict)
    crossing_side: dict[str, str] = field(default_factory=dict)


def walkable_component(net) -> list[str]:
    """Road edges of the largest connected pedestrian network.

    Pedestrians may walk a sidewalk in both directions, so connectivity is computed on
    the undirected graph of walkable edges, crossings and walking areas. Imported
    networks can have separate pieces; a walk between two of them cannot be routed.
    """
    walkable = [e for e in net.getEdges(withInternal=True) if e.allows("pedestrian")]
    adjacency: dict[str, set[str]] = {e.getID(): set() for e in walkable}
    for edge in walkable:
        for nxt in edge.getOutgoing():
            if nxt.getID() in adjacency:
                adjacency[edge.getID()].add(nxt.getID())
                adjacency[nxt.getID()].add(edge.getID())
    best: set[str] = set()
    seen: set[str] = set()
    for start in adjacency:
        if start in seen:
            continue
        component, stack = {start}, [start]
        seen.add(start)
        while stack:
            for nxt in adjacency[stack.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    component.add(nxt)
                    stack.append(nxt)
        if len(component) > len(best):
            best = component
    return sorted(e for e in best if not e.startswith(":"))


def pedestrian_edges(net) -> tuple[set[str], set[str]]:
    """Ids of all crossing and walking-area edges (internal pedestrian infrastructure)."""
    crossings, walkingareas = set(), set()
    for edge in net.getEdges(withInternal=True):
        if edge.getFunction() == "crossing":
            crossings.add(edge.getID())
        elif edge.getFunction() == "walkingarea":
            walkingareas.add(edge.getID())
    return crossings, walkingareas


def _node_to_tls(net) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for tls in net.getTrafficLights():
        for in_lane, _out_lane, _link in tls.getConnections():
            mapping[in_lane.getEdge().getToNode().getID()] = tls.getID()
    return mapping


def _upstream_neighbour(edge, own_tls: str, node_to_tls: dict[str, str], max_distance: float):
    """Nearest other signalised intersection upstream of ``edge`` (Dijkstra on reversed edges)."""
    counter = 0
    heap = [(edge.getLength(), counter, edge, (edge.getID(),))]
    seen: set[str] = set()
    while heap:
        dist, _, current, path = heapq.heappop(heap)
        if current.getID() in seen:
            continue
        seen.add(current.getID())
        node = current.getFromNode()
        owner = node_to_tls.get(node.getID())
        if owner is not None and owner != own_tls:
            return owner, path, dist
        if owner == own_tls and current is not edge:
            continue
        for prev in node.getIncoming():
            if not is_road(prev) or _is_turnaround(prev, current) or prev.getID() in seen:
                continue
            new_dist = dist + prev.getLength()
            if new_dist <= max_distance:
                counter += 1
                heapq.heappush(heap, (new_dist, counter, prev, (prev.getID(), *path)))
    return None


def tls_geometry(net_file: str | Path, max_distance: float = 500.0) -> dict[str, TLSGeometry]:
    """Position, approaches and upstream neighbours of every traffic light in the network."""
    net = load_net(str(net_file))
    node_to_tls = _node_to_tls(net)
    crossings, _walkingareas = pedestrian_edges(net)
    result: dict[str, TLSGeometry] = {}
    for tls in net.getTrafficLights():
        tls_id = tls.getID()
        in_edges: list = []
        for in_lane, _out, _link in tls.getConnections():
            edge = in_lane.getEdge()
            if edge.getFunction() == "" and edge not in in_edges:
                in_edges.append(edge)
        nodes = {e.getToNode() for e in in_edges}
        x = sum(n.getCoord()[0] for n in nodes) / max(len(nodes), 1)
        y = sum(n.getCoord()[1] for n in nodes) / max(len(nodes), 1)
        geo = TLSGeometry(tls_id, x, y)
        for crossing in sorted(crossings):
            if any(crossing.startswith(f":{n.getID()}_c") for n in nodes):
                shape = net.getLane(f"{crossing}_0").getShape()
                cx = sum(p[0] for p in shape) / len(shape)
                cy = sum(p[1] for p in shape) / len(shape)
                geo.crossing_side[crossing] = angle_to_side(bearing(x, y, cx, cy))
        candidates: list[NeighbourLink] = []
        for edge in in_edges:
            side = lane_approach_side(net, edge.getLanes()[-1].getID())
            geo.incoming_edges.append(edge.getID())
            geo.edge_side[edge.getID()] = side
            found = _upstream_neighbour(edge, tls_id, node_to_tls, max_distance)
            if found is not None:
                owner, path, dist = found
                candidates.append(NeighbourLink(owner, side, path, dist))
        # one neighbour per side: keep the closest, a second one on the same side is dropped
        for link in sorted(candidates, key=lambda c: c.distance):
            if link.side not in geo.neighbours and all(
                n.tls_id != link.tls_id for n in geo.neighbours.values()
            ):
                geo.neighbours[link.side] = link
        result[tls_id] = geo
    return result
