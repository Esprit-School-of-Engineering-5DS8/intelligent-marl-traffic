from environment.pedestrians import (
    PedestrianState,
    PedestrianWaiting,
    aggregate_waiting,
    crossing_tls,
    is_crossing_edge,
)

CROSSING_AXIS = {
    ":A1_c1": ("A1", "NS"),
    ":A1_c2": ("A1", "EW"),
    ":B1_c1": ("B1", "NS"),
}


def test_crossing_edge_detection():
    assert is_crossing_edge(":A1_c2")
    assert not is_crossing_edge(":A1_w2")      # walkingarea
    assert not is_crossing_edge("A1B1")        # normal edge
    assert not is_crossing_edge(":A1_0")       # internal turn
    assert not is_crossing_edge("")


def test_crossing_tls_extraction():
    assert crossing_tls(":A1_c2") == "A1"
    assert crossing_tls(":B1_c0") == "B1"
    assert crossing_tls("A1B1") is None


def test_aggregate_groups_by_tls_axis_and_crossing():
    records = [
        PedestrianWaiting("p0", ":A1_c1", 12.0),
        PedestrianWaiting("p1", ":A1_c1", 24.0),
        PedestrianWaiting("p2", ":A1_c2", 5.0),
        PedestrianWaiting("p3", ":Z9_c0", 99.0),   # unknown crossing: ignored
    ]
    states = aggregate_waiting(records, CROSSING_AXIS)
    assert len(states) == 2
    # Sorted by (tls, axis, crossing): EW before NS.
    ew = states[0]
    assert (ew.tls_id, ew.axis, ew.crossing_id) == ("A1", "EW", ":A1_c2")
    assert (ew.waiting, ew.max_wait_s) == (1, 5.0)
    ns = states[1]
    assert (ns.tls_id, ns.axis, ns.crossing_id) == ("A1", "NS", ":A1_c1")
    assert ns.waiting == 2 and ns.max_wait_s == 24.0 and ns.mean_wait_s == 18.0


def test_aggregate_empty():
    assert aggregate_waiting([], CROSSING_AXIS) == []


def test_state_round_trips_snapshot_fields():
    state = PedestrianState("A1", "NS", ":A1_c1", 3, 21.5, 11.25)
    assert state.tls_id == "A1" and state.max_wait_s == 21.5
