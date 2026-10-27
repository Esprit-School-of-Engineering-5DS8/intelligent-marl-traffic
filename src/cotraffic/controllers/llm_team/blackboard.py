"""Shared typed message board for the LLM roles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BlackboardMessage:
    kind: str
    source: str
    t: float
    ttl_s: float = 60.0
    payload: dict[str, Any] = field(default_factory=dict)

    def expired(self, t: float) -> bool:
        return t >= self.t + self.ttl_s

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "from": self.source,
            "type": self.kind,
            "t": round(self.t, 1),
            "expires_at": round(self.t + self.ttl_s, 1),
        }
        record.update(self.payload)
        return record


class Blackboard:
    """Append-only message board; expired messages are pruned on access."""

    def __init__(self) -> None:
        self._messages: list[BlackboardMessage] = []

    def post(self, message: BlackboardMessage) -> None:
        self._messages.append(message)

    def post_message(
        self,
        kind: str,
        source: str,
        t: float,
        payload: dict[str, Any] | None = None,
        ttl_s: float = 60.0,
    ) -> BlackboardMessage:
        message = BlackboardMessage(kind=kind, source=source, t=t, ttl_s=ttl_s, payload=payload or {})
        self.post(message)
        return message

    def prune(self, t: float) -> None:
        self._messages = [m for m in self._messages if not m.expired(t)]

    def active(self, t: float) -> list[BlackboardMessage]:
        self.prune(t)
        return list(self._messages)

    def of_kind(self, kind: str, t: float) -> list[BlackboardMessage]:
        return [m for m in self.active(t) if m.kind == kind]

    def clear(self) -> None:
        self._messages.clear()
