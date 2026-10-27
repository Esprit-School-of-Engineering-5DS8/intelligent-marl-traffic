"""The LLM A/B contract: a budget that fails loudly and an aggregate that keeps it honest.

Two things make an LLM number comparable to a controller instead of a decoration: the
episode must not silently finish on Max-Pressure (the fallback), and a row that did only
that must be recorded as such and kept out of the LLM tables.
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from cotraffic.analysis.aggregate import (
    hyperparameters,
    llm_health,
    llm_valid_column,
    valid_only,
)
from cotraffic.controllers.llm import LLMController

from test_llm_controller import FakeEnv, FakeProvider


def test_budget_caps_calls_and_is_reported_as_budget_not_a_result():
    provider = FakeProvider({"phases": [1, 0]})
    controller = LLMController(client=provider, interval_s=30, max_calls=2)
    env = FakeEnv()
    controller.reset(env)

    controller.act(env, {})  # call 1
    env.now = 30.0
    controller.act(env, {})  # call 2, budget now spent
    env.now = 60.0
    actions = controller.act(env, {})
    env.now = 90.0
    controller.act(env, {})

    assert provider.calls == 2  # never asked again
    assert set(actions) == set(env.intersections)  # still a full decision for the shield
    metrics = controller.metrics()
    assert metrics["llm_budget_hit"] == 1
    assert metrics["llm_status"] == "budget"
    assert metrics["llm_valid"] == 0
    assert metrics["llm_fallbacks"] >= 2


def test_a_clean_episode_is_ok_and_valid():
    provider = FakeProvider({"phases": [1, 0]})
    controller = LLMController(client=provider, interval_s=30, max_calls=48)
    env = FakeEnv()
    controller.reset(env)

    controller.act(env, {})
    env.now = 30.0
    controller.act(env, {})

    metrics = controller.metrics()
    assert metrics["llm_status"] == "ok"
    assert metrics["llm_valid"] == 1
    assert metrics["llm_coverage_pct"] == 100.0


def test_legacy_rows_without_the_verdict_are_recovered_from_their_counters():
    df = pd.DataFrame(
        {
            "method": ["llm", "llm", "llm", "mp"],
            "llm_available": [1, 1, 0, 0],
            "llm_calls": [40, 40, 0, 0],
            "llm_success": [40, 0, 0, 0],
        }
    )
    assert list(llm_valid_column(df)) == [1, 0, 0, 0]
    # A fallback-only LLM row measures Max-Pressure, so no table may count it as an LLM
    # result - while the baseline row itself is untouched.
    assert list(valid_only(df)["method"]) == ["llm", "mp"]


def test_llm_health_records_the_degraded_run_instead_of_dropping_it():
    df = pd.DataFrame(
        {
            "run_id": ["llm__grid3x3__normal__peak__s1"],
            "method": ["llm"],
            "network": ["grid3x3"],
            "scenario": ["normal"],
            "demand": ["peak"],
            "seed": [1],
            "llm_available": [1],
            "llm_calls": [12],
            "llm_success": [0],
            "llm_fallbacks": [12],
            "llm_last_error": ["HTTPError: 429 rate limit"],
        }
    )
    health = llm_health(df)
    assert len(health) == 1
    row = health.iloc[0]
    assert row["llm_status"] == "degraded"
    assert row["llm_valid"] == 0
    assert row["llm_errors"] == 12
    assert "429" in row["llm_last_error"]


def _fake_episode(**kwargs):
    """A result row shaped like run_episode's, so the compare worker can be tested without SUMO.

    Coop is 10 s better than MP on waiting time and the LLM is 5 s better, on every seed.
    """
    method, seed = kwargs["method"], kwargs["seed"]
    waiting = {"mp": 90.0, "coop": 80.0, "llm": 85.0}.get(method, 90.0)
    row = {
        "method": method,
        "seed": seed,
        "mean_waiting_time": waiting - seed,
        "mean_travel_time": 200.0,
        "throughput_per_h": 1000.0 + seed,
        "co2_total_kg": 100.0,
        "stops_per_vehicle": 5.0,
        "p95_waiting_time": 120.0,
        "parameters": json.dumps({"controller": method, "learning_rate": 0.0003}),
    }
    if method == "llm":
        row.update(
            {
                "llm_status": "ok",
                "llm_valid": 1,
                "llm_calls": 40,
                "llm_success": 40,
                "llm_errors": 0,
                "llm_coverage_pct": 100.0,
                "llm_prompt_tokens": 22_800,
                "llm_last_error": "",
            }
        )
    return row


def _compare_job(methods: list[str], seeds: list[int]):
    from api.jobs import JobRecord

    return JobRecord(
        id="comp_test",
        kind="compare",
        request={
            "network": "grid2x2",
            "scenario": "normal",
            "demand": "medium",
            "seed": seeds[0],
            "seeds": seeds,
            "methods": methods,
            "quick": True,
        },
        total_steps=len(methods) * len(seeds),
    )


def test_compare_returns_paired_deltas_parameters_and_llm_health(monkeypatch):
    import cotraffic.evaluation.runner as runner_mod

    from api.jobs import JobRunner

    monkeypatch.setattr(runner_mod, "run_episode", _fake_episode)
    job = _compare_job(["mp", "coop", "llm"], [1, 2, 3])
    JobRunner()._run_compare(job)

    assert job.status == "done"
    result = job.result
    assert result["seeds"] == [1, 2, 3]
    assert result["reference"] == "mp"  # best baseline present
    assert set(result["rows"]) == {"mp", "coop", "llm"}
    assert len(result["perSeed"]["coop"]) == 3  # one row per seed, not one per method

    wait = [c for c in result["comparisons"] if c["metric"] == "mean_waiting_time"]
    coop = next(c for c in wait if c["method"] == "coop")
    assert coop["improvementPct"] > 0  # coop is better, so the delta is oriented positive
    assert coop["pairedCiLo"] <= coop["pairedImprovementPct"] <= coop["pairedCiHi"]
    assert coop["pHolm"] is not None and coop["significant"] in (True, False)
    assert coop["nSeeds"] == 3
    assert next(c for c in wait if c["method"] == "mp")["isReference"] is True

    # Hyperparameters travel with the result, so a delta can be attributed to a config.
    assert result["parameters"]["coop"]["learning_rate"] == 0.0003
    health = result["llm"]["llm"]
    assert health["validSeeds"] == 3 and health["seeds"] == 3
    assert health["calls"] == 120 and health["promptTokens"] == 68_400
    assert result["warnings"] == []
    assert "paired seeds" in result["verdict"]


def test_compare_reports_a_degraded_llm_instead_of_reporting_it_as_the_model(monkeypatch):
    import cotraffic.evaluation.runner as runner_mod

    from api.jobs import JobRunner

    def degraded(**kwargs):
        row = _fake_episode(**kwargs)
        if row["method"] == "llm":
            row.update({"llm_status": "degraded", "llm_valid": 0, "llm_success": 0, "llm_errors": 40})
        return row

    monkeypatch.setattr(runner_mod, "run_episode", degraded)
    job = _compare_job(["mp", "llm"], [1, 2])
    JobRunner()._run_compare(job)

    health = job.result["llm"]["llm"]
    assert health["validSeeds"] == 0
    assert health["statuses"] == ["degraded", "degraded"]
    assert any("not LLM results" in w for w in job.result["warnings"])


def test_compare_warns_that_one_seed_cannot_be_tested(monkeypatch):
    import cotraffic.evaluation.runner as runner_mod

    from api.jobs import JobRunner

    monkeypatch.setattr(runner_mod, "run_episode", _fake_episode)
    job = _compare_job(["mp", "coop"], [1])
    JobRunner()._run_compare(job)

    assert any("one seed" in w for w in job.result["warnings"])
    assert all(c["pHolm"] is None for c in job.result["comparisons"] if not c["isReference"])


def test_hyperparameters_table_names_the_knobs_of_each_configuration():
    df = pd.DataFrame(
        {
            "method": ["coop"] * 3,
            "variant": ["coop"] * 3,
            "parameters": ['{"algorithm": "ppo", "learning_rate": 0.0003}'] * 3,
            "param_hash": ["deadbeef1234"] * 3,
        }
    )
    table = hyperparameters(df)
    assert set(table["parameter"]) == {"algorithm", "learning_rate"}
    assert set(table["runs"]) == {3}  # three result rows share the configuration
    assert set(table["param_hash"]) == {"deadbeef1234"}
