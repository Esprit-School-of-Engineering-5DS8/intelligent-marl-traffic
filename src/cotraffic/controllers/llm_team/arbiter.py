"""Code-side validation and conflict resolution for LLM directives."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from cotraffic.controllers.llm_team.schemas import (
    Directive,
    EnvelopeResult,
    RejectedDirective,
    validate_envelope,
)


@dataclass(frozen=True)
class ArbiterConfig:
    lead_time_warn_s: float = 15.0
    feedback_ttl_s: float = 60.0
    explanation_max_chars: int = 500


@dataclass
class ArbiterResult:
    role: str
    t: float
    accepted: list[Directive] = field(default_factory=list)
    rejected: list[RejectedDirective] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""

    def to_record(self) -> dict[str, Any]:
        return {
            "agent": self.role,
            "t": self.t,
            "accepted": [d.to_dict() for d in self.accepted],
            "rejected": [{"directive": dict(r.raw), "reason": r.reason} for r in self.rejected],
            "warnings": list(self.warnings),
            "alerts": list(self.alerts),
            "explanation": self.explanation,
        }

    def feedback_payload(self) -> dict[str, Any]:
        return {
            "accepted": [d.to_dict() for d in self.accepted],
            "rejected": [r.reason for r in self.rejected],
            "warnings": list(self.warnings),
        }


class Arbiter:
    def __init__(self, tls_ids: Iterable[str], config: ArbiterConfig | None = None) -> None:
        self.tls_ids = frozenset(tls_ids)
        self.config = config or ArbiterConfig()

    def submit(
        self,
        role: str,
        raw_envelope: Any,
        t: float,
        states: Mapping[str, Mapping[str, Any]],
    ) -> ArbiterResult:
        envelope: EnvelopeResult = validate_envelope(
            raw_envelope,
            role,
            self.tls_ids,
            t,
            explanation_max_chars=self.config.explanation_max_chars,
        )
        accepted: list[Directive] = []
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
            role=role,
            t=t,
            accepted=accepted,
            rejected=rejected,
            warnings=warnings,
            alerts=envelope.alerts,
            explanation=envelope.explanation,
        )

    @staticmethod
    def _state_issue(directive: Directive, state: Mapping[str, Any]) -> str | None:
        if directive.type == "hold":
            current = state.get("current_axis")
            if current != directive.axis:
                return (
                    f"hold target {directive.axis} is not the current green "
                    f"({current or 'transition'})"
                )
        return None


def select_winner(
    directives: Sequence[Directive], state: Mapping[str, Any]
) -> Directive | None:
    for dtype in ("preempt", "serve_ped", "hold"):
        group = [d for d in directives if d.type == dtype]
        if not group:
            continue
        if dtype == "preempt":
            return min(
                group,
                key=lambda d: (
                    d.eta_s if d.eta_s is not None else math.inf,
                    d.start_in_s or 0.0,
                    d.issued_at,
                ),
            )
        current = state.get("current_axis")
        matching = [d for d in group if d.axis == current]
        return max(matching or group, key=lambda d: d.issued_at)
    return None
