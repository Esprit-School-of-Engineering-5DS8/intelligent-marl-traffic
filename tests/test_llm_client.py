import io
import json
import urllib.error
import urllib.request

import pytest

from agents.llm.client import (
    CallLogger,
    LLMError,
    LLMHTTPError,
    LLMResponse,
    LLMResponseError,
    MockLLM,
    OpenAICompatClient,
    ReplayLLM,
    key_from_file,
    parse_json,
)


class CountingClient:
    model = "counting"

    def __init__(self):
        self.calls = 0

    def complete(self, system, user, schema, effort=None):
        self.calls += 1
        return LLMResponse(parsed={"directives": [], "alerts": [], "explanation": "ok"},
                           raw='{"directives": []}')


class FakeResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _chat_body(content: str, usage: dict | None = None) -> dict:
    return {
        "model": "m",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": usage or {},
    }


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


def _clear_llm_env(monkeypatch):
    for var in ("LLM_MODEL", "OPENAI_MODEL", "LLM_BASE_URL", "OPENAI_BASE_URL",
                "LLM_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY_FILE",
                "LLM_API_KEY_JSON", "LLM_TIMEOUT_S", "LLM_REASONING_EFFORT"):
        monkeypatch.delenv(var, raising=False)


def test_openai_compat_requires_config(monkeypatch):
    _clear_llm_env(monkeypatch)
    with pytest.raises(ValueError):
        OpenAICompatClient()


def test_key_from_file_json_path(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text('{"opencode-go": {"type": "api", "key": "secret-key"}}', encoding="utf-8")
    assert key_from_file(str(path), "opencode-go.key") == "secret-key"
    assert key_from_file(str(path), "missing.key") == ""
    assert key_from_file(str(path), "") == ""


def test_key_from_file_top_level_key(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text('{"key": "flat-key"}', encoding="utf-8")
    assert key_from_file(str(path)) == "flat-key"


def test_key_from_file_plain_text(tmp_path):
    path = tmp_path / "key.txt"
    path.write_text("  plain-key\n", encoding="utf-8")
    assert key_from_file(str(path)) == "plain-key"
    assert key_from_file(str(tmp_path / "missing")) == ""


def test_openai_compat_uses_key_file(tmp_path, monkeypatch):
    _clear_llm_env(monkeypatch)
    path = tmp_path / "auth.json"
    path.write_text('{"opencode-go": {"key": "file-key"}}', encoding="utf-8")
    client = OpenAICompatClient(model="m", base_url="http://x/v1",
                                api_key_file=str(path), api_key_json="opencode-go.key")
    assert client.api_key == "file-key"


def test_openai_compat_env_key_beats_file(tmp_path, monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    path = tmp_path / "auth.json"
    path.write_text('{"key": "file-key"}', encoding="utf-8")
    client = OpenAICompatClient(model="m", base_url="http://x", api_key_file=str(path))
    assert client.api_key == "env-key"


def test_openai_compat_timeout_from_env(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT_S", "7.5")
    assert OpenAICompatClient(model="m", base_url="http://x").timeout_s == 7.5
    assert OpenAICompatClient(model="m", base_url="http://x", timeout_s=3.0).timeout_s == 3.0


def test_openai_compat_extra_headers_and_user_agent(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_EXTRA_HEADERS", '{"x-opencode-session": "marl-traffic"}')
    monkeypatch.setenv("LLM_USER_AGENT", "marl-test/1.0")
    client = OpenAICompatClient(model="m", base_url="http://x")
    assert client.extra_headers == {"x-opencode-session": "marl-traffic"}
    assert client.user_agent == "marl-test/1.0"

    monkeypatch.setenv("LLM_EXTRA_HEADERS", "not json")
    monkeypatch.delenv("LLM_USER_AGENT", raising=False)
    client = OpenAICompatClient(model="m", base_url="http://x")
    assert client.extra_headers == {}
    assert client.user_agent == "marl-traffic/0.1"


def test_replay_strict_miss_raises(tmp_path):
    replayed = ReplayLLM(CountingClient(), str(tmp_path / "cache.jsonl"), strict=True)
    with pytest.raises(LLMError, match="replay cache miss"):
        replayed.complete("s", "u", {})
    assert replayed.inner.calls == 0


def test_openai_compat_payload():
    client = OpenAICompatClient(model="m", base_url="http://localhost:11434/v1/")
    assert client.base_url == "http://localhost:11434/v1"
    payload = client._payload("sys", "user")
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"


def test_effort_from_env_and_args(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    assert OpenAICompatClient(model="m", base_url="http://x").effort == "low"
    assert OpenAICompatClient(model="m", base_url="http://x", effort="high").effort == "high"


def test_payload_includes_effort():
    client = OpenAICompatClient(model="m", base_url="http://x")
    assert client._payload("s", "u", "low")["reasoning_effort"] == "low"
    assert "reasoning_effort" not in client._payload("s", "u", "")


def test_http_400_retries_without_effort(monkeypatch):
    _clear_llm_env(monkeypatch)
    payloads = []

    def fake_urlopen(request, timeout=None):
        payloads.append(json.loads(request.data.decode("utf-8")))
        if len(payloads) == 1:
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", None,
                                         io.BytesIO(b"effort not supported"))
        return FakeResponse(_chat_body('{"directives": []}'))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = OpenAICompatClient(model="m", base_url="http://x")
    response = client.complete("s", "u", {}, effort="low")
    assert response.parsed == {"directives": []}
    assert len(payloads) == 2
    assert payloads[0].get("reasoning_effort") == "low"
    assert "reasoning_effort" not in payloads[1]


def test_http_400_without_effort_raises(monkeypatch):
    _clear_llm_env(monkeypatch)

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", None,
                                     io.BytesIO(b"nope"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = OpenAICompatClient(model="m", base_url="http://x")
    with pytest.raises(LLMHTTPError) as info:
        client.complete("s", "u", {})
    assert info.value.status == 400


def test_cached_tokens_parsed(monkeypatch):
    _clear_llm_env(monkeypatch)

    def fake_urlopen(request, timeout=None):
        return FakeResponse(_chat_body('{"ok": true}',
                                       {"prompt_tokens": 100, "completion_tokens": 20,
                                        "prompt_cache_hit_tokens": 64}))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    response = OpenAICompatClient(model="m", base_url="http://x").complete("s", "u", {})
    assert response.tokens_cached == 64


def test_cached_tokens_details_fallback(monkeypatch):
    _clear_llm_env(monkeypatch)

    def fake_urlopen(request, timeout=None):
        return FakeResponse(_chat_body('{"ok": true}',
                                       {"prompt_tokens": 100, "completion_tokens": 20,
                                        "prompt_tokens_details": {"cached_tokens": 32}}))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    response = OpenAICompatClient(model="m", base_url="http://x").complete("s", "u", {})
    assert response.tokens_cached == 32


def test_replay_key_includes_effort(tmp_path):
    inner = CountingClient()
    replayed = ReplayLLM(inner, str(tmp_path / "cache.jsonl"))
    replayed.complete("s", "u", {}, effort="low")
    replayed.complete("s", "u", {}, effort="low")
    assert inner.calls == 1
    replayed.complete("s", "u", {}, effort="medium")
    assert inner.calls == 2
    replayed.complete("s", "u", {})
    assert inner.calls == 3


def test_empty_call_effort_falls_back_to_client_default(monkeypatch):
    _clear_llm_env(monkeypatch)
    payloads = []

    def fake_urlopen(request, timeout=None):
        payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(_chat_body('{"ok": true}'))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = OpenAICompatClient(model="m", base_url="http://x", effort="low")
    client.complete("s", "u", {}, effort="")
    client.complete("s", "u", {}, effort="high")
    assert payloads[0]["reasoning_effort"] == "low"
    assert payloads[1]["reasoning_effort"] == "high"


class DefaultEffortClient(CountingClient):
    effort = "low"


def test_replay_empty_effort_resolves_to_inner_default(tmp_path):
    inner = DefaultEffortClient()
    replayed = ReplayLLM(inner, str(tmp_path / "cache.jsonl"))
    replayed.complete("s", "u", {}, effort="")
    replayed.complete("s", "u", {}, effort="low")
    assert inner.calls == 1


def test_prompt_hash_stable():
    from agents.llm.client import prompt_hash
    assert prompt_hash("a", "b") == prompt_hash("a", "b")
    assert prompt_hash("a", "b") != prompt_hash("a", "c")
