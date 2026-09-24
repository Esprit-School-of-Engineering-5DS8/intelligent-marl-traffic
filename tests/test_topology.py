import pytest

from cotraffic.networks.build import ensure_network
from cotraffic.networks.topology import angle_to_side, fringe_edges, load_net, tls_geometry

pytestmark = pytest.mark.sumo


@pytest.mark.parametrize(
    "angle,side",
    [(0, "east"), (44, "east"), (46, "north"), (180, "west"), (-90, "south"), (315, "east")],
)
def test_angle_to_side(angle, side):
    assert angle_to_side(angle) == side


def test_grid_fringe_edges():
    net = load_net(str(ensure_network("grid2x2")))
    entries, exits = fringe_edges(net)
    assert len(entries) == len(exits) == 8
    by_side = {
        s: [e.edge_id for e in entries if e.side == s] for s in ("north", "east", "south", "west")
    }
    assert by_side["west"] == ["left0A0", "left1A1"]  # ordered south to north
    assert by_side["north"] == ["top0A1", "top1B1"]  # ordered west to east
    assert all(e.lanes == 2 for e in entries)


def test_grid_neighbours_and_approach_sides():
    geo = tls_geometry(ensure_network("grid2x2"))
    a0 = geo["A0"]
    assert a0.edge_side["left0A0"] == "west"
    assert a0.edge_side["A1A0"] == "north"
    assert {s: n.tls_id for s, n in a0.neighbours.items()} == {"north": "A1", "east": "B0"}
    assert a0.neighbours["north"].path_edges == ("A1A0",)
    assert set(a0.crossing_side.values()) == {"north", "east", "south", "west"}


def test_grid4x4_inner_junction_has_four_neighbours():
    geo = tls_geometry(ensure_network("grid4x4"))
    assert len(geo) == 16
    assert {s: n.tls_id for s, n in geo["B1"].neighbours.items()} == {
        "north": "B2",
        "east": "C1",
        "south": "B0",
        "west": "A1",
    }
