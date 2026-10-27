"""Small JSON-capable LLM providers (OpenCode Go, Groq and Gemini) with no extra dependency.

The traffic controller needs a strict, short JSON answer. Both APIs are called with
the standard library so that the simulation can run on a laptop without installing
another SDK. Keys are read from the environment and are never written to logs or
result files.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cotraffic.assistant.llm import LLMUnavailableError, validate

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

LOGGER = logging.getLogger("cotraffic.llm")

DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OPENCODE_MODEL = "deepseek-v4.1-flash"
DEFAULT_OPENCODE_BASE_URL = "https://opencode.ai/zen/go/v1"


@dataclass(frozen=True)
class LLMResult:
    """A parsed structured answer and the numbers needed to audit the call."""

    data: dict[str, Any]
    text: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    model: str = ""
    attempts: int = 1


class BaseProvider:
    name = "base"

    def __init__(
        self,
        model: str,
        api_key: str = "",
        timeout_s: float = 30.0,
        attempts: int = 2,
        min_interval_s: float = 0.0,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout_s = float(timeout_s)
        self.attempts = max(1, int(attempts))
        self.min_interval_s = max(0.0, float(min_interval_s))
        self._local = threading.local()
        self._last_request_at: float | None = None

    @property
    def reasoning_effort(self) -> str:
        return getattr(self._local, "reasoning_effort", "")

    @reasoning_effort.setter
    def reasoning_effort(self, value: str | None) -> None:
        self._local.reasoning_effort = value or ""

    @property
    def _last_usage(self) -> dict[str, int | None]:
        return getattr(self._local, "last_usage", {})

    @_last_usage.setter
    def _last_usage(self, value: dict[str, int | None]) -> None:
        self._local.last_usage = value

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
        effort: str | None = None,
    ) -> LLMResult:
        """Call the model until it returns JSON that satisfies ``schema``."""
        if effort is not None:
            self.reasoning_effort = effort
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
        for attempt in range(1, self.attempts + 1):
            started = time.perf_counter()
            self._last_usage = {}
            try:
                text, prompt_tokens, completion_tokens = self._complete(
                    history, max_tokens, schema
                )
            except LLMUnavailableError as error:
                last_error = error
                message = str(error)
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
            try:
                value = json.loads(text)
            except ValueError:
                last = f"not JSON: {text[:80]!r}"
            else:
                problems = validate(value, schema)
                if not problems:
                    return LLMResult(
                        value,
                        text,
                        latency_ms,
                        prompt_tokens,
                        completion_tokens,
                        self._last_usage.get("cached"),
                        self._last_usage.get("reasoning"),
                        self.model,
                        attempt,
                    )
                last = "; ".join(problems[:3])
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


class OpenCodeGoProvider(BaseProvider):
    """OpenCode Go's OpenAI-compatible endpoint."""

    name = "opencode"

    def __init__(
        self,
        model: str,
        api_key: str = "",
        timeout_s: float = 30.0,
        attempts: int = 2,
        min_interval_s: float = 0.0,
        base_url: str | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(model, api_key, timeout_s, attempts, min_interval_s)
        self.base_url = (
            base_url
            or os.environ.get("COTRAFFIC_LLM_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or DEFAULT_OPENCODE_BASE_URL
        ).rstrip("/")
        self.extra_headers = dict(
            extra_headers if extra_headers is not None else _env_headers()
        )

    def _complete(self, messages, max_tokens, schema):
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "max_tokens": max_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        headers = {"Authorization": f"Bearer {self.api_key}", **self.extra_headers}
        try:
            body = self._request(f"{self.base_url}/chat/completions", payload, headers)
        except LLMUnavailableError as error:
            if self.reasoning_effort and "HTTP 400" in str(error):
                payload.pop("reasoning_effort", None)
                body = self._request(f"{self.base_url}/chat/completions", payload, headers)
            else:
                raise
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMUnavailableError("OpenCode Go returned an unexpected response") from error
        if not isinstance(text, str) or not text.strip():
            raise LLMUnavailableError("OpenCode Go returned an empty response")
        usage = body.get("usage") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        self._last_usage = {
            "cached": _as_int(
                prompt_details.get("cached_tokens") or usage.get("prompt_cache_hit_tokens")
            ),
            "reasoning": _as_int(completion_details.get("reasoning_tokens")),
        }
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


def _env_headers() -> dict[str, str]:
    raw = (
        os.environ.get("COTRAFFIC_LLM_EXTRA_HEADERS")
        or os.environ.get("LLM_EXTRA_HEADERS")
        or ""
    ).strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def opencode_api_key() -> str:
    return (
        os.environ.get("COTRAFFIC_LLM_API_KEY")
        or os.environ.get("OPENCODE_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or ""
    )


def provider_available(provider: str) -> tuple[bool, str | None]:
    name = (provider or "groq").lower()
    if name in ("opencode", "opencode-go"):
        return (True, None) if opencode_api_key() else (False, "COTRAFFIC_LLM_API_KEY is not configured")
    if name == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        return (True, None) if key else (False, "GEMINI_API_KEY is not configured")
    if name == "groq":
        return (True, None) if os.environ.get("GROQ_API_KEY") else (False, "GROQ_API_KEY is not configured")
    return False, f"unknown LLM provider {name!r}"


def make_provider(
    provider: str | None = None,
    model: str | None = None,
    timeout_s: float | None = None,
    attempts: int = 2,
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
        return GroqProvider(chosen, key, timeout, attempts, min_interval)
    if name == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        if not key:
            raise LLMUnavailableError("GEMINI_API_KEY is not configured")
        chosen = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        return GeminiProvider(chosen, key, timeout, attempts, min_interval)
    if name in ("opencode", "opencode-go"):
        key = opencode_api_key()
        if not key:
            raise LLMUnavailableError("COTRAFFIC_LLM_API_KEY is not configured")
        chosen = (
            model
            or os.environ.get("COTRAFFIC_LLM_MODEL")
            or os.environ.get("LLM_MODEL")
            or DEFAULT_OPENCODE_MODEL
        )
        return OpenCodeGoProvider(chosen, key, timeout, attempts, min_interval)
    raise LLMUnavailableError(
        f"unknown LLM provider {name!r} (expected opencode, groq or gemini)"
    )
