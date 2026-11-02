"""The LLM strategist: a valid answer changes the mode after its latency, an invalid one
keeps the current mode, a missing server never stops the episode."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cotraffic.llm import strategist as st
from cotraffic.llm.client import LLMError


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, schema=None):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply, latency_s=6.0, prompt_tokens=100, output_tokens=20)


def env_at(now: float):
    return SimpleNamespace(
        now=now, episode=SimpleNamespace(end_time=2700.0), intersections={"A": 0}
    )


@pytest.fixture(autouse=True)
def quiet_network(monkeypatch):
    state = {"junctions": 1, "vehicles": 10, "halted": 3, "backlog": 0, "queue_mean": 3.0,
             "queue_max": 3, "queue_max_at": "A", "long_queues": 0, "pedestrians": 0,
             "events": []}  # fmt: skip
    monkeypatch.setattr(st, "network_state", lambda env: dict(state))


def run(replies, times):
    s = st.LlmStrategist(FakeClient(replies), st.StrategistPrompt.load(), window_s=300.0)
    s.reset(env_at(0.0))
    for t in times:
        s.update(env_at(t))
    return s


def test_valid_answer_applies_after_its_latency():
    s = run(['{"mode": "fluidite", "reason": "queues grow"}'], [0.0])
    assert s.current == "equilibre"  # the answer took 6 s
    s.update(env_at(5.0))
    assert s.current == "equilibre"
    s.update(env_at(10.0))
    assert s.current == "fluidite"
    assert s.switches == 1
    assert s.calls[0].valid and s.calls[0].reason == "queues grow"
    assert s.modes(SimpleNamespace(intersections={"A": 0, "B": 1})) == {"A": "mp", "B": "mp"}


def test_invalid_answer_gets_one_retry_then_keeps_the_mode():
    s = run(['{"mode": "chaos"}', "not json"], [0.0, 10.0])
    assert s.current == "equilibre"
    assert not s.calls[0].valid and s.calls[0].attempts == 2
    assert s.client.calls == 2


def test_missing_server_keeps_the_mode():
    s = run([LLMError("down")], [0.0, 10.0])
    assert s.current == "equilibre"
    assert s.calls[0].error


def test_one_call_per_window():
    s = run(['{"mode": "agent", "reason": "a"}', '{"mode": "equilibre", "reason": "b"}'],
            [0.0, 100.0, 299.0, 300.0, 310.0])  # fmt: skip
    assert len(s.calls) == 2
    assert s.current == "equilibre" and s.switches == 2


def test_the_prompt_restricts_the_answer_to_the_three_modes():
    schema = st.StrategistPrompt.load().schema()
    assert schema["properties"]["mode"]["enum"] == list(st.MODES)
    assert "<state>" in st.StrategistPrompt.load().system  # the state is data, not instructions
