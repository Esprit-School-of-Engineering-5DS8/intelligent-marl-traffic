import os
import xml.etree.ElementTree as ET

import pytest

from environment.topology import build_topology, neighbor_map_from_net, net_file_from_sumocfg

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRID_PHASES = [
    (42, "GGrr"),
    (3, "yyrr"),
    (42, "rrGG"),
    (3, "rryy"),
]


def _links(*lanes):
    return [[(lane, f"{lane}_to", f"{lane}_via")] for lane in lanes]


GRID_LINKS = _links("n_in_0", "n_in_1", "e_in_0", "e_in_1")


def test_groups_and_action_mapping():
    topology = build_topology("T0", GRID_PHASES, GRID_LINKS)
    assert topology.ns_lanes == frozenset({"n_in_0", "n_in_1"})
    assert topology.ew_lanes == frozenset({"e_in_0", "e_in_1"})
    assert topology.green_phase_for_action(0) == 0
    assert topology.green_phase_for_action(1) == 2
    assert topology.green_phase_for_action(2) == 0


def test_action_for_link_maps_approach_to_axis():
    topology = build_topology("T0", GRID_PHASES, GRID_LINKS)
    assert topology.action_for_link(0) == 0
    assert topology.action_for_link(1) == 0
    assert topology.action_for_link(2) == 1
    assert topology.action_for_link(3) == 1
    assert topology.action_for_link(99) is None


def test_phase_classification():
    topology = build_topology("T0", GRID_PHASES, GRID_LINKS)
    assert topology.phase(0).is_green
    assert topology.phase(1).is_yellow
    assert topology.phase(1).is_clearance is False
    assert topology.phase(2).is_green


def test_transition_path_goes_through_yellow():
    topology = build_topology("T0", GRID_PHASES, GRID_LINKS)
    assert topology.transition_path(0, 2) == (1, 2)
    assert topology.transition_path(2, 0) == (3, 0)


def test_transition_path_with_pedestrian_clearance():
    phases = [
        (30, "GGrr"),
        (5, "rrrr"),
        (3, "yyrr"),
        (30, "rrGG"),
        (5, "rrrr"),
        (3, "rryy"),
    ]
    topology = build_topology("T0", phases, GRID_LINKS)
    assert topology.green_phase_for_action(0) == 0
    assert topology.green_phase_for_action(1) == 3
    assert topology.transition_path(0, 3) == (1, 2, 3)
    assert topology.transition_path(3, 0) == (4, 5, 0)
    assert topology.phase(1).is_clearance


def test_rejects_unexpected_green_count():
    with pytest.raises(ValueError):
        build_topology("T0", [(42, "GGrr"), (3, "yyrr")], GRID_LINKS)


# Pedestrian program: 4 vehicle links + 4 crossing links from walkingareas.
# Phases come in pairs sharing vehicle greens: the 5 s "end-of-green" phase
# keeps vehicles green while the crossing signals turn red before the yellow.
PED_PHASES = [
    (37, "GGrrrGrG"),
    (5,  "GGrrrrrr"),
    (3,  "yyrrrrrr"),
    (37, "rrGGGrGr"),
    (5,  "rrGGrrrr"),
    (3,  "rryyrrrr"),
]
PED_LINKS = [
    [("n_in_0", "out", "via")],
    [("n_in_1", "out", "via")],
    [("e_in_0", "out", "via")],
    [("e_in_1", "out", "via")],
    [(":T0_w0_0", ":T0_c0_0", "")],
    [(":T0_w1_0", ":T0_c1_0", "")],
    [(":T0_w2_0", ":T0_c2_0", "")],
    [(":T0_w3_0", ":T0_c3_0", "")],
]


def test_pedestrian_program_groups_green_phases_by_vehicle_lanes():
    topology = build_topology("T0", PED_PHASES, PED_LINKS)
    assert topology.ns_lanes == frozenset({"n_in_0", "n_in_1"})
    assert topology.ew_lanes == frozenset({"e_in_0", "e_in_1"})
    assert topology.green_phase_for_action(0) == 0
    assert topology.green_phase_for_action(1) == 3

    # Twin phases keep the axis's vehicle green (with ped signals red).
    assert topology.is_green_phase(1) and topology.axis_for_phase(1) == "NS"
    assert topology.is_green_phase(4) and topology.axis_for_phase(4) == "EW"
    assert not topology.is_hold_phase(1) and not topology.is_hold_phase(4)
    assert topology.is_hold_phase(0) and topology.is_hold_phase(3)
    assert topology.axis_for_phase(2) is None

    # Transition keeps both the ped-red grace (1/4) and the yellow (2/5).
    assert topology.transition_path(0, 3) == (1, 2, 3)
    assert topology.transition_path(3, 0) == (4, 5, 0)


def test_pedestrian_topology_excludes_internal_lanes():
    topology = build_topology("T0", PED_PHASES, PED_LINKS)
    assert topology.controlled_lanes == frozenset({"n_in_0", "n_in_1", "e_in_0", "e_in_1"})
    # Crossing links resolve to the axis whose green serves their pedestrians:
    # c0 (link 4) walks with EW, c1 (link 5) walks with NS.
    assert topology.action_for_link(4) == 1
    assert topology.action_for_link(5) == 0


NET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<net>
    <junction id="A0" x="0" y="0"/>
    <junction id="A1" x="0" y="100"/>
    <junction id="B0" x="100" y="0"/>
    <junction id="C0" x="0" y="-100"/>
    <junction id="X" x="200" y="0"/>
    <edge id="A1A0" from="A1" to="A0"/>
    <edge id="B0A0" from="B0" to="A0"/>
    <edge id="C0A0" from="C0" to="A0"/>
    <edge id="XA0" from="X" to="A0"/>
    <edge id=":A0_0" function="internal" from="A0" to="A1"/>
</net>
"""


def test_neighbor_map_directions(tmp_path):
    net_file = tmp_path / "net.xml"
    net_file.write_text(NET_XML)
    neighbors = neighbor_map_from_net(str(net_file), ["A0", "A1", "B0", "C0"])
    assert neighbors["A0"] == {"N": "A1", "E": "B0", "S": "C0"}


def test_neighbor_map_order_is_deterministic(tmp_path):
    # Edges in a different document order: insertion order must be stable
    # (sorted by junction id) because this map ends up in LLM prompts.
    shuffled = NET_XML.replace(
        '<edge id="A1A0" from="A1" to="A0"/>\n    <edge id="B0A0" from="B0" to="A0"/>',
        '<edge id="B0A0" from="B0" to="A0"/>\n    <edge id="A1A0" from="A1" to="A0"/>')
    net_file = tmp_path / "shuffled.net.xml"
    net_file.write_text(shuffled)
    neighbors = neighbor_map_from_net(str(net_file), ["A0", "A1", "B0", "C0"])
    assert list(neighbors["A0"].keys()) == ["N", "E", "S"]


def test_net_file_from_sumocfg(tmp_path):
    cfg = tmp_path / "scenario.sumocfg"
    cfg.write_text(
        '<configuration><input><net-file value="grid.net.xml"/></input></configuration>'
    )
    assert net_file_from_sumocfg(str(cfg)) == str(tmp_path / "grid.net.xml")


def _topology_from_net(net_path, tls_id):
    root = ET.parse(net_path).getroot()
    tl_logic = root.find(f"./tlLogic[@id='{tls_id}']")
    phases = [(float(p.get("duration")), p.get("state")) for p in tl_logic.findall("phase")]
    connections = sorted(
        (c for c in root.findall("connection") if c.get("tl") == tls_id),
        key=lambda c: int(c.get("linkIndex")),
    )
    links = [[(f"{c.get('from')}_{c.get('fromLane')}", "", "")] for c in connections]
    return build_topology(tls_id, phases, links)


def test_real_grid3x3_topology_regression():
    net_path = os.path.join(REPO_ROOT, "scenarios", "grid_3x3", "grid3x3.net.xml")
    topology = _topology_from_net(net_path, "A0")
    assert topology.ns_lanes == frozenset({
        "A1A0_0", "A1A0_1", "bottom0A0_0", "bottom0A0_1",
    })
    assert topology.ew_lanes == frozenset({
        "B0A0_0", "B0A0_1", "left0A0_0", "left0A0_1",
    })
    assert len(topology.controlled_lanes) == 8


# N-phase programs (real networks): three distinct vehicle-green lane sets.
# Geometry vote: n_in_* head north, e_in_* east, s_in_0 south, w_in_0 west.
THREE_SET_PHASES = [
    (30, "GGrrrr"), (3, "yyrrrr"),
    (30, "rrGGrr"), (3, "rryyrr"),
    (30, "rrrrGG"), (3, "rrrryy"),
]
THREE_SET_LINKS = _links("n_in_0", "n_in_1", "e_in_0", "e_in_1", "s_in_0", "w_in_0")
THREE_SET_HEADINGS = {
    "n_in_0": (0.0, 1.0), "n_in_1": (0.0, 1.0),
    "e_in_0": (1.0, 0.0), "e_in_1": (1.0, 0.0),
    "s_in_0": (0.0, -1.0), "w_in_0": (-1.0, 0.0),
}


def test_three_set_program_groups_and_axes():
    topology = build_topology("T3", THREE_SET_PHASES, THREE_SET_LINKS, THREE_SET_HEADINGS)
    assert len(topology.groups) == 3
    assert topology.group_lanes == (
        frozenset({"n_in_0", "n_in_1"}),
        frozenset({"e_in_0", "e_in_1"}),
        frozenset({"s_in_0", "w_in_0"}),
    )
    # Mixed set (south + west) is a 1-1 vote tie -> NS; both axes stay filled.
    assert topology.axis_by_action == ("NS", "EW", "NS")
    assert topology.group_phase_for_action(0) == 0
    assert topology.group_phase_for_action(1) == 2
    assert topology.group_phase_for_action(2) == 4
    assert topology.is_hold_phase(4) and not topology.is_hold_phase(5)
    assert topology.is_green_phase(4) and topology.axis_for_phase(4) == "NS"
    assert topology.axis_for_phase(5) is None  # yellow
    assert topology.action_for_link(4) == 2 and topology.axis_for_link(4) == "NS"
    assert topology.action_for_link(2) == 1 and topology.axis_for_link(2) == "EW"
    assert topology.transition_path(0, 4) == (1, 2, 3, 4)
    # Axis lane partitions cover every controlled lane exactly once.
    assert topology.ns_lanes == frozenset({"n_in_0", "n_in_1", "s_in_0", "w_in_0"})
    assert topology.ew_lanes == frozenset({"e_in_0", "e_in_1"})


def test_three_set_program_without_headings_falls_back_to_phase_order():
    topology = build_topology("T3", THREE_SET_PHASES, THREE_SET_LINKS)
    assert topology.axis_by_action == ("NS", "EW", "EW")
    assert topology.ns_green_phase == 0 and topology.ew_green_phase == 2


def test_all_same_axis_moves_smallest_set_to_the_empty_axis():
    # Every set heads east: the NS axis would be empty, so the latest
    # smallest set (fewest lanes; tie -> latest program order) is moved.
    headings = {lane: (1.0, 0.0) for lane in THREE_SET_HEADINGS}
    topology = build_topology("T3", THREE_SET_PHASES, THREE_SET_LINKS, headings)
    assert topology.axis_by_action == ("EW", "EW", "NS")
    assert topology.axis_by_action.count("NS") == 1
    assert topology.axis_by_action.count("EW") == 2


def test_two_set_programs_ignore_geometry():
    # Grid nets keep the historical labels even if a lane heading is odd.
    headings = {lane: (1.0, 0.0) for lane in ("n_in_0", "n_in_1", "e_in_0", "e_in_1")}
    topology = build_topology("T0", GRID_PHASES, GRID_LINKS, headings)
    assert topology.axis_by_action == ("NS", "EW")
