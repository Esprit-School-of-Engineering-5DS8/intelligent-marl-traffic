"""Team client adapters: provider, mock, replay and call logging."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from cotraffic.assistant.llm import LLMUnavailableError

# CoTraffic: the hosted providers (cotraffic/llm/providers.py of the source branch) are not
# imported; the only real model is the local one (team.py). See PROVENANCE.md.
BaseProvider = LLMResult = Any

CACHE_VERSION = 2


class TeamError(RuntimeError):
    """No usable team response."""


@dataclass
class TeamResponse:
    parsed: Any
    raw: str = ""
    latency_s: float = 0.0
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_cached: int | None = None
    tokens_reasoning: int | None = None
    model: str = ""
    attempts: int = 1


class TeamClient(Protocol):
    model: str

    def complete(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        effort: str | None = None,
        max_tokens: int = 700,
    ) -> TeamResponse:
        ...


class ProviderClient:
    def __init__(self, provider: BaseProvider, name: str = "provider") -> None:
        self.provider = provider
        self.model = provider.model
        self.name = name

    def complete(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        effort: str | None = None,
        max_tokens: int = 700,
    ) -> TeamResponse:
        result: LLMResult = self.provider.chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            schema,
            max_tokens=max_tokens,
            effort=effort,
        )
        return TeamResponse(
            parsed=result.data,
            raw=result.text,
            latency_s=result.latency_ms / 1000.0,
            tokens_in=result.prompt_tokens,
            tokens_out=result.completion_tokens,
            tokens_cached=result.cached_tokens,
            tokens_reasoning=result.reasoning_tokens,
            model=result.model or self.model,
            attempts=result.attempts,
        )


class MockClient:
    model = "mock"
    name = "mock"

    def __init__(
        self,
        responder: Callable[[str, str, Mapping[str, Any]], Any] | None = None,
    ) -> None:
        self.responder = responder or (
            lambda system, user, schema: {
                "directives": [],
                "alerts": [],
                "explanation": "mock: no-op",
            }
        )
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        effort: str | None = None,
        max_tokens: int = 700,
    ) -> TeamResponse:
        parsed = self.responder(system, user, schema)
        self.calls.append(
            {"system": system, "user": user, "effort": effort or "", "parsed": parsed}
        )
        return TeamResponse(parsed=parsed, raw=json.dumps(parsed, sort_keys=True), model=self.model)


class ReplayClient:
    """Read-through JSONL cache; strict mode never calls the inner client."""

    def __init__(
        self,
        inner: TeamClient | None,
        cache_path: str,
        strict: bool = False,
        name: str = "replay",
        model: str | None = None,
    ) -> None:
        self.inner = inner
        self.cache_path = cache_path
        self.strict = strict
        self.name = name
        self.model = getattr(inner, "model", "") or model or "replay"
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._load()

    def _key(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        effort: str,
        max_tokens: int,
    ) -> str:
        payload = json.dumps(
            {
                "version": CACHE_VERSION,
                "model": self.model,
                "effort": effort,
                "max_tokens": max_tokens,
                "system": system,
                "user": user,
                "schema": schema,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load(self) -> None:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    self._cache[record["key"]] = record
        except (OSError, ValueError, KeyError):
            self._cache = {}

    def complete(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        effort: str | None = None,
        max_tokens: int = 700,
    ) -> TeamResponse:
        effective = (effort or "") if effort is not None else ""
        key = self._key(system, user, schema, effective, max_tokens)
        with self._lock:
            record = self._cache.get(key)
        if record is not None:
            return TeamResponse(**record["response"])
        if self.strict:
            raise TeamError(f"replay cache miss (strict mode): {self.cache_path}")
        if self.inner is None:
            raise TeamError("replay cache miss and no inner client configured")
        started = time.perf_counter()
        response = self.inner.complete(
            system, user, schema, effort=effort, max_tokens=max_tokens
        )
        if not response.latency_s:
            response.latency_s = time.perf_counter() - started
        record = {"key": key, "response": asdict(response)}
        with self._lock:
            self._cache[key] = record
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)), exist_ok=True)
                with open(self.cache_path, "a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
                        + "\n"
                    )
            except OSError:
                pass
        return response


class CallLogger:
    def __init__(self, path: str | None = None) -> None:
        self.path = path

    def log(self, record: Mapping[str, Any]) -> None:
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(dict(record), sort_keys=True, ensure_ascii=False, default=str)
                    + "\n"
                )
        except OSError:
            pass


def make_team_client(
    provider_name: str,
    model: str | None,
    timeout_s: float,
    attempts: int,
    backend: str = "opencode",
    cache_path: str = "",
    mock_responder: Callable[[str, str, Mapping[str, Any]], Any] | None = None,
) -> TeamClient:
    backend = (backend or "opencode").lower()
    if backend == "mock":
        return MockClient(mock_responder)
    if backend == "replay":
        try:
            inner = _provider_client(provider_name, model, timeout_s, attempts)
        except LLMUnavailableError:
            inner = None
        return ReplayClient(inner, cache_path, strict=True, name="replay", model=model)
    inner = _provider_client(provider_name, model, timeout_s, attempts)
    if not cache_path:
        return inner
    return ReplayClient(inner, cache_path, strict=False, name=backend, model=model)


def _provider_client(
    provider_name: str, model: str | None, timeout_s: float, attempts: int
) -> TeamClient:
    # CoTraffic: no hosted provider (no data leaves the machine, no API key)
    raise LLMUnavailableError(
        f"hosted provider {provider_name!r} is not available in CoTraffic: "
        "use the mock backend or the local model (team_rules, team_qwen)"
    )
