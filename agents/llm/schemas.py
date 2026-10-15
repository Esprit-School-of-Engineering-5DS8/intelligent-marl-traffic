"""
agents/llm/schemas.py
The directive contract (plan section 4.3) and envelope validation.

LLM agents may only emit an envelope containing typed directives. Everything
that constrains them lives here: allowed types per role, parameter ranges and
clipping, TTL defaults. Pure Python — no SUMO, no network, no TraCI — so the
whole contract is unit-testable.

Axis convention: "NS" (action 0) / "EW" (action 1), matching the binary
action space of the fast layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

AXES = ("NS", "EW")
AXIS_TO_ACTION = {"NS": 0, "EW": 1}
ACTION_TO_AXIS = {0: "NS", 1: "EW"}

DIRECTIVE_TYPES = ("bias", "hold", "preempt", "serve_ped")

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "operator": frozenset({"bias", "hold"}),
    "emergency": frozenset({"preempt"}),
    "pedestrian": frozenset({"serve_ped"}),
}

DEFAULT_TTL_S = 30.0
TTL_RANGE = (1.0, 60.0)

PARAM_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "bias": {"ns": (0.5, 2.0), "ew": (0.5, 2.0)},
    "hold": {"extra_green_s": (1.0, 20.0)},
    "preempt": {"start_in_s": (0.0, 60.0), "hold_s": (0.0, 40.0), "eta_s": (0.0, 300.0)},
    "serve_ped": {"min_green_s": (1.0, 30.0)},
}

REQUIRED_PARAMS: Dict[str, Tuple[str, ...]] = {
    "bias": (),
    "hold": ("extra_green_s",),
    "preempt": ("hold_s", "ev"),
    "serve_ped": ("min_green_s",),
}

# Passed to clients that support structured output (OpenAICompat sends it as
# prompt metadata only; schema enforcement is advisory there).
DIRECTIVE_ENVELOPE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent": {"type": "string"},
        "t": {"type": "number"},
        "directives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tls": {"type": "string"},
                    "type": {"enum": list(DIRECTIVE_TYPES)},
                    "phase": {"enum": list(AXES)},
                    "ttl_s": {"type": "number", "minimum": TTL_RANGE[0], "maximum": TTL_RANGE[1]},
                },
                "required": ["tls", "type"],
            },
        },
        "alerts": {"type": "array", "items": {"type": "object"}},
        "explanation": {"type": "string"},
    },
    "required": ["directives"],
}

EMPTY_ENVELOPE: Dict[str, Any] = {"directives": [], "alerts": [], "explanation": ""}


class SchemaError(ValueError):
    """An envelope or directive does not match the directive contract."""


@dataclass(frozen=True)
class Directive:
    """One validated directive, ready for the DirectiveLayer."""

    tls_id: str
    type: str
    axis: Optional[str] = None  # hold / preempt / serve_ped
    ns: Optional[float] = None  # bias
    ew: Optional[float] = None  # bias
    extra_green_s: Optional[float] = None  # hold
    start_in_s: Optional[float] = None  # preempt
    hold_s: Optional[float] = None  # preempt
    ev: Optional[str] = None  # preempt
    eta_s: Optional[float] = None  # preempt (conflict resolution)
    min_green_s: Optional[float] = None  # serve_ped
    # Exact green group within the directive's axis (N-phase programs only).
    # Set by the code-side reviewer (never prompted): with 3+ green sets per
    # junction, "NS"/"EW" alone cannot address the protected-turn phase an EV
    # actually approaches.
    phase_index: Optional[int] = None
    ttl_s: float = DEFAULT_TTL_S
    issued_at: float = 0.0

    def key(self) -> Tuple[str, str, Optional[str]]:
        """Storage key: one slot per (type, ev); non-preempt types replace."""
        return (self.type, self.ev if self.type == "preempt" else None)

    def to_dict(self) -> Dict[str, Any]:
        record: Dict[str, Any] = {"tls": self.tls_id, "type": self.type, "ttl_s": self.ttl_s}
        for name in ("phase",):
            axis = getattr(self, "axis")
            if axis is not None:
                record[name] = axis
        for name in ("ns", "ew", "extra_green_s", "start_in_s", "hold_s", "ev",
                     "eta_s", "min_green_s", "phase_index"):
            value = getattr(self, name)
            if value is not None:
                record[name] = value
        record["issued_at"] = self.issued_at
        return record


@dataclass(frozen=True)
class RejectedDirective:
    """A directive dropped by validation, with the reason for the feedback loop."""

    raw: Mapping[str, Any]
    reason: str


@dataclass
class EnvelopeResult:
    """Outcome of validating one raw LLM envelope."""

    accepted: List[Directive] = field(default_factory=list)
    rejected: List[RejectedDirective] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    explanation: str = ""


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError(f"parameter '{name}' must be a number, got {value!r}")
    return float(value)


def _clip(value: float, bounds: Tuple[float, float], name: str, notes: List[str]) -> float:
    lo, hi = bounds
    if value < lo:
        notes.append(f"{name} clipped up: {value:.2f} -> {lo:.2f}")
        return lo
    if value > hi:
        notes.append(f"{name} clipped down: {value:.2f} -> {hi:.2f}")
        return hi
    return value


def _axis(value: Any, name: str = "phase") -> str:
    if isinstance(value, str) and value.strip().upper() in AXES:
        return value.strip().upper()
    raise SchemaError(f"'{name}' must be one of {AXES}, got {value!r}")


def _required(raw: Mapping[str, Any], name: str, dtype: str) -> Any:
    if name not in raw or raw[name] is None:
        raise SchemaError(f"'{dtype}' directive requires '{name}'")
    return raw[name]


def validate_directive(
    raw: Any,
    role: str,
    tls_ids: Iterable[str],
    t: float = 0.0,
) -> Tuple[Directive, List[str]]:
    """
    Validate and clip one raw directive. Returns (directive, notes); notes are
    human-readable clipping messages. Raises SchemaError when the directive is
    not acceptable at all (unknown TLS/type, wrong role, missing parameter).
    """
    if not isinstance(raw, Mapping):
        raise SchemaError("directive must be a JSON object")

    tls_id = raw.get("tls")
    if not isinstance(tls_id, str) or not tls_id:
        raise SchemaError("directive is missing 'tls'")
    if tls_id not in set(tls_ids):
        raise SchemaError(f"unknown tls '{tls_id}'")

    dtype = raw.get("type")
    if dtype not in DIRECTIVE_TYPES:
        raise SchemaError(f"unknown directive type '{dtype}'")
    if dtype not in ROLE_PERMISSIONS.get(role, frozenset()):
        raise SchemaError(f"role '{role}' may not emit '{dtype}' directives")

    notes: List[str] = []
    ttl = _clip(_number(raw.get("ttl_s", DEFAULT_TTL_S), "ttl_s"), TTL_RANGE, "ttl_s", notes)

    for name in REQUIRED_PARAMS[dtype]:
        _required(raw, name, dtype)
    for name in PARAM_RANGES[dtype]:
        if name in raw and raw[name] is not None:
            _number(raw[name], name)

    kwargs: Dict[str, Any] = {"tls_id": tls_id, "type": dtype, "ttl_s": ttl, "issued_at": t}

    if dtype in ("hold", "preempt", "serve_ped"):
        kwargs["axis"] = _axis(raw.get("phase"))
        if raw.get("phase_index") is not None:
            value = raw["phase_index"]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SchemaError(
                    f"'phase_index' must be a non-negative integer, got {value!r}")
            kwargs["phase_index"] = int(value)

    if dtype == "bias":
        kwargs["ns"] = _clip(_number(raw.get("ns", 1.0), "ns"), PARAM_RANGES["bias"]["ns"], "ns", notes)
        kwargs["ew"] = _clip(_number(raw.get("ew", 1.0), "ew"), PARAM_RANGES["bias"]["ew"], "ew", notes)
    elif dtype == "hold":
        kwargs["extra_green_s"] = _clip(
            _number(raw["extra_green_s"], "extra_green_s"),
            PARAM_RANGES["hold"]["extra_green_s"], "extra_green_s", notes)
    elif dtype == "preempt":
        kwargs["start_in_s"] = _clip(
            _number(raw.get("start_in_s", 0.0), "start_in_s"),
            PARAM_RANGES["preempt"]["start_in_s"], "start_in_s", notes)
        kwargs["hold_s"] = _clip(
            _number(raw["hold_s"], "hold_s"),
            PARAM_RANGES["preempt"]["hold_s"], "hold_s", notes)
        ev = raw["ev"]
        if not isinstance(ev, str) or not ev:
            raise SchemaError("'preempt' directive requires a non-empty 'ev' string")
        kwargs["ev"] = ev
        if raw.get("eta_s") is not None:
            kwargs["eta_s"] = _clip(
                _number(raw["eta_s"], "eta_s"),
                PARAM_RANGES["preempt"]["eta_s"], "eta_s", notes)
    elif dtype == "serve_ped":
        kwargs["min_green_s"] = _clip(
            _number(raw["min_green_s"], "min_green_s"),
            PARAM_RANGES["serve_ped"]["min_green_s"], "min_green_s", notes)

    return Directive(**kwargs), notes


def validate_envelope(
    raw: Any,
    role: str,
    tls_ids: Iterable[str],
    t: float = 0.0,
    explanation_max_chars: int = 500,
) -> EnvelopeResult:
    """
    Validate a whole envelope. Structural problems (not an object, directives
    not a list) raise SchemaError and count as a failed LLM call; per-directive
    problems are collected as rejected directives so the rest still applies.
    """
    if not isinstance(raw, Mapping):
        raise SchemaError(f"envelope must be a JSON object, got {type(raw).__name__}")

    raw_directives = raw.get("directives", [])
    if not isinstance(raw_directives, list):
        raise SchemaError("'directives' must be a list")

    result = EnvelopeResult()
    seen: set = set()
    for item in raw_directives:
        try:
            directive, notes = validate_directive(item, role, tls_ids, t)
        except SchemaError as exc:
            result.rejected.append(RejectedDirective(raw=item if isinstance(item, Mapping) else {"raw": item},
                                                     reason=str(exc)))
            continue
        key = (directive.tls_id,) + directive.key()
        if key in seen:
            result.rejected.append(RejectedDirective(raw=item, reason=f"duplicate directive {key[1:]} for {directive.tls_id}"))
            continue
        seen.add(key)
        if notes:
            result.warnings.extend(f"{directive.tls_id}: {note}" for note in notes)
        result.accepted.append(directive)

    raw_alerts = raw.get("alerts", [])
    if isinstance(raw_alerts, list):
        for alert in raw_alerts:
            if isinstance(alert, Mapping) and isinstance(alert.get("kind"), str) and alert["kind"]:
                result.alerts.append(dict(alert))
            else:
                result.warnings.append("alert dropped: missing 'kind'")
    elif raw_alerts:
        result.warnings.append("'alerts' must be a list; ignored")

    explanation = raw.get("explanation", "")
    if isinstance(explanation, str):
        result.explanation = explanation[:explanation_max_chars]
    return result
