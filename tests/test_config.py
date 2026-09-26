import pytest

from cotraffic import config
from cotraffic.envs.observations import ObservationConfig, Padding
from cotraffic.envs.rewards import RewardConfig


@pytest.mark.parametrize("kind", ["networks", "demand", "scenarios"])
def test_every_config_parses(kind):
    names = config.available(kind)
    assert names
    for name in names:
        cfg = config.load(kind, name)
        assert cfg["name"] == name


def test_network_configs_are_complete():
    for name in config.available("networks"):
        cfg = config.load("networks", name)
        Padding.from_dict(cfg["padding"])
        assert cfg["demand"]["peak_vehicles_per_hour"] > 0
        assert cfg["neighbours"]["max_distance_m"] > 0


def test_grid_policies_transfer_between_grids():
    # zero-shot evaluation on grid8x8 requires identical observation/action layouts
    assert (
        config.load("networks", "grid8x8")["padding"]
        == config.load("networks", "grid4x4")["padding"]
    )


def test_protocol_timing_is_consistent():
    t = config.load_protocol()["timing"]
    assert t["yellow_time"] < t["delta_time"] <= t["min_green"] < t["max_green"] < t["max_red"]


def test_deep_merge_does_not_mutate_inputs():
    a = {"x": {"y": 1, "z": 2}}
    b = {"x": {"y": 3}, "w": 4}
    out = config.deep_merge(a, b)
    assert out == {"x": {"y": 3, "z": 2}, "w": 4}
    assert a == {"x": {"y": 1, "z": 2}}


def test_unknown_options_are_rejected():
    with pytest.raises(ValueError):
        ObservationConfig.from_dict({"neighbors": True})
    with pytest.raises(ValueError):
        RewardConfig.from_dict({"co2_weight": 1.0})


def test_missing_config_fails_loudly():
    with pytest.raises(FileNotFoundError):
        config.load("networks", "does_not_exist")


def test_seed_ranges_are_enforced():
    from cotraffic.evaluation.matrix import expand
    from cotraffic.seeds import TEST_SEEDS, VALIDATION_SEEDS, check_seeds

    assert not set(TEST_SEEDS) & set(VALIDATION_SEEDS)
    check_seeds([0, 4, 999], TEST_SEEDS, "evaluation")
    with pytest.raises(ValueError, match="validation seeds"):
        check_seeds([1000, 3], VALIDATION_SEEDS, "validation")
    with pytest.raises(ValueError, match="evaluation seeds"):
        expand({"seeds": [0, 1000], "cells": []})


def test_every_config_uses_its_own_seed_range():
    from cotraffic.seeds import TEST_SEEDS, VALIDATION_SEEDS, check_seeds

    for name in config.available("agents"):
        check_seeds(config.load_agent(name)["validation"]["seeds"], VALIDATION_SEEDS, name)
    for name in config.available("experiments"):
        check_seeds(config.load("experiments", name)["seeds"], TEST_SEEDS, name)
