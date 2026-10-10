import json

import pytest

from agents.llm.client import (
    CallLogger,
    LLMResponse,
    LLMResponseError,
    MockLLM,
    OpenAICompatClient,
    ReplayLLM,
    parse_json,
)


class CountingClient:
    model = "counting"

    def __init__(self):
        self.calls = 0

    def complete(self, system, user, schema):
        self.calls += 1
        return LLMResponse(parsed={"directives": [], "alerts": [], "explanation": "ok"},
                           raw='{"directives": []}')


def test_mock_default_is_empty_envelope():
    client = MockLLM()
    response = client.complete("s", "u", {})
    assert response.parsed == {"directives": [], "alerts": [], "explanation": "mock: no-op"}
    assert len(client.calls) == 1


def test_mock_responder_used():
    client = MockLLM(lambda system, user, schema: {"directives": [{"tls": "A", "type": "bias"}]})
    assert client.complete("s", "u", {}).parsed["directives"][0]["tls"] == "A"


def test_replay_caches_and_persists(tmp_path):
    cache = tmp_path / "cache.jsonl"
    inner = CountingClient()
    replayed = ReplayLLM(inner, str(cache))
    first = replayed.complete("s", "u", {})
    second = replayed.complete("s", "u", {})
    assert inner.calls == 1
    assert first.parsed == second.parsed
    assert cache.exists()

    reloaded = ReplayLLM(CountingClient(), str(cache))
    assert reloaded.complete("s", "u", {}).parsed == first.parsed
    assert reloaded.inner.calls == 0


def test_parse_json_error_keeps_raw():
    with pytest.raises(LLMResponseError) as info:
        parse_json("not json", "completion")
    assert "invalid JSON" in str(info.value)
    assert info.value.raw == "not json"


def test_call_logger_appends_jsonl(tmp_path):
    path = tmp_path / "decisions.jsonl"
    logger = CallLogger(str(path))
    logger.log({"t": 0, "agent": "operator"})
    logger.log({"t": 30, "agent": "operator"})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["t"] == 30
    CallLogger(None).log({"ignored": True})


def test_openai_compat_requires_config(monkeypatch):
    for var in ("LLM_MODEL", "OPENAI_MODEL", "LLM_BASE_URL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValueError):
        OpenAICompatClient()


def test_openai_compat_payload():
    client = OpenAICompatClient(model="m", base_url="http://localhost:11434/v1/")
    assert client.base_url == "http://localhost:11434/v1"
    payload = client._payload("sys", "user")
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"


def test_prompt_hash_stable():
    from agents.llm.client import prompt_hash
    assert prompt_hash("a", "b") == prompt_hash("a", "b")
    assert prompt_hash("a", "b") != prompt_hash("a", "c")
