import pytest

from agents.max_pressure import MaxPressureAgent

STATE = {
    "lane_queues": {"n_in_0": 5, "n_in_1": 2, "e_in_0": 1, "e_in_1": 0},
    "ns_lanes": frozenset({"n_in_0", "n_in_1"}),
    "ew_lanes": frozenset({"e_in_0", "e_in_1"}),
}


def test_chooses_ns_when_ns_queue_larger():
    assert MaxPressureAgent("T0").select_action(STATE) == 0


def test_chooses_ew_when_ew_queue_larger():
    state = dict(STATE, lane_queues={"n_in_0": 1, "e_in_0": 7})
    assert MaxPressureAgent("T0").select_action(state) == 1


def test_tie_goes_to_ns():
    state = dict(STATE, lane_queues={"n_in_0": 3, "e_in_0": 3})
    assert MaxPressureAgent("T0").select_action(state) == 0


def test_requires_topology_groups():
    with pytest.raises(KeyError):
        MaxPressureAgent("T0").select_action({"lane_queues": {}})
