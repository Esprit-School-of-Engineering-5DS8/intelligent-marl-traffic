"""Operator role: bias and hold directives for routine traffic."""

from __future__ import annotations

from cotraffic.controllers.llm_team.agent import LLMAgent


class OperatorAgent(LLMAgent):
    def __init__(self, client, system_prompt: str | None = None, max_retries: int = 1,
                 max_tokens: int = 300) -> None:
        super().__init__(
            "operator", client, system_prompt, max_retries, max_tokens=max_tokens
        )
