"""End-to-end runs in quick mode: result files exist, columns are complete, values sane."""

import math

import pandas as pd
import pytest

from cotraffic.evaluation.runner import run_episode

pytestmark = pytest.mark.sumo

CORE = [
    "mean_travel_time",
    "mean_waiting_time",
    "mean_time_loss",
    "mean_queue",
    "throughput_per_h",
    "co2_g_per_km",
    "stops_per_vehicle",
    "p95_waiting_time",
    "gini_waiting_time",
    "person_weighted_delay",
    "unfinished",
    "teleports_total",
]


@pytest.mark.parametrize("method", ["ft", "act", "mp"])
def test_quick_run_writes_a_complete_row(method, tmp_path):
    row = run_episode(
        method, "grid2x2", "medium", [], seed=0, quick=True, raw_dir=tmp_path, logs_dir=tmp_path
    )
    df = pd.read_csv(tmp_path / f"{row['run_id']}.csv")
    assert len(df) == 1
    for col in CORE + ["method", "network", "scenario", "demand", "seed", "git_commit"]:
        assert col in df.columns, col
    for col in CORE:
        assert not math.isnan(float(df[col].iloc[0])), col
    assert df["mean_travel_time"].iloc[0] > 0
    assert df["throughput_per_h"].iloc[0] > 0
    assert df["mean_waiting_time"].iloc[0] <= df["mean_travel_time"].iloc[0]


def test_incident_and_emergency_scenarios_run(tmp_path):
    row = run_episode(
        "act",
        "grid2x2",
        "medium",
        ["incident", "emergency"],
        seed=2,
        quick=True,
        raw_dir=tmp_path,
        logs_dir=tmp_path,
    )
    assert row["ev_count"] >= 3
    assert row["incident_start"] != ""


def test_pedestrian_rule_serves_waiting_pedestrians(tmp_path):
    from cotraffic.controllers.registry import make_controller

    ctrl = make_controller("ped_rule_mp")
    row = run_episode(
        "ped_rule_mp",
        "grid2x2",
        "peak",
        ["pedestrians"],
        seed=3,
        quick=True,
        raw_dir=tmp_path,
        logs_dir=tmp_path,
        controller=ctrl,
    )
    assert ctrl.requests > 0
    assert row["collisions"] == 0


@pytest.mark.parametrize("method", ["ev_rule", "ev_rule_mp"])
def test_ev_rule_preempts_and_stays_safe(method, tmp_path):
    from cotraffic.controllers.registry import make_controller

    ctrl = make_controller(method)
    row = run_episode(
        method,
        "grid2x2",
        "peak",
        ["emergency"],
        seed=3,
        quick=True,
        raw_dir=tmp_path,
        logs_dir=tmp_path,
        controller=ctrl,
    )
    assert ctrl.preemptions > 0
    assert row["ev_count"] >= 3 and row["collisions"] == 0
