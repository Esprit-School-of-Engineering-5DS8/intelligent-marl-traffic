"""Small JSON-capable LLM providers (Groq and Gemini) with no extra dependency.

The traffic controller needs a strict, short JSON answer. Both APIs are called with
the standard library so that the simulation can run on a laptop without installing
another SDK. Keys are read from the environment and are never written to logs or
result files.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cotraffic.assistant.llm import LLMUnavailableError, validate
from cotraffic.llm.trace import LLMTracer, context_window

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

LOGGER = logging.getLogger("cotraffic.llm")

DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


@dataclass(frozen=True)
class LLMResult:
    """A parsed structured answer and the numbers needed to audit the call."""

    data: dict[str, Any]
    text: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class BaseProvider:
    name = "base"

    def __init__(
        self,
        model: str,
        api_key: str = "",
        timeout_s: float = 30.0,
        attempts: int = 2,
        min_interval_s: float = 0.0,
        tracer: LLMTracer | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout_s = float(timeout_s)
        self.attempts = max(1, int(attempts))
        self.min_interval_s = max(0.0, float(min_interval_s))
        self.tracer = tracer
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        if self.min_interval_s <= 0:
            return
        now = time.monotonic()
        if self._last_request_at is not None:
            wait = self.min_interval_s - (now - self._last_request_at)
            if wait > 0:
                LOGGER.info("wall-clock throttle: waiting %.1fs", wait)
                time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _request(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        self._throttle()
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "kemetra/0.1 (+traffic-control research)",
                **headers,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                detail = error.read().decode("utf-8", errors="replace")[:300]
            except (OSError, ValueError, UnicodeError):
                pass
            message = f"{self.name} HTTP {error.code}"
            if detail:
                message += f": {detail}"
            raise LLMUnavailableError(self._redact(message)) from error
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            raise LLMUnavailableError(self._redact(f"{self.name} request failed: {error}")) from error
        if not isinstance(body, dict):
            raise LLMUnavailableError(f"{self.name} returned a non-object response")
        return body

    def _redact(self, text: str) -> str:
        return text.replace(self.api_key, "***") if self.api_key else text

    def _complete(
        self,
        messages: Sequence[Mapping[str, str]],
        max_tokens: int,
        schema: Mapping[str, Any],
    ) -> tuple[str, int | None, int | None]:
        raise NotImplementedError

    def chat_json(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: Mapping[str, Any],
        max_tokens: int = 700,
    ) -> LLMResult:
        """Call the model until it returns JSON that satisfies ``schema``."""
        schema_message = {
            "role": "system",
            "content": "Reply with a JSON object that validates against this JSON Schema:\n"
            + json.dumps(schema, separators=(",", ":")),
        }
        history = [
            *(dict(message) for message in messages if message.get("role") == "system"),
            schema_message,
            *(dict(message) for message in messages if message.get("role") != "system"),
        ]
        last = ""
        last_error: LLMUnavailableError | None = None
        window = context_window(self.model)
        for attempt in range(1, self.attempts + 1):
            started = time.perf_counter()
            prompt_snapshot = [dict(message) for message in history]
            try:
                text, prompt_tokens, completion_tokens = self._complete(
                    history, max_tokens, schema
                )
            except LLMUnavailableError as error:
                latency_ms = 1000.0 * (time.perf_counter() - started)
                last_error = error
                message = str(error)
                self._trace(
                    {
                        "attempt": attempt,
                        "provider": self.name,
                        "model": self.model,
                        "messages": prompt_snapshot,
                        "schema": dict(schema),
                        "latency_ms": round(latency_ms, 2),
                        "error": self._redact(message),
                        "valid": False,
                        "context_window_tokens": window,
                    }
                )
                if any(code in message for code in ("HTTP 401", "HTTP 403", "HTTP 429")):
                    raise
                last = message
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"Previous request failed ({message}). Retry with a compact, "
                            "valid JSON object matching the schema."
                        ),
                    }
                )
                continue
            latency_ms = 1000.0 * (time.perf_counter() - started)
            last_error = None
            value: dict[str, Any] | None = None
            problems: list[str] = []
            try:
                parsed = json.loads(text)
            except ValueError:
                last = f"not JSON: {text[:80]!r}"
            else:
                if isinstance(parsed, dict):
                    value = parsed
                    problems = validate(value, schema)
                else:
                    problems = ["response is not a JSON object"]
                if not problems:
                    self._trace(
                        {
                            "attempt": attempt,
                            "provider": self.name,
                            "model": self.model,
                            "messages": prompt_snapshot,
                            "schema": dict(schema),
                            "raw_response": text,
                            "parsed": value,
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
                            "latency_ms": round(latency_ms, 2),
                            "context_window_tokens": window,
                            "context_utilisation": round(
                                ((prompt_tokens or 0) + (completion_tokens or 0)) / window, 4
                            ),
                            "valid": True,
                        }
                    )
                    return LLMResult(
                        value,
                        text,
                        latency_ms,
                        prompt_tokens,
                        completion_tokens,
                    )
                last = "; ".join(problems[:3])
            self._trace(
                {
                    "attempt": attempt,
                    "provider": self.name,
                    "model": self.model,
                    "messages": prompt_snapshot,
                    "schema": dict(schema),
                    "raw_response": text,
                    "parsed": value,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
                    "latency_ms": round(latency_ms, 2),
                    "context_window_tokens": window,
                    "context_utilisation": round(
                        ((prompt_tokens or 0) + (completion_tokens or 0)) / window, 4
                    ),
                    "valid": False,
                    "validation_error": last,
                }
            )
            history += [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        f"Invalid answer ({last}). Reply again with JSON matching the "
                        "schema exactly, using only the allowed values."
                    ),
                },
            ]
        if last_error is not None:
            raise last_error
        raise LLMUnavailableError(f"invalid structured output ({last})")

    def _trace(self, event: dict[str, Any]) -> None:
        if self.tracer is not None:
            self.tracer.record(event)


class GroqProvider(BaseProvider):
    name = "groq"

    def _complete(self, messages, max_tokens, schema):
        payload = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "max_tokens": max_tokens,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "traffic_decisions",
                    "strict": True,
                    "schema": dict(schema),
                },
            },
        }
        body = self._request(
            GROQ_URL,
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMUnavailableError("Groq returned an unexpected response") from error
        if not isinstance(text, str) or not text.strip():
            raise LLMUnavailableError("Groq returned an empty response")
        usage = body.get("usage", {})
        return (
            text,
            _as_int(usage.get("prompt_tokens")),
            _as_int(usage.get("completion_tokens")),
        )


class GeminiProvider(BaseProvider):
    name = "gemini"

    def _complete(self, messages, max_tokens, schema):
        system = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        )
        contents = [
            {
                "role": "model" if message.get("role") == "assistant" else "user",
                "parts": [{"text": str(message.get("content", ""))}],
            }
            for message in messages
            if message.get("role") != "system"
        ]
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = GEMINI_URL.format(model=urllib.parse.quote(self.model, safe="")) + "?key=" + urllib.parse.quote(self.api_key)
        body = self._request(url, payload, {})
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMUnavailableError("Gemini returned an unexpected response") from error
        if not isinstance(text, str) or not text.strip():
            raise LLMUnavailableError("Gemini returned an empty response")
        usage = body.get("usageMetadata", {})
        return (
            text,
            _as_int(usage.get("promptTokenCount")),
            _as_int(usage.get("candidatesTokenCount")),
        )


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def make_provider(
    provider: str | None = None,
    model: str | None = None,
    timeout_s: float | None = None,
    attempts: int = 2,
    tracer: LLMTracer | None = None,
) -> BaseProvider:
    """Build the configured provider, or raise ``LLMUnavailableError`` with a clear message."""
    name = (provider or os.environ.get("COTRAFFIC_LLM_PROVIDER") or "groq").lower()
    timeout = float(timeout_s if timeout_s is not None else os.environ.get("COTRAFFIC_LLM_TIMEOUT", "30"))
    min_interval = float(os.environ.get("COTRAFFIC_LLM_MIN_WALL_INTERVAL_S", "0"))
    if name == "groq":
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            raise LLMUnavailableError("GROQ_API_KEY is not configured")
        chosen = model or os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        return GroqProvider(chosen, key, timeout, attempts, min_interval, tracer)
    if name == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        if not key:
            raise LLMUnavailableError("GEMINI_API_KEY is not configured")
        chosen = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        return GeminiProvider(chosen, key, timeout, attempts, min_interval, tracer)
    raise LLMUnavailableError(f"unknown LLM provider {name!r} (expected groq or gemini)")
