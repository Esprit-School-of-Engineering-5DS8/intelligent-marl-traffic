"""
agents/llm/client.py
LLM access layer (plan section 4.6): one protocol, several backends.

All agent code goes through `LLMClient.complete`. No vendor SDKs, no TraCI in
this module. Backends:

- `MockLLM`          deterministic offline stand-in; the whole pipeline runs
                     and is testable without a model.
- `ReplayLLM`        read-through cache keyed by hash(model, system, user);
                     reruns of a recorded seed are free and bit-identical.
- `OpenAICompatClient` any OpenAI-style endpoint (hosted API, Ollama, vLLM,
                     LM Studio). Base URL/model/key come from arguments or
                     `LLM_*`/`OPENAI_*` environment variables, never committed.

`CallLogger` appends one JSONL record per call: t, agent, prompt hash, tokens,
latency, raw response, parsed response, arbiter outcome.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol

DEFAULT_TIMEOUT_S = 20.0


class LLMError(RuntimeError):
    """Transport, timeout or backend failure."""


class LLMResponseError(LLMError):
    """The backend answered but the payload was not usable JSON."""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


@dataclass
class LLMResponse:
    parsed: Any
    raw: str = ""
    latency_s: float = 0.0
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    model: str = ""


class LLMClient(Protocol):
    def complete(self, system: str, user: str, schema: Dict[str, Any]) -> LLMResponse:
        ...


def prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()[:16]


def parse_json(text: str, source: str = "response") -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise LLMResponseError(f"{source}: invalid JSON ({exc})", raw=text or "") from exc


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


class MockLLM:
    """Deterministic, offline LLM stand-in.

    The default responder does nothing (`{"directives": []}`); pass a
    `responder(system, user, schema) -> dict` to script behavior in tests.
    """

    model = "mock"

    def __init__(self, responder: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None):
        self.responder = responder or (lambda system, user, schema: {"directives": [], "alerts": [], "explanation": "mock: no-op"})
        self.calls: List[Dict[str, Any]] = []

    def complete(self, system: str, user: str, schema: Dict[str, Any]) -> LLMResponse:
        parsed = self.responder(system, user, schema)
        self.calls.append({"system": system, "user": user, "parsed": parsed})
        return LLMResponse(parsed=parsed, raw=json.dumps(parsed, sort_keys=True), model=self.model)


class ReplayLLM:
    """Response cache: record once, replay for free and bit-identically."""

    def __init__(self, inner: LLMClient, cache_path: str):
        self.inner = inner
        self.cache_path = cache_path
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load()

    @property
    def model(self) -> str:
        return getattr(self.inner, "model", type(self.inner).__name__)

    def _key(self, system: str, user: str) -> str:
        payload = json.dumps({"model": self.model, "system": system, "user": user},
                             sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load(self) -> None:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return
        with open(self.cache_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                self._cache[record["key"]] = record

    def complete(self, system: str, user: str, schema: Dict[str, Any]) -> LLMResponse:
        key = self._key(system, user)
        record = self._cache.get(key)
        if record is not None:
            return LLMResponse(parsed=record["parsed"], raw=record.get("raw", ""),
                               model=record.get("model", self.model))
        response = self.inner.complete(system, user, schema)
        record = {"key": key, "model": self.model, "parsed": response.parsed,
                  "raw": response.raw}
        self._cache[key] = record
        os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)), exist_ok=True)
        with open(self.cache_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        return response


class OpenAICompatClient:
    """Any OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, timeout_s: float = DEFAULT_TIMEOUT_S,
                 json_mode: bool = True):
        self.model = model or os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL") or ""
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL")
                         or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self.timeout_s = timeout_s
        self.json_mode = json_mode
        if not self.model or not self.base_url:
            raise ValueError(
                "OpenAICompatClient requires a model and a base URL "
                "(arguments or LLM_MODEL/LLM_BASE_URL environment variables)")

    def _payload(self, system: str, user: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def complete(self, system: str, user: str, schema: Dict[str, Any]) -> LLMResponse:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(self._payload(system, user)).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise LLMError(f"request failed: {exc}") from exc
        latency = time.perf_counter() - started

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(f"unexpected response shape ({exc})",
                                   raw=json.dumps(body)) from exc
        usage = body.get("usage") or {}
        return LLMResponse(
            parsed=parse_json(content, "chat completion"),
            raw=content,
            latency_s=latency,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            model=body.get("model", self.model),
        )


class CallLogger:
    """Appends one JSONL record per LLM call and arbiter outcome."""

    def __init__(self, path: Optional[str] = None):
        self.path = path

    def log(self, record: Dict[str, Any]) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, default=str) + "\n")
