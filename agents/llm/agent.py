"""
agents/llm/agent.py
Generic LLM agent: builds the request, calls the client, retries once on
invalid output, then falls back to an empty envelope (plan sections 4.3, 4.6).

Role-specific prompts and behavior (operator, emergency, pedestrian) land in
Phase 3/4; this module provides the transport and failure handling they share.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

from agents.llm.client import LLMClient, LLMError, LLMResponse, prompt_hash
from agents.llm.schemas import DIRECTIVE_ENVELOPE_SCHEMA, EMPTY_ENVELOPE, SchemaError

RETRY_NOTE = (
    "\n\nYour previous response was not a valid JSON envelope. "
    "Respond again with ONLY a JSON object: "
    '{"directives": [...], "alerts": [...], "explanation": "..."}'
)

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


def default_system_prompt(role: str) -> str:
    return (
        f"You are the {role} agent for a 3x3 grid of traffic signals. Each tick you "
        "receive a JSON snapshot. Reply with a single JSON envelope:\n"
        '{"directives": [...], "alerts": [...], "explanation": "..."}\n'
        "Doing nothing is always valid: {\"directives\": []}. "
        "Never explain outside the JSON."
    )


def load_system_prompt(role: str) -> str:
    """Role prompt from agents/llm/prompts/<role>.md when present (Phase 3)."""
    path = os.path.join(PROMPTS_DIR, f"{role}.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    return default_system_prompt(role)


@dataclass
class AgentCall:
    role: str
    envelope: Dict[str, Any]
    response: Optional[LLMResponse] = None
    error: Optional[str] = None
    prompt_hash: str = ""
    attempts: int = 1
    effort: str = ""
    # Role-specific reviewer notes (e.g. the Emergency agent's corridor checks
    # and rule fallback); surfaced in the decision log when set.
    review: Optional[Dict[str, Any]] = None

    @property
    def failed(self) -> bool:
        return self.error is not None


class LLMAgent:
    def __init__(self, role: str, client: LLMClient, system_prompt: Optional[str] = None,
                 max_retries: int = 1):
        self.role = role
        self.client = client
        self.system_prompt = system_prompt if system_prompt is not None else load_system_prompt(role)
        self.max_retries = int(max_retries)

    def build_user_message(self, t: float, snapshot: Mapping[str, Any],
                           blackboard: Iterable[Any] = ()) -> str:
        context: Dict[str, Any] = {"blackboard": []}
        for message in blackboard:
            context["blackboard"].append(
                message.to_dict() if hasattr(message, "to_dict") else dict(message))
        # sort_keys: canonical JSON regardless of dict insertion order, so the
        # same state always yields the same prompt (record/replay keys, and
        # provider-side prefix caching, depend on byte stability).
        return json.dumps({"tick": t, "snapshot": snapshot, "context": context},
                          ensure_ascii=False, sort_keys=True, default=str)

    def ask(self, t: float, snapshot: Mapping[str, Any],
            blackboard: Iterable[Any] = (),
            effort: Optional[str] = None) -> AgentCall:
        user = self.build_user_message(t, snapshot, blackboard)
        last_error: Optional[str] = None
        response: Optional[LLMResponse] = None

        for attempt in range(1, self.max_retries + 2):
            try:
                response = self.client.complete(self.system_prompt, user,
                                                DIRECTIVE_ENVELOPE_SCHEMA, effort=effort)
                parsed = response.parsed
                if not isinstance(parsed, Mapping):
                    raise SchemaError(f"envelope must be a JSON object, got {type(parsed).__name__}")
                return AgentCall(
                    role=self.role,
                    envelope=dict(parsed),
                    response=response,
                    prompt_hash=prompt_hash(self.system_prompt, user),
                    attempts=attempt,
                    effort=effort or "",
                )
            except (LLMError, SchemaError) as exc:
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
