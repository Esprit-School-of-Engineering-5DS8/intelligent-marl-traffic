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
    from cotraffic.controllers.registry import LEARNED
    from cotraffic.seeds import TEST_SEEDS, VALIDATION_SEEDS, check_seeds

    for name in config.available("agents"):
        cfg = config.load_agent(name)
        # every learned agent selects on validation seeds; llm_team (the teammate's LLM team,
        # controllers/llm_team/PROVENANCE.md) is not trained and declares no seed
        if name in LEARNED or "validation" in cfg:
            check_seeds(cfg["validation"]["seeds"], VALIDATION_SEEDS, name)
    for name in config.available("experiments"):
        check_seeds(config.load("experiments", name)["seeds"], TEST_SEEDS, name)


def test_district_variant_keeps_the_district_layout():
    # the demonstration variant with sidewalks is driven by the agents trained on
    # real_district, so the observation and action layouts must be the same
    base = Padding.from_dict(config.load("networks", "real_district")["padding"])
    variant = Padding.from_dict(config.load("networks", "real_district_ped")["padding"])
    assert variant.extra_crossings_unobserved and not base.extra_crossings_unobserved
    assert (variant.lanes_per_side, variant.max_phases, variant.max_crossings) == (
        base.lanes_per_side,
        base.max_phases,
        base.max_crossings,
    )


def test_extra_crossings_are_refused_unless_accepted():
    from types import SimpleNamespace

    from cotraffic.envs.observations import ObservationBuilder

    protocol = config.load_protocol()
    cfg = ObservationConfig.from_dict({"pedestrians": True})
    inter = SimpleNamespace(id="J", n_phases=2, crossings=["c0", "c1", "c2", "c3", "c4"])
    for accept in (False, True):
        pad = Padding(3, 3, 4, extra_crossings_unobserved=accept)
        builder = ObservationBuilder(cfg, pad, protocol["timing"], protocol["observation"])
        if accept:
            builder.check(inter)
        else:
            with pytest.raises(ValueError, match="5 crossings"):
                builder.check(inter)
