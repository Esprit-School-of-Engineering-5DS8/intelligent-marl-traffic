"""Tests for the stdlib Groq/Gemini providers and their schema retry loop."""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import pytest

from cotraffic.assistant.llm import LLMUnavailableError
from cotraffic.llm.providers import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    BaseProvider,
    GeminiProvider,
    GroqProvider,
    make_provider,
)

SCHEMA = {
    "type": "object",
    "required": ["decisions"],
    "properties": {"decisions": {"type": "array"}},
}


class ScriptedProvider(BaseProvider):
    name = "scripted"

    def __init__(self, answers):
        super().__init__("fake-model", attempts=len(answers))
        self.answers = list(answers)
        self.seen = []

    def _complete(self, messages, max_tokens, schema):
        self.seen.append([dict(message) for message in messages])
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer, 7, 3


def test_schema_is_sent_and_valid_json_is_returned():
    provider = ScriptedProvider(['{"decisions": []}'])
    result = provider.chat_json([{"role": "user", "content": "state"}], SCHEMA)

    assert result.data == {"decisions": []}
    assert result.prompt_tokens == 7
    assert result.completion_tokens == 3
    assert "JSON Schema" in provider.seen[0][0]["content"]
    assert provider.seen[0][-1] == {"role": "user", "content": "state"}


def test_invalid_json_is_retried_with_the_error():
    provider = ScriptedProvider(["not json", '{"decisions": []}'])
    result = provider.chat_json([{"role": "user", "content": "state"}], SCHEMA)

    assert result.data == {"decisions": []}
    assert len(provider.seen) == 2
    assert "Invalid answer" in provider.seen[1][-1]["content"]
    assert "not JSON" in provider.seen[1][-1]["content"]


def test_wall_clock_throttle_waits_between_requests(monkeypatch):
    provider = ScriptedProvider(['{"decisions": []}'])
    provider.min_interval_s = 10.0
    clock = iter([0.0, 0.0, 2.0, 10.0])
    slept: list[float] = []
    monkeypatch.setattr("cotraffic.llm.providers.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("cotraffic.llm.providers.time.sleep", slept.append)

    provider._throttle()
    provider._throttle()

    assert slept == [8.0]


def test_transient_provider_error_is_retried():
    provider = ScriptedProvider(
        [LLMUnavailableError("groq HTTP 500: temporary"), '{"decisions": []}']
    )
    result = provider.chat_json([{"role": "user", "content": "state"}], SCHEMA)

    assert result.data == {"decisions": []}
    assert len(provider.seen) == 2
    assert "Previous request failed" in provider.seen[1][-1]["content"]


def test_auth_error_is_not_retried():
    provider = ScriptedProvider([LLMUnavailableError("groq HTTP 403: forbidden")])
    with pytest.raises(LLMUnavailableError, match="403"):
        provider.chat_json([{"role": "user", "content": "state"}], SCHEMA)

    assert len(provider.seen) == 1


def test_invalid_json_exhausts_attempts():
    provider = ScriptedProvider(['{"wrong": []}', "still not json"])
    with pytest.raises(LLMUnavailableError, match="invalid structured output"):
        provider.chat_json([{"role": "user", "content": "state"}], SCHEMA)


def test_make_provider_requires_keys_and_chooses_models(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    with pytest.raises(LLMUnavailableError, match="GROQ_API_KEY"):
        make_provider("groq")
    with pytest.raises(LLMUnavailableError, match="GEMINI_API_KEY"):
        make_provider("gemini")
    with pytest.raises(LLMUnavailableError, match="unknown"):
        make_provider("other")

    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    groq = make_provider("groq")
    assert isinstance(groq, GroqProvider)
    assert groq.model == DEFAULT_GROQ_MODEL

    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")
    gemini = make_provider("gemini")
    assert isinstance(gemini, GeminiProvider)
    assert gemini.model == DEFAULT_GEMINI_MODEL


def test_groq_parses_usage_and_sends_auth(monkeypatch):
    provider = GroqProvider("model-x", "gsk-secret")

    def fake_request(url, payload, headers):
        assert payload["model"] == "model-x"
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["response_format"]["json_schema"]["schema"] == SCHEMA
        assert headers["Authorization"] == "Bearer gsk-secret"
        return {
            "choices": [{"message": {"content": '{"decisions": []}'}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4},
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    result = provider.chat_json([{"role": "user", "content": "state"}], SCHEMA)

    assert result.data == {"decisions": []}
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 4


def test_gemini_maps_roles_and_system_instruction(monkeypatch):
    provider = GeminiProvider("gemini-x", "gm-secret")
    captured = {}

    def fake_request(url, payload, headers):
        captured["url"] = url
        captured["payload"] = payload
        return {
            "candidates": [{"content": {"parts": [{"text": '{"decisions": []}'}]}}],
            "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 2},
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    messages = [
        {"role": "system", "content": "control the lights"},
        {"role": "assistant", "content": "previous"},
        {"role": "user", "content": "state"},
    ]
    result = provider.chat_json(messages, SCHEMA)

    assert result.data == {"decisions": []}
    assert result.prompt_tokens == 9
    assert "gm-secret" in captured["url"]
    payload = captured["payload"]
    assert payload["systemInstruction"]["parts"][0]["text"].startswith("control the lights")
    assert "JSON Schema" in payload["systemInstruction"]["parts"][0]["text"]
    assert [part["role"] for part in payload["contents"]] == ["model", "user"]
    assert payload["contents"][-1]["parts"][0]["text"] == "state"


def test_keys_are_redacted_from_errors():
    provider = GroqProvider("model-x", "gsk-secret")
    assert "gsk-secret" not in provider._redact("failed gsk-secret")
