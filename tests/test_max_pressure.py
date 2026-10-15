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


THREE_GROUP_STATE = {
    "lane_queues": {"n_in_0": 1, "e_in_0": 2, "s_in_0": 9},
    "group_lanes": [frozenset({"n_in_0"}), frozenset({"e_in_0"}), frozenset({"s_in_0"})],
    "axis_by_action": ("NS", "EW", "NS"),
}


def test_three_group_picks_the_busiest_group():
    assert MaxPressureAgent("T0").select_action(THREE_GROUP_STATE) == 2
    state = dict(THREE_GROUP_STATE, lane_queues={"n_in_0": 0, "e_in_0": 7, "s_in_0": 3})
    assert MaxPressureAgent("T0").select_action(state) == 1


def test_three_group_ties_prefer_the_lowest_action():
    state = dict(THREE_GROUP_STATE, lane_queues={"n_in_0": 4, "e_in_0": 4, "s_in_0": 4})
    assert MaxPressureAgent("T0").select_action(state) == 0
