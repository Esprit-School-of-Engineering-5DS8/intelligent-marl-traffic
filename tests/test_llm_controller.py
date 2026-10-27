"""Tests for the batched LLM controller and its deterministic fallback."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from cotraffic.assistant.llm import LLMUnavailableError
from cotraffic.controllers.llm import LLMController
from cotraffic.llm.providers import LLMResult


class FakeActionSpace:
    n = 2


class WideActionSpace:
    n = 3


class FakeMeasurements:
    def __init__(self) -> None:
        self.lanes = ["a0", "b0", "ao", "bo"]
        self.capacity = dict.fromkeys(self.lanes, 10.0)
        self.halting = {"a0": 5.0, "b0": 1.0, "ao": 0.0, "bo": 0.0}
        self.count = {"a0": 6.0, "b0": 2.0, "ao": 1.0, "bo": 1.0}
        self.speed = dict.fromkeys(self.lanes, 5.0)

    def queue(self, lanes) -> float:
        return sum(self.halting[lane] for lane in lanes) / 10.0

    def link_pressure(self, in_lane: str, out_lane: str) -> float:
        return self.count[in_lane] / self.capacity[in_lane] - self.count[out_lane] / self.capacity[
            out_lane
        ]


class FakeIntersection:
    def __init__(self, tls_id: str) -> None:
        self.id = tls_id
        self.phase = 0
        self.in_yellow = False
        self.green_since = 0.0
        self.phase_lanes = [frozenset({"a0"}), frozenset({"b0"})]
        self.phase_links = [frozenset({0}), frozenset({1})]
        self.side_lanes = {
            "north": ["a0"],
            "east": [],
            "south": ["b0"],
            "west": [],
        }
        self.crossings = []
        self.links = [
            SimpleNamespace(index=0, in_lane="a0", out_lane="ao", crossing=None),
            SimpleNamespace(index=1, in_lane="b0", out_lane="bo", crossing=None),
        ]
        self.link_by_index = {link.index: link for link in self.links}

    def green_elapsed(self, now: float) -> float:
        return now - self.green_since


class FakeEnv:
    def __init__(self) -> None:
        self.now = 0.0
        self.intersections = {"A0": FakeIntersection("A0"), "B0": FakeIntersection("B0")}
        self.possible_agents = list(self.intersections)
        self.meas = FakeMeasurements()
        self.ped_waiting = {}
        self.ev_info = {}

    def action_space(self, agent: str):
        return FakeActionSpace()


class WideEnv(FakeEnv):
    def action_space(self, agent: str):
        return WideActionSpace()


class FakeProvider:
    model = "fake-model"

    def __init__(self, data: dict | None = None, error: Exception | None = None) -> None:
        self.data = data or {"decisions": []}
        self.error = error
        self.calls = 0
        self.efforts: list[str] = []

    def chat_json(self, messages, schema, max_tokens=700, effort=None):
        self.calls += 1
        self.efforts.append(effort)
        if self.error is not None:
            raise self.error
        return LLMResult(self.data, "{}", 1.0, 10, 5)


def make_controller(provider: FakeProvider) -> LLMController:
    return LLMController(client=provider, interval_s=30)


def test_batches_all_intersections_and_holds_between_calls():
    provider = FakeProvider(
        {
            "decisions": [
                {"tls_id": "A0", "phase": 1},
                {"tls_id": "B0", "phase": 0},
            ]
        }
    )
    env = FakeEnv()
    controller = make_controller(provider)
    controller.reset(env)

    assert controller.act(env, {}) == {"A0": 1, "B0": 0}
    assert provider.calls == 1

    env.now = 5.0
    assert controller.act(env, {}) == {"A0": 1, "B0": 0}
    assert provider.calls == 1

    env.now = 30.0
    assert controller.act(env, {}) == {"A0": 1, "B0": 0}
    assert provider.calls == 2
    assert controller.metrics()["llm_success"] == 2
    assert controller.metrics()["llm_cache_hits"] == 1


def test_phases_array_maps_to_intersections_in_order():
    provider = FakeProvider({"phases": [1, 0]})
    env = FakeEnv()
    controller = make_controller(provider)
    controller.reset(env)

    assert controller.act(env, {}) == {"A0": 1, "B0": 0}
    assert controller.metrics()["llm_success"] == 1
    assert controller.metrics()["llm_partial"] == 0


def test_schema_uses_a_compact_phases_array():
    provider = FakeProvider({"phases": [0, 0]})
    env = FakeEnv()
    controller = make_controller(provider)
    controller.reset(env)

    schema = controller._schema(env, sorted(env.intersections))
    assert schema["required"] == ["phases"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["phases"]["items"]["maximum"] == 1


def test_reasoning_effort_is_forwarded_and_reported():
    provider = FakeProvider({"phases": [0, 0]})
    env = FakeEnv()
    controller = make_controller(provider)
    controller.reset(env)

    controller.act(env, {})
    assert provider.efforts == ["none"]
    assert controller.metrics()["llm_reasoning_effort"] == "none"


def test_phase_count_uses_intersection_not_padded_action_space():
    provider = FakeProvider({"phases": [2, 0]})
    env = WideEnv()
    controller = make_controller(provider)
    controller.reset(env)

    schema = controller._schema(env, sorted(env.intersections))
    assert schema["properties"]["phases"]["items"]["maximum"] == 1
    assert controller.act(env, {}) == {"A0": 0, "B0": 0}
    assert controller.metrics()["llm_partial"] == 1


def test_invalid_phase_and_missing_intersection_fall_back_to_max_pressure():
    provider = FakeProvider(
        {
            "decisions": [
                {"tls_id": "A0", "phase": 1},
                {"tls_id": "B0", "phase": 9},
                {"tls_id": "unknown", "phase": 0},
            ]
        }
    )
    env = FakeEnv()
    controller = make_controller(provider)
    controller.reset(env)

    actions = controller.act(env, {})
    assert actions == {"A0": 1, "B0": 0}
    assert controller.metrics()["llm_success"] == 1
    assert controller.metrics()["llm_partial"] == 1


def test_provider_error_falls_back_and_backs_off():
    provider = FakeProvider(error=LLMUnavailableError("quota"))
    env = FakeEnv()
    controller = make_controller(provider)
    controller.reset(env)

    assert controller.act(env, {}) == {"A0": 0, "B0": 0}
    assert controller.metrics()["llm_fallbacks"] == 1
    assert "quota" in controller.metrics()["llm_last_error"]

    env.now = 5.0
    assert controller.act(env, {}) == {"A0": 0, "B0": 0}
    assert provider.calls == 1


def test_missing_key_is_reported_without_raising(monkeypatch):
    def unavailable(**_):
        raise LLMUnavailableError("GROQ_API_KEY is not configured")

    monkeypatch.setattr("cotraffic.controllers.llm.make_provider", unavailable)
    env = FakeEnv()
    controller = LLMController()
    controller.reset(env)

    assert controller.act(env, {}) == {"A0": 0, "B0": 0}
    assert controller.metrics()["llm_available"] == 0
    assert "GROQ_API_KEY" in controller.metrics()["llm_last_error"]


def test_no_api_key_in_error_text():
    provider = FakeProvider(error=LLMUnavailableError("boom sk-secret"))
    provider.api_key = "sk-secret"
    env = FakeEnv()
    controller = make_controller(provider)
    controller.reset(env)

    controller.act(env, {})
    assert "sk-secret" not in controller.metrics()["llm_last_error"]
