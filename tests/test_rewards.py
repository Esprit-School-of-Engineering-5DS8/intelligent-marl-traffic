import pytest

from cotraffic.envs.rewards import RewardComputer, RewardConfig, vehicle_kind

NORM = {"wait": 10.0, "queue": 5.0, "pressure": 4.0, "co2": 100.0, "ev": 2.0, "ped": 3.0}
OCC = {"passenger": 1.2, "bus": 30.0, "emergency": 2.0}
RAW = {"wait": -20.0, "queue": 10.0, "pressure": 8.0, "co2": 200.0, "ev": 4.0, "ped": 6.0}


def combine(**cfg):
    return RewardComputer(RewardConfig(**cfg), OCC, NORM).combine(RAW)


def test_base_terms():
    assert combine() == pytest.approx(-2.0)  # waiting grew by 20 s -> negative
    assert combine(base="queue") == pytest.approx(-2.0)  # 10 halting / 5
    assert combine(base="pressure") == pytest.approx(-2.0)  # |8| / 4


def test_penalties_add_to_the_base_term():
    r = combine(co2=0.25, ev=0.5, ped=0.25)
    assert r == pytest.approx(-2.0 - 0.25 * 2.0 - 0.5 * 2.0 - 0.25 * 2.0)


def test_reward_is_clipped():
    assert combine(ev=100.0) == pytest.approx(-5.0)


def test_unknown_base_is_rejected():
    with pytest.raises(ValueError):
        RewardConfig.from_dict({"base": "speed"})


def test_vehicle_kinds_follow_the_id_prefixes():
    assert vehicle_kind("bus_L1_a.3") == "bus"
    assert vehicle_kind("ev_2") == "emergency"
    assert vehicle_kind("incident_0") == "incident"
    assert vehicle_kind("car_17") == "passenger"
