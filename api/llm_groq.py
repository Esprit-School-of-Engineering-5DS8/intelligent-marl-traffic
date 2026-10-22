"""Small Groq adapter used by the backend assistant.

The API key stays on the server. The browser only talks to our own API.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

from cotraffic.assistant.llm import LLMUnavailableError, validate

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqError(RuntimeError):
    """Raised when Groq is unavailable or returns an invalid response."""


class GroqClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    def status(self) -> dict[str, Any]:
        return {
            "available": bool(self.api_key),
            "provider": "groq",
            "model": self.model if self.api_key else None,
            "message": "ready" if self.api_key else "GROQ_API_KEY is not configured",
        }

    def chat(self, messages: Sequence[Mapping[str, str]], max_tokens: int = 600) -> str:
        if not self.api_key:
            raise LLMUnavailableError("GROQ_API_KEY is not configured on the backend")
        payload = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            GROQ_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            raise LLMUnavailableError(f"Groq request failed: {error}") from error
        text = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not isinstance(text, str) or not text.strip():
            raise LLMUnavailableError("Groq returned an empty response")
        return text

    def chat_json(self, messages: Sequence[Mapping[str, str]], schema: Mapping[str, Any], attempts: int = 2) -> dict:
        history = list(messages)
        last = ""
        for _ in range(attempts):
            text = self.chat(history, max_tokens=800)
            try:
                value = json.loads(text)
            except ValueError:
                last = "response was not valid JSON"
            else:
                problems = validate(value, schema)
                if not problems:
                    return value
                last = "; ".join(problems[:3])
            history += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"Invalid answer ({last}). Reply with JSON matching the schema exactly."},
            ]
        raise LLMUnavailableError(f"invalid structured output ({last})")
