import pytest

from agents.llm.schemas import (
    EMPTY_ENVELOPE,
    SchemaError,
    validate_directive,
    validate_envelope,
)

TLS = {"A", "B"}


def test_valid_bias_defaults_and_ttl():
    directive, notes = validate_directive({"tls": "A", "type": "bias"}, "operator", TLS, t=5.0)
    assert directive.ns == 1.0 and directive.ew == 1.0
    assert directive.ttl_s == 30.0 and directive.issued_at == 5.0
    assert notes == []


def test_bias_clipped_with_note():
    directive, notes = validate_directive(
        {"tls": "A", "type": "bias", "ns": 3.0, "ew": 0.1}, "operator", TLS)
    assert directive.ns == 2.0 and directive.ew == 0.5
    assert any("ns clipped" in note for note in notes)
    assert any("ew clipped" in note for note in notes)


def test_ttl_clipped():
    directive, notes = validate_directive(
        {"tls": "A", "type": "bias", "ttl_s": 120}, "operator", TLS)
    assert directive.ttl_s == 60.0
    assert notes


def test_unknown_tls_rejected():
    with pytest.raises(SchemaError, match="unknown tls"):
        validate_directive({"tls": "Z", "type": "bias"}, "operator", TLS)


def test_unknown_type_rejected():
    with pytest.raises(SchemaError, match="unknown directive type"):
        validate_directive({"tls": "A", "type": "teleport"}, "operator", TLS)


def test_wrong_role_rejected():
    with pytest.raises(SchemaError, match="may not emit"):
        validate_directive(
            {"tls": "A", "type": "preempt", "phase": "NS", "hold_s": 5, "ev": "ev0"},
            "operator", TLS)


def test_hold_requires_extra_green():
    with pytest.raises(SchemaError, match="extra_green_s"):
        validate_directive({"tls": "A", "type": "hold", "phase": "NS"}, "operator", TLS)


def test_preempt_requires_ev():
    with pytest.raises(SchemaError, match="'ev'"):
        validate_directive(
            {"tls": "A", "type": "preempt", "phase": "NS", "hold_s": 5}, "emergency", TLS)


def test_preempt_axis_and_params():
    directive, _ = validate_directive(
        {"tls": "A", "type": "preempt", "phase": "ew", "hold_s": 30,
         "ev": "ev_1", "eta_s": 12.5},
        "emergency", TLS)
    assert directive.axis == "EW"
    assert directive.start_in_s == 0.0 and directive.hold_s == 30.0
    assert directive.ev == "ev_1" and directive.eta_s == 12.5


def test_serve_ped_clipped():
    directive, notes = validate_directive(
        {"tls": "A", "type": "serve_ped", "phase": "NS", "min_green_s": 50},
        "pedestrian", TLS)
    assert directive.min_green_s == 30.0
    assert notes


def test_non_dict_directive_rejected():
    with pytest.raises(SchemaError, match="JSON object"):
        validate_directive("bias", "operator", TLS)


def test_envelope_must_be_object():
    with pytest.raises(SchemaError):
        validate_envelope([], "operator", TLS)


def test_envelope_directives_must_be_list():
    with pytest.raises(SchemaError, match="must be a list"):
        validate_envelope({"directives": {}}, "operator", TLS)


def test_envelope_mixes_accepted_and_rejected():
    result = validate_envelope({
        "directives": [
            {"tls": "A", "type": "bias", "ns": 1.5},
            {"tls": "Z", "type": "bias"},
            {"tls": "B", "type": "preempt", "phase": "NS", "hold_s": 10, "ev": "ev0"},
        ],
        "explanation": "hello",
    }, "operator", TLS)
    assert len(result.accepted) == 1 and len(result.rejected) == 2
    assert result.explanation == "hello"


def test_duplicate_directives_rejected():
    result = validate_envelope({"directives": [
        {"tls": "A", "type": "bias", "ns": 1.5},
        {"tls": "A", "type": "bias", "ns": 1.2},
    ]}, "operator", TLS)
    assert len(result.accepted) == 1 and len(result.rejected) == 1


def test_alerts_filtered_and_explanation_truncated():
    result = validate_envelope({
        "directives": [],
        "alerts": [{"kind": "spillback", "where": "B2B1"}, {"where": "x"}, "nope"],
        "explanation": "x" * 1000,
    }, "operator", TLS)
    assert result.alerts == [{"kind": "spillback", "where": "B2B1"}]
    assert len(result.warnings) == 2
    assert len(result.explanation) == 500


def test_empty_envelope_valid():
    result = validate_envelope(EMPTY_ENVELOPE, "operator", TLS)
    assert result.accepted == [] and result.rejected == []
