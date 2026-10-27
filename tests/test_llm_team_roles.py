"""Emergency and pedestrian reviewer tests."""

from __future__ import annotations

from test_llm_team_controller import FakeEnv

from cotraffic.controllers.llm_team.client import MockClient, TeamError
from cotraffic.controllers.llm_team.roles.emergency import EmergencyAgent
from cotraffic.controllers.llm_team.roles.pedestrian import PedestrianAgent
from cotraffic.controllers.llm_team.snapshot import (
    build_evs,
    build_phase_maps,
    build_snapshot,
    build_states,
)
from cotraffic.envs.ev import EVState, UpcomingTLS


def _emergency_snapshot():
    env = FakeEnv()
    env.ev_states = [
        EVState("ev0", "edge", "lane", 10.0, (UpcomingTLS("B0", 2, 20.0, "r"),))
    ]
    maps = build_phase_maps(env)
    snapshot = build_snapshot(
        0.0,
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
