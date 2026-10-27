"""Supervisor cadence, events, logging and fallback tests."""

from __future__ import annotations

import json

from cotraffic.controllers.llm_team.agent import LLMAgent
from cotraffic.controllers.llm_team.arbiter import Arbiter
from cotraffic.controllers.llm_team.blackboard import Blackboard
from cotraffic.controllers.llm_team.client import (
    CallLogger,
    MockClient,
    TeamError,
    TeamResponse,
)
from cotraffic.controllers.llm_team.snapshot import PedestrianState
from cotraffic.controllers.llm_team.supervisor import Supervisor, SupervisorConfig
from cotraffic.envs.ev import EVState, UpcomingTLS

TLS = ["A"]
STATES = {
    "A": {
        "current_axis": "NS",
        "current_phase": 0,
        "time_in_phase": 5,
        "ns_lanes": {"n0"},
        "ew_lanes": {"e0"},
        "lane_queues": {"n0": 1, "e0": 1},
        "lane_waiting": {"n0": 0.0, "e0": 0.0},
    },
}


def _states(ns_queue: int):
    return {"A": {**STATES["A"], "lane_queues": {"n0": ns_queue, "e0": 2}}}


BUSY_STATES = _states(10)
CONGESTED_STATES = _states(20)


def make_supervisor(
    tmp_path=None,
    responder=None,
    roles=("operator", "emergency"),
    config=None,
    pedestrian=False,
    network="testnet",
):
    if pedestrian and "pedestrian" not in roles:
        roles = tuple(roles) + ("pedestrian",)
    client = MockClient(responder)
    agents = {role: LLMAgent(role, client) for role in roles}
    logger = CallLogger(str(tmp_path / "decisions.jsonl")) if tmp_path else None
    return Supervisor(
        agents=agents,
        arbiter=Arbiter(TLS),
        blackboard=Blackboard(),
        logger=logger,
        config=config or SupervisorConfig(delta_s=30.0, ev_replan_s=10.0),
        pedestrian_trigger=pedestrian,
        network=network,
    )


def test_should_run_periodic_and_ev_triggers():
    supervisor = make_supervisor()
    assert supervisor.should_run(0.0, STATES) is True
    supervisor.run(0.0, STATES)
    assert supervisor.should_run(1.0, STATES) is False
    assert supervisor.should_run(60.0, STATES) is True
    assert supervisor.should_run(5.0, STATES, [object()]) is True


def test_run_logs_call_and_posts_feedback(tmp_path):
    supervisor = make_supervisor(tmp_path)
    results = supervisor.run(0.0, STATES)
    assert len(results) == 1
    assert results[0].accepted == []
    assert len(supervisor.blackboard.of_kind("arbiter_result", 0.0)) == 1

    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["agent"] == "operator" and record["error"] is None
    assert record["arbiter"]["accepted"] == []
    assert record["attempts"] == 1


def test_emergency_runs_on_ev_cadence():
    supervisor = make_supervisor()
    evs = [object()]
    assert supervisor.should_run(0.0, STATES, evs)
    supervisor.run(0.0, STATES, evs)
    assert not supervisor.should_run(1.0, STATES, evs)
    assert supervisor.should_run(10.0, STATES, evs)


def _ev(veh_id="ev_0", distance_m=200.0, speed=10.0):
    return EVState(
        veh_id,
        "edge",
        "edge_0",
        speed,
        (UpcomingTLS("A", 0, distance_m, "r"),),
    )


def test_ev_events_trigger_off_cadence():
    supervisor = make_supervisor()
    ev = _ev(distance_m=200.0)
    assert supervisor.should_run(0.0, STATES, [ev]) is True
    supervisor.run(0.0, STATES, [ev])
    assert supervisor.stats["emergency_calls"] == 1

    assert supervisor.should_run(4.0, STATES, [_ev(distance_m=140.0)]) is True
    supervisor.run(4.0, STATES, [_ev(distance_m=140.0)])
    assert supervisor.stats["emergency_calls"] == 2

    assert supervisor.should_run(8.0, STATES, [_ev("ev_1", 180.0)]) is True
    supervisor.run(8.0, STATES, [_ev("ev_1", 180.0)])
    assert supervisor.should_run(9.0, STATES, [_ev("ev_1", 180.0)]) is False


def test_ev_events_can_be_disabled():
    config = SupervisorConfig(ev_event_triggers=False)
    supervisor = make_supervisor(config=config)
    ev = _ev()
    supervisor.run(0.0, STATES, [ev])
    assert supervisor.should_run(4.0, STATES, [_ev(distance_m=140.0)]) is False


def _ped(tls_id="A", axis="NS", waiting=4, max_wait=22.0):
    return PedestrianState(tls_id, axis, f":{tls_id}_c1", waiting, max_wait, 10.0)


def test_pedestrian_runs_on_data_and_events():
    supervisor = make_supervisor(pedestrian=True)
    ped = _ped()
    assert supervisor.should_run(0.0, STATES, (), (), [ped]) is True
    supervisor.run(0.0, STATES, (), (), (), [ped])
    assert supervisor.stats["pedestrian_calls"] == 1
    assert supervisor.should_run(1.0, STATES, (), (), [ped]) is False
    assert supervisor.should_run(8.0, STATES, (), (), [_ped("B", "EW")]) is True


def test_pedestrian_does_not_run_without_data_or_trigger():
    without_data = make_supervisor(pedestrian=True)
    without_data.run(0.0, STATES)
    assert without_data.should_run(1.0, STATES, (), (), []) is False

    disabled = make_supervisor(pedestrian=False)
    disabled.run(0.0, STATES)
    assert disabled.stats.get("pedestrian_calls", 0) == 0
    assert disabled.should_run(1.0, STATES, (), (), [_ped()]) is False


def test_classify_congested_on_long_pedestrian_wait():
    supervisor = make_supervisor(pedestrian=True)
    assert (
        supervisor.classify(0.0, STATES, pedestrians=[_ped(max_wait=25.0)])
        == "congested"
    )
    assert supervisor.classify(0.0, STATES, pedestrians=[_ped(max_wait=8.0)]) == "quiet"


def test_client_failure_falls_back_to_empty_envelope(tmp_path):
    def boom(system, user, schema):
        raise TeamError("no backend")

    supervisor = make_supervisor(tmp_path, responder=boom)
    results = supervisor.run(0.0, STATES)
    assert len(results) == 1 and results[0].accepted == []
    assert supervisor.stats["fallbacks"] == 1
    assert supervisor.stats["retries"] == 1

    record = json.loads((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip())
    assert "no backend" in record["error"]
    assert record["attempts"] == 2


def test_retry_once_then_success():
    class FlakyClient:
        model = "flaky"

        def __init__(self):
            self.calls = 0

        def complete(self, system, user, schema, effort=None, max_tokens=700):
            self.calls += 1
            if self.calls == 1:
                raise TeamError("transient")
            return TeamResponse(
                parsed={"directives": [], "alerts": [], "explanation": "ok"}
            )

    client = FlakyClient()
    agent = LLMAgent("operator", client)
    call = agent.ask(0.0, {"t": 0})
    assert call.error is None
    assert call.attempts == 2 and client.calls == 2


def test_accepted_directive_from_agent(tmp_path):
    def responder(system, user, schema):
        return {
            "directives": [{"tls": "A", "type": "bias", "ns": 1.5}],
            "alerts": [],
            "explanation": "favor NS",
        }

    supervisor = make_supervisor(tmp_path, responder=responder)
    results = supervisor.run(0.0, STATES)
    assert len(results[0].accepted) == 1
    assert results[0].accepted[0].ns == 1.5


def test_user_message_is_canonical_json():
    agent = LLMAgent("operator", MockClient())
    snapshot_a = {
        "t": 0.0,
        "intersections": {"A": {"queue": {"ns": 1, "ew": 2}, "neighbors": {"N": "B"}}},
        "alerts": [],
        "evs": [],
        "blackboard": [],
    }
    snapshot_b = {
        "blackboard": [],
        "evs": [],
        "alerts": [],
        "intersections": {"A": {"neighbors": {"N": "B"}, "queue": {"ew": 2, "ns": 1}}},
        "t": 0.0,
    }
    assert agent.build_user_message(0.0, snapshot_a) == agent.build_user_message(
        0.0, snapshot_b
    )


def test_forced_role_runs_off_cadence():
    supervisor = make_supervisor()
    supervisor.run(0.0, STATES)
    assert supervisor.stats["calls"] == 1
    results = supervisor.run(
        5.0, STATES, (), [{"kind": "queue_growth", "tls": "A"}], ("operator",)
    )
    assert len(results) == 1
    assert supervisor.stats["calls"] == 2


def test_max_calls_disables_slow_layer(tmp_path):
    supervisor = make_supervisor(tmp_path, config=SupervisorConfig(max_calls=2))
    supervisor.run(0.0, STATES)
    evs = [object()]
    supervisor.run(10.0, STATES, evs)
    assert supervisor.stats["calls"] == 2
    assert supervisor.should_run(60.0, STATES, evs) is False
    assert supervisor.run(60.0, STATES, evs) == []
    assert supervisor.stats["calls"] == 2
    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert "max_calls=2" in json.loads(lines[-1])["error"]


def test_cadence_tiers():
    quiet = make_supervisor()
    quiet.run(0.0, STATES)
    assert quiet.should_run(30.0, STATES) is False
    assert quiet.should_run(60.0, STATES) is True

    normal = make_supervisor()
    normal.run(0.0, BUSY_STATES)
    assert normal.should_run(29.0, BUSY_STATES) is False
    assert normal.should_run(30.0, BUSY_STATES) is True

    congested = make_supervisor()
    congested.run(0.0, CONGESTED_STATES)
    assert congested.should_run(14.0, CONGESTED_STATES) is False
    assert congested.should_run(15.0, CONGESTED_STATES) is True


def test_classify_tiers():
    supervisor = make_supervisor()
    assert supervisor.classify(0.0, STATES) == "quiet"
    assert supervisor.classify(0.0, BUSY_STATES) == "normal"
    assert supervisor.classify(0.0, CONGESTED_STATES) == "congested"
    assert supervisor.classify(0.0, STATES, alerts=[{"kind": "queue_growth"}]) == "congested"
    assert supervisor.classify(0.0, STATES, evs=[object()]) == "congested"


def test_effort_escalation(tmp_path):
    config = SupervisorConfig(base_effort="low", escalate_effort="medium")
    supervisor = make_supervisor(tmp_path, config=config)
    supervisor.run(0.0, CONGESTED_STATES)
    assert supervisor.agents["operator"].client.calls[0]["effort"] == "medium"
    assert supervisor.stats["escalated"] == 1

    record = json.loads((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip())
    assert record["complexity"] == "congested" and record["effort"] == "medium"

    quiet = make_supervisor(config=config)
    quiet.run(0.0, STATES)
    assert quiet.agents["operator"].client.calls[0]["effort"] == "low"
    assert quiet.stats["escalated"] == 0


def test_no_escalation_when_disabled():
    config = SupervisorConfig(base_effort="low", escalate_effort="")
    supervisor = make_supervisor(config=config)
    supervisor.run(0.0, CONGESTED_STATES)
    assert supervisor.agents["operator"].client.calls[0]["effort"] == "low"
    assert supervisor.stats["escalated"] == 0


def test_agent_alerts_reach_blackboard(tmp_path):
    def responder(system, user, schema):
        return {
            "directives": [],
            "alerts": [{"kind": "spillback", "where": "A1A0"}],
            "explanation": "",
        }

    supervisor = make_supervisor(tmp_path, responder=responder)
    supervisor.run(0.0, STATES)
    alerts = supervisor.blackboard.of_kind("spillback", 0.0)
    assert len(alerts) == 1
    assert alerts[0].to_dict()["where"] == "A1A0"
