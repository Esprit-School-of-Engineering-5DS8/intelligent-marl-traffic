"""Controller tests for the integration LLM team."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cotraffic.assistant.llm import LLMUnavailableError
from cotraffic.controllers.llm_team.client import (
    MockClient,
    ReplayClient,
    TeamError,
    TeamResponse,
)
from cotraffic.controllers.llm_team.controller import LLMTeamController
from cotraffic.controllers.llm_team.snapshot import build_pedestrians, build_phase_map
from cotraffic.controllers.registry import TEAM, make_controller


class FakeActionSpace:
    n = 3


class FakeMeasurements:
    def __init__(self) -> None:
        self.lanes = ["n0", "e0", "s0", "no", "eo", "so"]
        self.capacity = dict.fromkeys(self.lanes, 10.0)
        self.halting = {"n0": 5.0, "e0": 6.0, "s0": 1.0, "no": 0.0, "eo": 0.0, "so": 0.0}
        self.count = {"n0": 2.0, "e0": 3.0, "s0": 1.0, "no": 0.0, "eo": 0.0, "so": 0.0}
        self.waiting = {"n0": 5.0, "e0": 40.0, "s0": 3.0, "no": 0.0, "eo": 0.0, "so": 0.0}
        self.speed = dict.fromkeys(self.lanes, 5.0)

    def queue(self, lanes) -> float:
        return sum(self.halting[lane] for lane in lanes) / 10.0

    def link_pressure(self, in_lane: str, out_lane: str) -> float:
        return self.count[in_lane] / 10.0 - self.count[out_lane] / 10.0


def make_intersection(tls_id: str, phases: int) -> SimpleNamespace:
    if phases == 2:
        lanes = [("n0", "no", "south"), ("e0", "eo", "west")]
        states = ["Gr", "rG"]
    else:
        lanes = [
            ("n0", "no", "south"),
            ("e0", "eo", "west"),
            ("s0", "so", "north"),
        ]
        states = ["Grr", "rGr", "rrG"]
    links = [
        SimpleNamespace(index=index, in_lane=in_lane, out_lane=out_lane, crossing=None)
        for index, (in_lane, out_lane, _side) in enumerate(lanes)
    ]
    return SimpleNamespace(
        id=tls_id,
        phase=0,
        in_yellow=False,
        green_since=0.0,
        green_states=states,
        phase_links=[frozenset({index}) for index in range(phases)],
        phase_lanes=[frozenset({link.in_lane}) for link in links],
        side_lanes={},
        crossings=[],
        crossing_links=[],
        links=links,
        link_by_index={link.index: link for link in links},
        n_phases=phases,
        in_lanes=[link.in_lane for link in links],
        lane_side={in_lane: side for in_lane, _out, side in lanes},
        green_elapsed=lambda now: now - 0.0,
    )


class FakeEnv:
    def __init__(self) -> None:
        self.network = "testnet"
        self.now = 0.0
        self.intersections = {
            "A0": make_intersection("A0", 2),
            "B0": make_intersection("B0", 3),
        }
        self.meas = FakeMeasurements()
        self.ev_states = []
        self.ped_waiting = {}
        self.ped_wait_sum = {}
        self.crossing_owner = {}
        self.person_ids = set()
        self.neighbour_links = {}

    def action_space(self, agent: str):
        return FakeActionSpace()


class BiasClient:
    model = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system, user, schema, effort=None, max_tokens=700):
        self.calls += 1
        return TeamResponse(
            parsed={
                "directives": [
                    {"tls": "A0", "type": "bias", "ns": 2.0, "ew": 1.0, "ttl_s": 30}
                ],
                "alerts": [],
                "explanation": "favor NS at A0",
            },
            model=self.model,
        )


def test_registry_exposes_llm_team():
    # CoTraffic: the team is registered as team_rules and team_qwen (PROVENANCE.md)
    assert TEAM == ("team_rules", "team_qwen")
    controller = make_controller("team_rules", client=BiasClient())
    assert controller.name == "team_rules"


def test_controller_applies_directives_and_reports_metrics():
    env = FakeEnv()
    controller = LLMTeamController(client=BiasClient(), max_calls=10)
    controller.reset(env)
    actions = controller.act(env, {})
    assert actions["A0"] == 0
    assert actions["B0"] in (0, 1, 2)
    metrics = controller.metrics()
    assert metrics["llm_team_calls"] == 1
    assert metrics["llm_team_operator_calls"] == 1
    assert metrics["llm_team_available"] == 1
    assert metrics["llm_team_directives"] == 1


def test_mock_backend_needs_no_key_and_no_http(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("HTTP call attempted in mock mode")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    env = FakeEnv()
    controller = LLMTeamController(backend="mock")
    controller.reset(env)
    assert isinstance(controller._client, MockClient)
    actions = controller.act(env, {})
    assert set(actions) == {"A0", "B0"}
    assert controller.metrics()["llm_team_available"] == 1


def test_phase_map_two_and_three_phase_programs():
    two = build_phase_map(make_intersection("A0", 2))
    assert two.axis_by_action == ("NS", "EW")
    assert two.group_phases == ((0,), (1,))
    assert two.link_phase[1] == 1

    three = build_phase_map(make_intersection("B0", 3))
    assert three.axis_by_action == ("NS", "EW", "NS")
    assert three.link_phase[2] == 2
    assert three.group_lanes[2] == frozenset({"s0"})


def test_pedestrian_state_carries_exact_phase(monkeypatch):
    env = FakeEnv()
    env.ped_waiting = {"c1": 3}
    env.ped_wait_sum = {"c1": 60.0}
    env.crossing_owner = {"c1": "B0"}
    maps = {
        "B0": build_phase_map(env.intersections["B0"]),
    }
    maps["B0"] = type(maps["B0"])(
        **{
            **maps["B0"].__dict__,
            "crossing_axis": {"c1": "NS"},
            "crossing_phase": {"c1": 2},
        }
    )
    monkeypatch.setattr(
        "cotraffic.controllers.llm_team.snapshot.longest_waits",
        lambda _env: {"c1": 25.0},
    )
    states = build_pedestrians(env, maps)
    assert len(states) == 1
    assert states[0].axis == "NS"
    assert states[0].max_wait_s == 25.0
    assert states[0].mean_wait_s == 20.0
    assert states[0].phase_index == 2


def test_unavailable_provider_falls_back_to_max_pressure(monkeypatch):
    def unavailable(*args, **kwargs):
        raise LLMUnavailableError("no key")

    monkeypatch.setattr(
        "cotraffic.controllers.llm_team.controller.make_team_client", unavailable
    )
    env = FakeEnv()
    controller = LLMTeamController(backend="opencode")
    controller.reset(env)
    actions = controller.act(env, {})
    assert set(actions) == {"A0", "B0"}
    assert controller.metrics()["llm_team_available"] == 0
    assert "no key" in controller.metrics()["llm_team_last_error"]


def test_llm_team_package_has_no_traci_reference():
    package = Path("src/cotraffic/controllers/llm_team")
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "import traci" not in text and "from traci" not in text, path


def test_failed_call_does_not_break_the_tick():
    class BoomClient:
        model = "boom"

        def complete(self, system, user, schema, effort=None, max_tokens=700):
            raise RuntimeError("backend down")

    env = FakeEnv()
    controller = LLMTeamController(client=BoomClient(), max_calls=10)
    controller.reset(env)
    actions = controller.act(env, {})
    assert set(actions) == {"A0", "B0"}
    assert controller.metrics()["llm_team_fallbacks"] == 1


def test_replay_client_round_trip_and_strict_miss(tmp_path):
    cache = tmp_path / "cache.jsonl"
    responder = lambda system, user, schema: {
        "directives": [{"tls": "A0", "type": "bias", "ns": 1.1}],
        "alerts": [],
        "explanation": "cached",
    }
    writer = ReplayClient(MockClient(responder), str(cache))
    first = writer.complete("system", "user", {"type": "object"}, max_tokens=12)
    assert first.parsed["explanation"] == "cached"

    reader = ReplayClient(None, str(cache), strict=True, model="mock")
    second = reader.complete("system", "user", {"type": "object"}, max_tokens=12)
    assert second.parsed == first.parsed

    with pytest.raises(TeamError, match="cache miss"):
        reader.complete("system", "other", {"type": "object"}, max_tokens=12)


def test_controller_maintains_emergency_plan_without_extra_call():
    from cotraffic.envs.ev import EVState, UpcomingTLS

    env = FakeEnv()
    env.ev_states = [
        EVState("ev0", "edge", "lane", 10.0, (UpcomingTLS("B0", 2, 20.0, "r"),))
    ]
    client = MockClient(
        lambda system, user, schema: {
            "directives": [
                {
                    "tls": "B0",
                    "type": "preempt",
                    "phase": "NS",
                    "ev": "ev0",
                    "start_in_s": 0,
                    "hold_s": 10,
                    "ttl_s": 20,
                }
            ],
            "alerts": [],
            "explanation": "test",
        }
    )
    controller = LLMTeamController(client=client, max_calls=10)
    controller.reset(env)
    controller.act(env, {})
    assert len(client.calls) == 2

    env.now = 5.0
    env.ev_states = [
        EVState("ev0", "edge", "lane", 10.0, (UpcomingTLS("B0", 2, 10.0, "r"),))
    ]
    controller.act(env, {})
    metrics = controller.metrics()
    assert len(client.calls) == 2
    assert metrics["llm_team_code_updates"] == 1
