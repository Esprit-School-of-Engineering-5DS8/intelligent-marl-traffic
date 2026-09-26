import numpy as np
import pandas as pd
import pytest

from cotraffic.analysis.aggregate import assign_families, compare, summarise
from cotraffic.evaluation.matrix import expand


def fake_results():
    rng = np.random.default_rng(0)
    rows = []
    for method, centre in (("ft", 200.0), ("act", 180.0), ("mp", 150.0), ("coop", 140.0)):
        for seed in range(5):
            rows.append(
                {
                    "network": "g",
                    "scenario": "normal",
                    "demand": "peak",
                    "method": method,
                    "seed": seed,
                    "mean_travel_time": centre + rng.normal(0, 2),
                    "throughput_per_h": 1000 - centre + rng.normal(0, 2),
                }
            )
    return pd.DataFrame(rows)


def test_summary_has_a_ci_around_each_mean():
    s = summarise(fake_results(), ["mean_travel_time"])
    assert len(s) == 4 and (s["n"] == 5).all()
    assert (s["ci_lo"] <= s["mean"]).all() and (s["mean"] <= s["ci_hi"]).all()


def test_compare_against_the_best_baseline():
    c = compare(fake_results(), "mean_travel_time", ["coop"], "best_baseline")
    row = c.iloc[0]
    assert row["reference"] == "mp"
    assert row["improvement_pct"] == pytest.approx(100 * (150 - 140) / 150, abs=2)
    assert row["cliffs_delta"] == -1.0 and row["effect"] == "large"
    assert row["kind"] == "best_baseline"


def test_compare_respects_higher_is_better_metrics():
    c = compare(fake_results(), "throughput_per_h", ["coop"], "best_baseline")
    assert c.iloc[0]["reference"] == "mp" and c.iloc[0]["improvement_pct"] > 0


def test_expand_enumerates_cells_and_skips_learned_methods_without_checkpoints():
    exp = {
        "seeds": [0, 1],
        "cells": [
            {
                "network": "grid2x2",
                "methods": ["ft", "mp", "coop_not_trained"],
                "demands": ["low", "peak"],
                "scenarios": ["normal", "incident+emergency"],
            }
        ],
    }
    specs, warnings = expand(exp)
    assert len(specs) == 2 * 2 * 2 * 2
    assert {s.scenarios for s in specs} == {(), ("incident", "emergency")}
    assert warnings and "coop_not_trained" in warnings[0]


def test_learned_runs_get_two_way_intervals_and_paired_comparisons():
    rng = np.random.default_rng(3)
    seed_effect = rng.normal(0, 20, size=5)
    rows = []
    for seed in range(5):
        rows.append(
            {
                "run_id": f"mp__g__normal__peak__s{seed}",
                "network": "g",
                "scenario": "normal",
                "demand": "peak",
                "method": "mp",
                "seed": seed,
                "mean_travel_time": 200 + seed_effect[seed],
            }
        )
        for t, offset in ((1, 8.0), (2, 12.0), (3, 10.0)):
            rows.append(
                {
                    "run_id": f"coop-t{t}__g__normal__peak__s{seed}",
                    "network": "g",
                    "scenario": "normal",
                    "demand": "peak",
                    "method": "coop",
                    "seed": seed,
                    "mean_travel_time": 200 + seed_effect[seed] + offset,
                }
            )
    df = pd.DataFrame(rows)
    s = summarise(df, ["mean_travel_time"]).set_index("method")
    assert s.loc["coop", "n"] == 15 and s.loc["coop", "n_train"] == 3
    assert s.loc["mp", "n_train"] == 1
    row = compare(df, "mean_travel_time", ["coop"], "best_baseline").iloc[0]
    # coop is 10 s slower on every seed: the paired comparison sees it, with a tight CI
    expected = -100 * 10.0 / df[df.method == "mp"]["mean_travel_time"].mean()
    assert row["paired_improvement_pct"] == pytest.approx(expected, abs=0.01)
    assert row["paired_ci_lo"] <= row["paired_improvement_pct"] <= row["paired_ci_hi"] < 0


def test_holm_is_applied_within_the_core_family_only():
    comp = pd.DataFrame(
        {
            "network": ["g", "g", "g"],
            "scenario": ["normal", "normal", "incident"],
            "demand": ["peak", "low", "peak"],
            "method": ["coop", "coop", "coop"],
            "p_value": [0.01, 0.02, 0.001],
            "comparison": ["learned_vs_best"] * 3,
        }
    )
    core = {("g", "normal", "peak", "coop"), ("g", "normal", "low", "coop")}
    out = assign_families(comp, core)
    assert out["family"].tolist() == ["core", "core", "exploratory"]
    # the exploratory test does not enlarge the core family
    assert out["p_holm"].tolist() == pytest.approx([0.02, 0.02, 0.001])
