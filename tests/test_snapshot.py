from agents.supervisor.blackboard import BlackboardMessage
from environment.ev import EVState, UpcomingTLS
from environment.snapshot import build_snapshot

STATES = {
    "B1": {
        "current_axis": "NS",
        "time_in_phase": 18,
        "ns_lanes": {"B1_0", "B1_1"},
        "ew_lanes": {"B1_2"},
        "lane_queues": {"B1_0": 4, "B1_1": 3, "B1_2": 2},
        "lane_waiting": {"B1_0": 40.0, "B1_1": 21.0, "B1_2": 9.0},
    },
    "B0": {"current_axis": None, "time_in_phase": 1,
           "lane_queues": {}, "lane_waiting": {}},
}


def test_snapshot_shape_and_aggregates():
    snapshot = build_snapshot(
        t=420,
        states=STATES,
        neighbors={"B1": {"N": "B2", "W": "A1"}},
        evs=[EVState("ev0", "left1A1", "left1A1_0", 13.9,
                     (UpcomingTLS("A1", 2, 62.0, "r"),))],
        alerts=[{"kind": "spillback", "edge": "B2B1"}],
        blackboard=[BlackboardMessage("ev_corridor", "emergency", 400.0, 60.0,
                                      {"tls": ["A1"]})],
    )
    b1 = snapshot["intersections"]["B1"]
    assert b1["phase"] == "NS"
    assert b1["queue"] == {"ns": 7, "ew": 2}
    assert b1["wait_s"] == {"ns": 61.0, "ew": 9.0}
    assert b1["neighbors"] == {"N": "B2", "W": "A1"}
    assert snapshot["intersections"]["B0"]["phase"] == "transition"

    ev = snapshot["evs"][0]
    assert ev["speed"] == 13.9
    assert ev["next_tls"][0]["tls"] == "A1"
    assert ev["next_tls"][0]["dist_m"] == 62.0
    assert ev["next_tls"][0]["eta_s"] == round(62.0 / 13.9, 1)
    assert ev["next_tls"][0]["signal"] == "r"

    assert snapshot["alerts"] == [{"kind": "spillback", "edge": "B2B1"}]
    assert snapshot["blackboard"][0]["type"] == "ev_corridor"
    assert snapshot["t"] == 420.0


def test_eta_floors_speed():
    ev = EVState("ev0", "left1A1", "left1A1_0", 0.0, (UpcomingTLS("A1", 0, 30.0, "r"),))
    snapshot = build_snapshot(0, STATES, evs=[ev])
    assert snapshot["evs"][0]["next_tls"][0]["eta_s"] == 30.0
