"""Arbiter validation and priority tests."""

from __future__ import annotations

import pytest

from cotraffic.controllers.llm_team.arbiter import Arbiter, select_winner
from cotraffic.controllers.llm_team.schemas import Directive, SchemaError

TLS = ["A", "B"]
STATE = {
    "A": {"current_axis": "NS", "time_in_phase": 5},
    "B": {"current_axis": "EW", "time_in_phase": 2},
}


def test_valid_envelope_accepted_with_issued_at():
    arbiter = Arbiter(TLS)
    result = arbiter.submit(
        "operator", {"directives": [{"tls": "A", "type": "bias", "ns": 1.5}]}, 12.0, STATE
    )
    assert len(result.accepted) == 1
    assert result.accepted[0].issued_at == 12.0


def test_wrong_role_rejected_but_rest_applies():
    arbiter = Arbiter(TLS)
    result = arbiter.submit(
        "operator",
        {
            "directives": [
                {"tls": "A", "type": "bias", "ns": 1.5},
                {
                    "tls": "A",
                    "type": "preempt",
                    "phase": "NS",
                    "hold_s": 10,
                    "ev": "ev0",
                },
            ]
        },
        0.0,
        STATE,
    )
    assert len(result.accepted) == 1 and len(result.rejected) == 1
    assert "may not emit" in result.rejected[0].reason


def test_hold_rejected_when_axis_not_green():
    arbiter = Arbiter(TLS)
    result = arbiter.submit(
        "operator",
        {"directives": [{"tls": "A", "type": "hold", "phase": "EW", "extra_green_s": 5}]},
        0.0,
        STATE,
    )
    assert len(result.accepted) == 0 and len(result.rejected) == 1
    assert "current green" in result.rejected[0].reason


def test_preempt_short_lead_warns():
    arbiter = Arbiter(TLS)
    result = arbiter.submit(
        "emergency",
        {
            "directives": [
                {
                    "tls": "A",
                    "type": "preempt",
                    "phase": "NS",
                    "start_in_s": 5,
                    "hold_s": 10,
                    "ev": "ev0",
                },
                {
                    "tls": "B",
                    "type": "preempt",
                    "phase": "EW",
                    "start_in_s": 0,
                    "hold_s": 10,
                    "ev": "ev0",
                },
            ]
        },
        0.0,
        STATE,
    )
    assert len(result.accepted) == 2
    assert sum("short lead" in warning for warning in result.warnings) == 1


def test_malformed_envelope_raises():
    arbiter = Arbiter(TLS)
    with pytest.raises(SchemaError):
        arbiter.submit("operator", "not an envelope", 0.0, STATE)


def test_select_winner_priority_and_eta():
    hold = Directive(tls_id="A", type="hold", axis="NS", extra_green_s=5, issued_at=0)
    preempt = Directive(
        tls_id="A",
        type="preempt",
        axis="EW",
        start_in_s=0,
        hold_s=10,
        ev="ev0",
        eta_s=8,
        issued_at=0,
    )
    assert select_winner([hold, preempt], STATE["A"]).type == "preempt"

    far = Directive(
        tls_id="A",
        type="preempt",
        axis="NS",
        start_in_s=0,
        hold_s=10,
        ev="ev1",
        eta_s=20,
        issued_at=0,
    )
    assert select_winner([far, preempt], STATE["A"]).ev == "ev0"
    assert select_winner([hold], STATE["A"]).type == "hold"
    bias = Directive(tls_id="A", type="bias", ns=1.5, ew=1.0, issued_at=0)
    assert select_winner([bias], STATE["A"]) is None


def test_to_record_shape():
    arbiter = Arbiter(TLS)
    result = arbiter.submit(
        "operator",
        {"directives": [{"tls": "A", "type": "bias", "ns": 3.0}], "explanation": "why"},
        0.0,
        STATE,
    )
    record = result.to_record()
    assert record["agent"] == "operator" and record["t"] == 0.0
    assert record["accepted"][0]["ns"] == 2.0
    assert record["warnings"]
    assert result.feedback_payload()["accepted"][0]["type"] == "bias"
