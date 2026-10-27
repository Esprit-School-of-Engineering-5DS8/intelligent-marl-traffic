"""Shared LLM transport for the three team roles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cotraffic.assistant.llm import LLMUnavailableError
from cotraffic.controllers.llm_team.client import TeamClient, TeamResponse
from cotraffic.controllers.llm_team.schemas import (
    DIRECTIVE_ENVELOPE_SCHEMA,
    EMPTY_ENVELOPE,
    SchemaError,
)

RETRY_NOTE = (
    "\n\nYour previous response was not a valid JSON envelope. "
    "Respond again with ONLY a JSON object: "
    '{"directives": [...], "alerts": [...], "explanation": "..."}'
)
PROMPTS_DIR = Path(__file__).with_name("prompts")


def prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()[:16]


def default_system_prompt(role: str) -> str:
    return (
        f"You are the {role} agent for a signalised traffic network. "
        "The user message contains snapshot.network and snapshot.tls_ids. "
        "Reply with a single JSON envelope: "
        '{"directives": [...], "alerts": [...], "explanation": "..."}. '
        'Doing nothing is always valid: {"directives": []}. '
        "Never explain outside the JSON."
    )


def load_system_prompt(role: str) -> str:
    path = PROMPTS_DIR / f"{role}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return default_system_prompt(role)


@dataclass
class AgentCall:
    role: str
    envelope: dict[str, Any]
    response: TeamResponse | None = None
    error: str | None = None
    prompt_hash: str = ""
    attempts: int = 1
    effort: str = ""
    review: dict[str, Any] | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None


class LLMAgent:
    def __init__(
        self,
        role: str,
        client: TeamClient,
        system_prompt: str | None = None,
        max_retries: int = 1,
        max_tokens: int = 700,
    ) -> None:
        self.role = role
        self.client = client
        self.system_prompt = system_prompt if system_prompt is not None else load_system_prompt(role)
        self.max_retries = int(max_retries)
        self.max_tokens = int(max_tokens)

    def snapshot_for_prompt(self, snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
        return snapshot

    def build_user_message(
        self,
        t: float,
        snapshot: Mapping[str, Any],
        blackboard: Iterable[Any] = (),
    ) -> str:
        return json.dumps(
            {"tick": t, "snapshot": self.snapshot_for_prompt(snapshot)},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def ask(
        self,
        t: float,
        snapshot: Mapping[str, Any],
        blackboard: Iterable[Any] = (),
        effort: str | None = None,
    ) -> AgentCall:
        user = self.build_user_message(t, snapshot, blackboard)
        last_error: str | None = None
        response: TeamResponse | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                response = self.client.complete(
                    self.system_prompt,
                    user,
                    DIRECTIVE_ENVELOPE_SCHEMA,
                    effort=effort,
                    max_tokens=self.max_tokens,
                )
                parsed = response.parsed
                if not isinstance(parsed, Mapping):
                    raise SchemaError(
                        f"envelope must be a JSON object, got {type(parsed).__name__}"
                    )
                return AgentCall(
                    role=self.role,
                    envelope=dict(parsed),
                    response=response,
                    prompt_hash=prompt_hash(self.system_prompt, user),
                    attempts=attempt,
                    effort=effort or "",
                )
            except (LLMUnavailableError, SchemaError, ValueError, TypeError, KeyError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                user = self.build_user_message(t, snapshot, blackboard) + RETRY_NOTE
            except Exception as exc:  # noqa: BLE001 - a failed role must not stop the run
                last_error = f"{type(exc).__name__}: {exc}"
                user = self.build_user_message(t, snapshot, blackboard) + RETRY_NOTE
        return AgentCall(
            role=self.role,
            envelope=dict(EMPTY_ENVELOPE),
            response=response,
            error=last_error,
            prompt_hash=prompt_hash(self.system_prompt, user),
            attempts=self.max_retries + 1,
            effort=effort or "",
        )
