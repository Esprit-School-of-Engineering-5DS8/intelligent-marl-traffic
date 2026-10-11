"""
agents/llm/client.py
LLM access layer (plan section 4.6): one protocol, several backends.

All agent code goes through `LLMClient.complete`. No vendor SDKs, no TraCI in
this module. Backends:

- `MockLLM`          deterministic offline stand-in; the whole pipeline runs
                     and is testable without a model.
- `ReplayLLM`        read-through cache keyed by hash(model, system, user);
                     reruns of a recorded seed are free and bit-identical.
                     `strict=True` raises on a cache miss instead of calling
                     the backend, so replay plots cannot spend tokens.
- `OpenAICompatClient` any OpenAI-style endpoint (hosted API, Ollama, vLLM,
                     LM Studio, opencode-go). Base URL/model/key come from
                     arguments, `LLM_*`/`OPENAI_*` environment variables, or a
                     generic JSON/text key file (`LLM_API_KEY_FILE` +
                     `LLM_API_KEY_JSON`), never committed.

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

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_USER_AGENT = "marl-traffic/0.1"


class LLMError(RuntimeError):
    """Transport, timeout or backend failure."""


class LLMHTTPError(LLMError):
    """The backend answered with an HTTP error status."""

    def __init__(self, message: str, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


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
    tokens_cached: Optional[int] = None
    model: str = ""


class LLMClient(Protocol):
    def complete(self, system: str, user: str, schema: Dict[str, Any],
                 effort: Optional[str] = None) -> LLMResponse:
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


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_json_dict(name: str) -> Dict[str, str]:
    """Parse a JSON object env var into a string dict; invalid input is ignored."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def _usage_counts(usage: Dict[str, Any]):
    """(tokens_in, tokens_out, tokens_cached) from an OpenAI-style usage block."""
    tokens_in = usage.get("prompt_tokens")
    tokens_out = usage.get("completion_tokens")
    cached = usage.get("prompt_cache_hit_tokens")
    if not cached:
        details = usage.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens")
    return tokens_in, tokens_out, cached


def key_from_file(path: str, json_path: str = "") -> str:
    """
    Read an API key from a generic key file.

    - plain-text file: the stripped content is the key;
    - JSON file: `json_path` is the dotted path to the key (e.g.
      `opencode-go.key`); with no path, a top-level `"key"` entry is used.
    Missing files, bad JSON or missing paths return "".
    """
    if not path:
        return ""
    resolved = os.path.expanduser(path)
    if not os.path.isfile(resolved):
        return ""
    try:
        with open(resolved, "r", encoding="utf-8") as handle:
            text = handle.read().strip()
    except OSError:
        return ""
    if not text:
        return ""
    try:
        data: Any = json.loads(text)
    except ValueError:
        return text
    node: Any = data
    path_parts = json_path.split(".") if json_path else ["key"]
    for part in path_parts:
        if not isinstance(node, dict) or part not in node:
            return ""
        node = node[part]
    return node if isinstance(node, str) else ""


class MockLLM:
    """Deterministic, offline LLM stand-in.

    The default responder does nothing (`{"directives": []}`); pass a
    `responder(system, user, schema) -> dict` to script behavior in tests.
    """

    model = "mock"

    def __init__(self, responder: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None):
        self.responder = responder or (lambda system, user, schema: {"directives": [], "alerts": [], "explanation": "mock: no-op"})
        self.calls: List[Dict[str, Any]] = []

    def complete(self, system: str, user: str, schema: Dict[str, Any],
                 effort: Optional[str] = None) -> LLMResponse:
        parsed = self.responder(system, user, schema)
        self.calls.append({"system": system, "user": user, "effort": effort or "",
                           "parsed": parsed})
        return LLMResponse(parsed=parsed, raw=json.dumps(parsed, sort_keys=True), model=self.model)


class ReplayLLM:
    """Response cache: record once, replay for free and bit-identically."""

    def __init__(self, inner: LLMClient, cache_path: str, strict: bool = False):
        self.inner = inner
        self.cache_path = cache_path
        self.strict = strict
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load()

    @property
    def model(self) -> str:
        return getattr(self.inner, "model", type(self.inner).__name__)

    def _key(self, system: str, user: str, effort: str) -> str:
        payload = json.dumps({"model": self.model, "effort": effort,
                              "system": system, "user": user},
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

    def complete(self, system: str, user: str, schema: Dict[str, Any],
                 effort: Optional[str] = None) -> LLMResponse:
        # The key must reflect what the inner client will actually send, so an
        # empty per-call effort resolves to the inner default here too.
        effective = (effort or getattr(self.inner, "effort", "") or "")
        key = self._key(system, user, effective)
        record = self._cache.get(key)
        if record is not None:
            return LLMResponse(parsed=record["parsed"], raw=record.get("raw", ""),
                               model=record.get("model", self.model))
        if self.strict:
            raise LLMError(f"replay cache miss (strict mode): {self.cache_path}")
        response = self.inner.complete(system, user, schema, effort=effort)
        record = {"key": key, "model": self.model, "effort": effective,
                  "parsed": response.parsed, "raw": response.raw}
        self._cache[key] = record
        os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)), exist_ok=True)
        with open(self.cache_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        return response


class OpenAICompatClient:
    """Any OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, timeout_s: Optional[float] = None,
                 json_mode: bool = True, api_key_file: Optional[str] = None,
                 api_key_json: Optional[str] = None,
                 user_agent: Optional[str] = None,
                 extra_headers: Optional[Dict[str, str]] = None,
                 effort: Optional[str] = None):
        self.model = model or os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL") or ""
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL")
                         or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or key_from_file(
                api_key_file or os.environ.get("LLM_API_KEY_FILE", ""),
                api_key_json or os.environ.get("LLM_API_KEY_JSON", ""),
            )
        )
        self.timeout_s = timeout_s if timeout_s is not None else _env_float("LLM_TIMEOUT_S", DEFAULT_TIMEOUT_S)
        self.json_mode = json_mode
        self.user_agent = (user_agent or os.environ.get("LLM_USER_AGENT") or DEFAULT_USER_AGENT)
        self.extra_headers = dict(extra_headers) if extra_headers is not None else _env_json_dict("LLM_EXTRA_HEADERS")
        self.effort = (effort if effort is not None else os.environ.get("LLM_REASONING_EFFORT", "")).strip()
        if not self.model or not self.base_url:
            raise ValueError(
                "OpenAICompatClient requires a model and a base URL "
                "(arguments or LLM_MODEL/LLM_BASE_URL environment variables)")

    def _payload(self, system: str, user: str, effort: str = "") -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if effort:
            payload["reasoning_effort"] = effort
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _request(self, system: str, user: str, effort: str) -> LLMResponse:
        headers = {"Content-Type": "application/json", "User-Agent": self.user_agent}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(self._payload(system, user, effort)).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            raise LLMHTTPError(f"HTTP {exc.code}: {detail}", status=exc.code,
                               body=detail) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise LLMError(f"request failed: {exc}") from exc
        latency = time.perf_counter() - started

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(f"unexpected response shape ({exc})",
                                   raw=json.dumps(body)) from exc
        tokens_in, tokens_out, tokens_cached = _usage_counts(body.get("usage") or {})
        return LLMResponse(
            parsed=parse_json(content, "chat completion"),
            raw=content,
            latency_s=latency,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cached=tokens_cached,
            model=body.get("model", self.model),
        )

    def complete(self, system: str, user: str, schema: Dict[str, Any],
                 effort: Optional[str] = None) -> LLMResponse:
        # A falsy per-call effort ("" or None) means "use the client default";
        # only a non-empty string overrides it.
        effective = (effort or self.effort) or ""
        try:
            return self._request(system, user, effective)
        except LLMHTTPError as exc:
            # Some gateways reject reasoning_effort; retry once without it.
            if effective and exc.status == 400:
                return self._request(system, user, "")
            raise


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
