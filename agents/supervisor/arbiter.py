"""
agents/supervisor/arbiter.py
The arbiter (plan section 4.4): plain code, no LLM, no TraCI.

Duties:
- schema validation, clipping and role permissions (delegated to schemas.py),
- state-aware rejection (a `hold` must target the currently green axis),
- pre-emption lead-time warning,
- conflict resolution: `preempt` > `serve_ped` > `hold` > `bias`; two preempts
  on one TLS: lowest ETA wins (ties: earliest effective start, then age).
- feedback: accepted/rejected/clipped results are returned so the supervisor
  can post them to the blackboard and log them.

Numerical caps and the starvation guard live in DirectiveLayer, the component
that actually enforces them over time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from agents.llm.schemas import (
    Directive,
    EnvelopeResult,
    RejectedDirective,
    SchemaError,
    validate_envelope,
)


@dataclass(frozen=True)
class ArbiterConfig:
    lead_time_warn_s: float = 15.0
    feedback_ttl_s: float = 60.0
    explanation_max_chars: int = 500


@dataclass
class ArbiterResult:
    """Outcome of one agent submission, ready for logging and feedback."""

    role: str
    t: float
    accepted: List[Directive] = field(default_factory=list)
    rejected: List[RejectedDirective] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    explanation: str = ""

    def to_record(self) -> Dict[str, Any]:
        return {
            "agent": self.role,
            "t": self.t,
            "accepted": [d.to_dict() for d in self.accepted],
            "rejected": [{"directive": dict(r.raw), "reason": r.reason} for r in self.rejected],
            "warnings": list(self.warnings),
            "alerts": list(self.alerts),
            "explanation": self.explanation,
        }

    def feedback_payload(self) -> Dict[str, Any]:
        return {
            "accepted": [d.to_dict() for d in self.accepted],
            "rejected": [r.reason for r in self.rejected],
            "warnings": list(self.warnings),
        }


class Arbiter:
    def __init__(self, tls_ids: Iterable[str], config: Optional[ArbiterConfig] = None):
        self.tls_ids = frozenset(tls_ids)
        self.config = config or ArbiterConfig()

    def submit(self, role: str, raw_envelope: Any, t: float,
               states: Mapping[str, Mapping[str, Any]]) -> ArbiterResult:
        """
        Validate one agent envelope. Raises SchemaError when the envelope itself
        is malformed (the supervisor treats that as a failed call and falls
        back); per-directive errors are returned as rejections.
        """
        envelope: EnvelopeResult = validate_envelope(
            raw_envelope, role, self.tls_ids, t,
            explanation_max_chars=self.config.explanation_max_chars,
        )
        accepted: List[Directive] = []
        rejected = list(envelope.rejected)
        warnings = list(envelope.warnings)

        for directive in envelope.accepted:
            issue = self._state_issue(directive, states.get(directive.tls_id, {}))
            if issue is not None:
                rejected.append(RejectedDirective(raw=directive.to_dict(), reason=issue))
                continue
            accepted.append(directive)
            if directive.type == "preempt":
                start_in = directive.start_in_s or 0.0
                if 0.0 < start_in < self.config.lead_time_warn_s:
                    warnings.append(
                        f"preempt@{directive.tls_id}: short lead {start_in:.1f}s "
                        f"< {self.config.lead_time_warn_s:.0f}s"
                    )
        return ArbiterResult(
            role=role, t=t, accepted=accepted, rejected=rejected,
            warnings=warnings, alerts=envelope.alerts, explanation=envelope.explanation,
        )

    @staticmethod
    def _state_issue(directive: Directive, state: Mapping[str, Any]) -> Optional[str]:
        if directive.type == "hold":
            current = state.get("current_axis")
            if current != directive.axis:
                return (f"hold target {directive.axis} is not the current green "
                        f"({current or 'transition'})")
        return None


def select_winner(directives: Sequence[Directive],
                  state: Mapping[str, Any]) -> Optional[Directive]:
    """
    Highest-priority active directive for one TLS. `bias` is excluded on
    purpose: biases are merged by the DirectiveLayer instead of winning.
    """
    for dtype in ("preempt", "serve_ped", "hold"):
        group = [d for d in directives if d.type == dtype]
        if not group:
            continue
        if dtype == "preempt":
            # Earliest ETA wins; ties by earliest effective start, then age.
            return min(
                group,
                key=lambda d: (
                    d.eta_s if d.eta_s is not None else math.inf,
                    d.start_in_s or 0.0,
                    d.issued_at,
                ),
            )
        # serve_ped / hold: prefer the directive serving the current green.
        current = state.get("current_axis")
        matching = [d for d in group if d.axis == current]
        return max(matching or group, key=lambda d: d.issued_at)
    return None
