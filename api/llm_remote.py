"""Hosted language models for the assistant, as an alternative to the local Ollama model.

The keys stay on the backend (environment variables) and never reach the browser. The
models only word answers whose numbers come from the result files: the same check as for
the local model applies (``cotraffic.assistant.ask.grounded``).

    ANTHROPIC_API_KEY  [COTRAFFIC_CLAUDE_MODEL]   provider "claude"
    OPENAI_API_KEY     [COTRAFFIC_OPENAI_MODEL]   provider "openai"
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

from cotraffic.assistant.llm import LLMUnavailableError, LocalLLM

PROVIDERS = {
    "claude": ("ANTHROPIC_API_KEY", "COTRAFFIC_CLAUDE_MODEL", "claude-sonnet-5-5"),
    "openai": ("OPENAI_API_KEY", "COTRAFFIC_OPENAI_MODEL", "gpt-4o-mini"),
}


class RemoteLLM(LocalLLM):
    """Same interface as :class:`LocalLLM` (``chat``, ``chat_json``, ``status``)."""

    def __init__(self, provider: str) -> None:
        super().__init__()
        key_var, model_var, default = PROVIDERS[provider]
        self.provider = provider
        self.key = os.environ.get(key_var, "")
        self.key_var = key_var
        self.model = os.environ.get(model_var, default)

    def status(self) -> tuple[bool, str]:
        if not self.key:
            return False, f"{self.key_var} is not set on the backend"
        return True, f"{self.model} ({self.provider})"

    def _post(self, url: str, headers: dict[str, str], payload: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
            raise LLMUnavailableError(f"{self.provider}: {err}") from err

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: Mapping[str, Any] | None = None,
        max_tokens: int = 400,
    ) -> str:
        if not self.key:
            raise LLMUnavailableError(f"{self.key_var} is not set")
        msgs = [dict(m) for m in messages]
        if schema is not None:
            msgs.append(
                {
                    "role": "user",
                    "content": "Reply with JSON only, matching this schema: " + json.dumps(schema),
                }
            )
        if self.provider == "claude":
            system = "\n".join(m["content"] for m in msgs if m["role"] == "system")
            reply = self._post(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": 0,
                    "system": system,
                    "messages": [m for m in msgs if m["role"] != "system"],
                },
            )
            parts = reply.get("content") or []
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        else:
            reply = self._post(
                "https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {self.key}"},
                {"model": self.model, "messages": msgs, "max_tokens": max_tokens, "temperature": 0},
            )
            choices = reply.get("choices") or [{}]
            text = choices[0].get("message", {}).get("content") or ""
        if not text.strip():
            raise LLMUnavailableError("empty reply")
        return text


def make_llm(provider: str) -> LocalLLM:
    return RemoteLLM(provider) if provider in PROVIDERS else LocalLLM()
