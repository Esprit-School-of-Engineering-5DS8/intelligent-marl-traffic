"""Emergency and pedestrian reviewer tests."""

from __future__ import annotations

from test_llm_team_controller import FakeEnv

from cotraffic.controllers.llm_team.client import MockClient, TeamError
from cotraffic.controllers.llm_team.roles.emergency import EmergencyAgent
from cotraffic.controllers.llm_team.roles.operator import OperatorAgent
from cotraffic.controllers.llm_team.roles.pedestrian import PedestrianAgent
from cotraffic.controllers.llm_team.snapshot import (
    build_evs,
    build_phase_maps,
    build_snapshot,
    build_states,
)
from cotraffic.envs.ev import EVState, UpcomingTLS


def _emergency_snapshot(distance_m=20.0, t=0.0, evs=True):
    env = FakeEnv()
    if evs:
        env.ev_states = [
            EVState(
                "ev0",
                "edge",
                "lane",
                10.0,
                (UpcomingTLS("B0", 2, distance_m, "r"),),
            )
        ]
    maps = build_phase_maps(env)
    snapshot = build_snapshot(
        t,
        build_states(env, maps),
        evs=build_evs(env),
        network=env.network,
    )
    return snapshot, maps


def _preempts(call):
    return [
        directive
        for directive in call.envelope.get("directives", [])
        if directive.get("type") == "preempt"
    ]


def test_emergency_reviewer_pins_exact_phase():
    snapshot, maps = _emergency_snapshot()

    def responder(system, user, schema):
        return {
            "directives": [
                {
                    "tls": "B0",
                    "type": "preempt",
                    "phase": "EW",
                    "ev": "ev0",
                    "start_in_s": 0,
                    "hold_s": 10,
                    "ttl_s": 20,
                }
            ],
            "alerts": [],
            "explanation": "test",
        }

    agent = EmergencyAgent(MockClient(responder), phase_maps=maps)
    call = agent.ask(0.0, snapshot)
    directives = _preempts(call)
    assert len(directives) == 1
    assert directives[0]["phase"] == "NS"
    assert directives[0]["phase_index"] == 2
    assert directives[0]["eta_s"] == 2.0
    assert call.review["source"] == "llm"


def test_emergency_rule_fallback_proposes_corridor():
    snapshot, maps = _emergency_snapshot()

    def boom(system, user, schema):
        raise TeamError("backend down")

    agent = EmergencyAgent(MockClient(boom), phase_maps=maps)
    call = agent.ask(0.0, snapshot)
    directives = _preempts(call)
    assert len(directives) == 1
    assert directives[0]["phase"] == "NS"
    assert directives[0]["phase_index"] == 2
    assert call.review["source"] == "rules"


def _ped_snapshot(phase_index=2):
    return {
        "t": 0.0,
        "network": "testnet",
        "tls_ids": ["B0"],
        "intersections": {
            "B0": {"phase": "EW", "time_in_phase_s": 5, "queue": {"ns": 2, "ew": 8}}
        },
        "alerts": [],
        "evs": [],
        "blackboard": [],
        "pedestrians": [
            {
                "tls": "B0",
                "axis": "NS",
                "waiting": 4,
                "max_wait_s": 25.0,
                "mean_wait_s": 12.0,
                "phase_index": phase_index,
            }
        ],
    }


def test_pedestrian_reviewer_enforces_window_and_exact_phase():
    def responder(system, user, schema):
        return {
            "directives": [
                {
                    "tls": "B0",
                    "type": "serve_ped",
                    "phase": "NS",
                    "min_green_s": 5,
                    "ttl_s": 10,
                }
            ],
            "alerts": [],
            "explanation": "test",
        }

    agent = PedestrianAgent(MockClient(responder))
    call = agent.ask(0.0, _ped_snapshot())
    directive = call.envelope["directives"][0]
    assert directive["min_green_s"] == 15.0
    assert directive["phase_index"] == 2
    assert directive["ttl_s"] >= 25.0


def test_pedestrian_rule_fallback_serves_long_wait():
    def boom(system, user, schema):
        raise TeamError("backend down")

    agent = PedestrianAgent(MockClient(boom))
    call = agent.ask(0.0, _ped_snapshot(phase_index=None))
    directives = [
        d for d in call.envelope["directives"] if d.get("type") == "serve_ped"
    ]
    assert len(directives) == 1
    assert directives[0]["tls"] == "B0"
    assert directives[0]["min_green_s"] == 18.0
    assert call.review["source"] == "rules"


def test_emergency_maintain_extends_and_releases_without_client():
    snapshot, maps = _emergency_snapshot(distance_m=20.0, t=0.0)

    def responder(system, user, schema):
        return {
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

    client = MockClient(responder)
    agent = EmergencyAgent(client, phase_maps=maps)
    call = agent.ask(0.0, snapshot)
    assert len(_preempts(call)) == 1
    assert len(client.calls) == 1

    later, _ = _emergency_snapshot(distance_m=10.0, t=5.0)
    maintained = agent.maintain(5.0, later)
    assert maintained is not None
    directive = _preempts(maintained)[0]
    assert directive["start_in_s"] == 0.0
    assert directive["hold_s"] == 9.0
    assert len(client.calls) == 1

    assert agent.maintain(5.0, later) is None

    gone, _ = _emergency_snapshot(t=20.0, evs=False)
    released = agent.maintain(20.0, gone)
    assert released is not None
    directive = _preempts(released)[0]
    assert directive["hold_s"] == 0
    assert len(client.calls) == 1


def test_operator_and_pedestrian_prompts_are_pruned():
    snapshot = _ped_snapshot()
    snapshot["evs"] = [
        {
            "id": "ev0",
            "edge": "edge",
            "speed": 10.0,
            "next_tls": [
                {"tls": "B0", "link_index": 2, "dist_m": 10.0, "eta_s": 1.0}
            ],
        }
    ]
    operator_view = OperatorAgent(MockClient()).snapshot_for_prompt(snapshot)
    assert "pedestrians" not in operator_view
    assert operator_view["evs"] == [
        {"id": "ev0", "eta_s": 1.0, "tls": ["B0"]}
    ]

    pedestrian_view = PedestrianAgent(MockClient()).snapshot_for_prompt(snapshot)
    assert "evs" not in pedestrian_view
    assert set(pedestrian_view["intersections"]) == {"B0"}


def test_snapshot_filters_far_evs_and_caps_context():
    env = FakeEnv()
    env.ev_states = [
        EVState(
            "near",
            "edge",
            "lane",
            10.0,
            tuple(UpcomingTLS(f"T{i}", 0, 10.0 * (i + 1), "r") for i in range(5)),
        ),
        EVState("far", "edge", "lane", 1.0, (UpcomingTLS("T9", 0, 500.0, "r"),)),
    ]
    snapshot = build_snapshot(
        0.0,
        build_states(env, build_phase_maps(env)),
        evs=build_evs(env),
        alerts=[{"kind": "queue_growth", "i": i} for i in range(10)],
        blackboard=[{"kind": "feedback", "i": i} for i in range(10)],
        network=env.network,
    )
    assert [ev["id"] for ev in snapshot["evs"]] == ["near"]
    assert len(snapshot["evs"][0]["next_tls"]) == 3
    assert len(snapshot["alerts"]) == 5
    assert len(snapshot["blackboard"]) == 6
