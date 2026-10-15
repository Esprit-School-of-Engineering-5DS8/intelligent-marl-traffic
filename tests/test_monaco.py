"""
tests/test_monaco.py
Regression tests for the MoST Monaco scenario (Phase 6, deliverable B).

Pure XML over the committed network: no SUMO process needed. The MoST network
has 12 signalized junctions, all with actuated programs: 8 of them have two
distinct vehicle-green lane sets, 4 have three (protected-turn / one-way
phases). The topology layer must build all of them, cluster the sets into the
NS/EW axes without leaving an axis empty, and translate any controlled link
back to the exact group (so EV pre-emption and pedestrian sensing work).

The headless live-run smoke check (static program conversion, phase pinning)
is part of the documented validation chain in docs/test/phase6/monaco.md.
"""

import os
import xml.etree.ElementTree as ET

import pytest

from environment.topology import build_topology

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NET_PATH = os.path.join(REPO_ROOT, "scenarios", "monaco", "in", "most.net.xml")
SUMO_CFG = os.path.join(REPO_ROOT, "scenarios", "monaco", "monaco.llm.sumocfg")

THREE_SET_TLS = {"134872", "142742", "144421", "cluster_135794_135910"}
EXPECTED_TLS_COUNT = 12


def _net_data(net_path=NET_PATH):
    root = ET.parse(net_path).getroot()
    coords = {
        junction.get("id"): (float(junction.get("x")), float(junction.get("y")))
        for junction in root.findall("junction")
        if junction.get("type") != "internal"
    }
    edges = {edge.get("id"): edge for edge in root.findall("edge")
             if edge.get("function") != "internal"}
    connections = {}
    for connection in root.findall("connection"):
        tls_id = connection.get("tl")
        if tls_id is None:
            continue
        connections.setdefault(tls_id, []).append(connection)
    return root, coords, edges, connections


def _lane_headings(coords, edges, tls_connections):
    headings = {}
    for connection in tls_connections:
        from_edge, from_lane = connection.get("from"), connection.get("fromLane")
        if from_edge is None or from_edge.startswith(":"):
            continue
        edge = edges.get(from_edge)
        if edge is None:
            continue
        try:
            x1, y1 = coords[edge.get("from")]
            x2, y2 = coords[edge.get("to")]
        except KeyError:
            continue
        headings[f"{from_edge}_{from_lane}"] = (x2 - x1, y2 - y1)
    return headings


def _topology_from_net(root, coords, edges, tls_id):
    tl_logic = root.find(f"./tlLogic[@id='{tls_id}']")
    phases = [(float(p.get("duration")), p.get("state")) for p in tl_logic.findall("phase")]
    connections = sorted(
        (c for c in root.findall("connection") if c.get("tl") == tls_id),
        key=lambda c: int(c.get("linkIndex")),
    )
    links = [[(f"{c.get('from')}_{c.get('fromLane')}", "", "")] for c in connections]
    headings = _lane_headings(coords, edges, connections)
    return build_topology(tls_id, phases, links, headings), connections


@pytest.fixture(scope="module")
def monaco():
    root, coords, edges, connections = _net_data()
    return root, coords, edges, connections


def _tls_ids(root):
    return sorted(tl.get("id") for tl in root.findall("tlLogic"))


def test_all_monaco_tls_build(monaco):
    root, coords, edges, _ = monaco
    tls_ids = _tls_ids(root)
    assert len(tls_ids) == EXPECTED_TLS_COUNT
    for tls_id in tls_ids:
        topology, connections = _topology_from_net(root, coords, edges, tls_id)
        lane_links = {}
        for index, connection in enumerate(connections):
            lane_links.setdefault(
                f"{connection.get('from')}_{connection.get('fromLane')}", []).append(index)
        assert 2 <= len(topology.groups) <= 3, tls_id
        assert set(topology.axis_by_action) == {"NS", "EW"}, tls_id
        assert topology.controlled_lanes == frozenset().union(*(g.lanes for g in topology.groups))
        assert not (topology.ns_lanes & topology.ew_lanes)
        for group in topology.groups:
            assert group.canonical_phase in group.phases
            for phase_index in group.phases:
                state = topology.phases[phase_index].state
                for lane in group.lanes:
                    links = lane_links[lane]
                    assert all(state[index] in "Gg" for index in links), \
                        (tls_id, phase_index, lane)


def test_expected_set_counts(monaco):
    root, coords, edges, _ = monaco
    for tls_id in _tls_ids(root):
        topology, _ = _topology_from_net(root, coords, edges, tls_id)
        expected = 3 if tls_id in THREE_SET_TLS else 2
        assert len(topology.groups) == expected, tls_id


def test_axis_labels_follow_lane_geometry(monaco):
    """
    Geometry (lane headings) labels the axes of N-phase programs; two-set
    programs keep the historical phase-order labels (NS = first set) so grid
    and pedestrian runs stay byte-identical.
    """
    root, coords, edges, _ = monaco

    # 3-set junctions: each set is clustered by its lanes' heading class.
    topology, _ = _topology_from_net(root, coords, edges, "142742")
    # sets: N-heading -> NS, W-heading -> EW, S-heading -> NS
    assert topology.axis_by_action == ("NS", "EW", "NS")

    topology, _ = _topology_from_net(root, coords, edges, "cluster_135794_135910")
    # sets: {N,S} -> NS, E -> EW, W -> EW
    assert topology.axis_by_action == ("NS", "EW", "EW")

    topology, _ = _topology_from_net(root, coords, edges, "144421")
    # sets: S -> NS, W -> EW, E -> EW
    assert topology.axis_by_action == ("NS", "EW", "EW")

    # 134872's three sets all head east/west; the latest smallest set is moved
    # to the empty NS axis so both controller actions exist.
    topology, _ = _topology_from_net(root, coords, edges, "134872")
    assert topology.axis_by_action == ("EW", "EW", "NS")

    # Two-set junctions: first set = NS, second = EW (legacy convention,
    # independent of the compass).
    topology, _ = _topology_from_net(root, coords, edges, "137525")
    assert topology.axis_by_action == ("NS", "EW")


def test_action_for_link_covers_every_group(monaco):
    root, coords, edges, _ = monaco
    for tls_id in _tls_ids(root):
        topology, connections = _topology_from_net(root, coords, edges, tls_id)
        for action, group in enumerate(topology.groups):
            canonical = topology.phases[group.canonical_phase].state
            served = [
                index for index, connection in enumerate(connections)
                if canonical[index] in "Gg"
                and f"{connection.get('from')}_{connection.get('fromLane')}" in group.lanes
            ]
            assert served, (tls_id, action)
            resolved = {topology.action_for_link(index) for index in served}
            assert action in resolved, (tls_id, action, resolved)
            assert topology.axis_for_link(served[0]) == group.axis


def test_monaco_llm_config_is_self_contained():
    root = ET.parse(SUMO_CFG).getroot()
    scenario_dir = os.path.dirname(SUMO_CFG)
    for entry in root.findall(".//net-file") + root.findall(".//route-files") \
            + root.findall(".//additional-files"):
        for item in entry.get("value").split(","):
            path = os.path.join(scenario_dir, item.strip())
            assert os.path.isfile(path), path
    begin = float(root.find(".//begin").get("value"))
    end = float(root.find(".//end").get("value"))
    assert begin == 25200.0 and end > begin
