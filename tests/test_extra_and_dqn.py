"""Extra measurements (results/extra/) and the DQN algorithm option."""

from __future__ import annotations

import pytest

from cotraffic import config
from cotraffic.analysis.aggregate import assign_families
from cotraffic.training.train import algorithm_class


def test_algorithm_option():
    from stable_baselines3 import DQN, PPO

    assert algorithm_class("ppo") is PPO and algorithm_class("dqn") is DQN
    with pytest.raises(ValueError):
        algorithm_class("a2c")
    cfg = config.load_agent("dqn")
    assert (
        cfg["algorithm"] == "dqn" and cfg["observation"] == config.load_agent("ind")["observation"]
    )


def test_dqn_tests_form_their_own_family():
    import pandas as pd

    comp = pd.DataFrame(
        {
            "network": ["grid4x4"] * 3,
            "scenario": ["normal"] * 3,
            "demand": ["peak"] * 3,
            "method": ["ind", "coop_forecast", "dqn"],
            "comparison": ["learned_vs_best"] * 3,
            "p_value": [0.01, 0.02, 0.03],
        }
    )
    core = {("grid4x4", "normal", "peak", "ind")}
    dqn = {("grid4x4", "normal", "peak", "dqn")}
    out = assign_families(comp, core, {"dqn": dqn})
    assert list(out["family"]) == ["core", "exploratory", "dqn"]
    assert list(out["p_holm"]) == [0.01, 0.02, 0.03]  # one test per family: unchanged


def test_extra_run_adds_measurements_without_changing_the_simulation(tmp_path):
    from cotraffic.evaluation.runner import run_episode

    common = dict(seed=7, quick=True)
    plain = run_episode(
        "mp",
        "grid2x2",
        "medium",
        ["pedestrians", "emergency"],
        raw_dir=tmp_path / "raw",
        logs_dir=tmp_path / "logs",
        **common,
    )
    extra = run_episode(
        "mp",
        "grid2x2",
        "medium",
        ["pedestrians", "emergency"],
        raw_dir=tmp_path / "xraw",
        logs_dir=tmp_path / "xlogs",
        extra=True,
        **common,
    )
    for key in ("mean_travel_time", "mean_waiting_time", "ped_mean_waiting_time", "ev_delay"):
        assert extra[key] == pytest.approx(plain[key])
    for key in ("ped_p95_waiting_time", "ped_crossings_in_green_pct", "reward_delay", "reward_co2"):
        assert key in extra
    assert 0.0 <= extra["ped_crossings_in_green_pct"] <= 100.0
    assert extra["ped_p95_waiting_time"] >= extra["ped_mean_waiting_time"] * 0.5
    assert (tmp_path / "xlogs" / "emergency").is_dir() or extra.get("ev_count", 0) == 0
