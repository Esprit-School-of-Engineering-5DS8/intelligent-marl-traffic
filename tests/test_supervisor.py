import json

from agents.llm.agent import LLMAgent
from agents.llm.client import CallLogger, LLMError, LLMResponse, MockLLM
from agents.supervisor.arbiter import Arbiter
from agents.supervisor.blackboard import Blackboard
from agents.supervisor.supervisor import Supervisor, SupervisorConfig

TLS = ["A"]
STATES = {
    "A": {
        "current_axis": "NS",
        "time_in_phase": 5,
        "ns_lanes": {"n0"},
        "ew_lanes": {"e0"},
        "lane_queues": {"n0": 1, "e0": 1},
        "lane_waiting": {"n0": 0.0, "e0": 0.0},
    },
}


def make_supervisor(tmp_path=None, responder=None, roles=("operator", "emergency")):
    agents = {role: LLMAgent(role, MockLLM(responder)) for role in roles}
    logger = CallLogger(str(tmp_path / "decisions.jsonl")) if tmp_path else None
    return Supervisor(
        agents=agents,
        arbiter=Arbiter(TLS),
        blackboard=Blackboard(),
        logger=logger,
        config=SupervisorConfig(delta_s=30.0, ev_replan_s=10.0),
    )


def test_should_run_periodic_and_ev_triggers():
    supervisor = make_supervisor()
    assert supervisor.should_run(0.0, []) is True
    supervisor.run(0.0, STATES)
    assert supervisor.should_run(1.0, []) is False
    assert supervisor.should_run(30.0, []) is True
    assert supervisor.should_run(5.0, [object()]) is True


def test_run_logs_call_and_posts_feedback(tmp_path):
    supervisor = make_supervisor(tmp_path)
    results = supervisor.run(0.0, STATES)
    assert len(results) == 1  # only the operator: no EV active
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
    assert supervisor.should_run(0.0, evs)
    supervisor.run(0.0, STATES, evs)
    assert not supervisor.should_run(1.0, evs)
    assert supervisor.should_run(10.0, evs)


def test_client_failure_falls_back_to_empty_envelope(tmp_path):
    def boom(system, user, schema):
        raise LLMError("no backend")

    supervisor = make_supervisor(tmp_path, responder=boom)
    results = supervisor.run(0.0, STATES)
    assert len(results) == 1 and results[0].accepted == []
    assert supervisor.stats["fallbacks"] == 1

    record = json.loads((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip())
    assert "no backend" in record["error"]
    assert record["attempts"] == 2  # one retry before fallback


def test_retry_once_then_success():
    class FlakyClient:
        model = "flaky"

        def __init__(self):
            self.calls = 0

        def complete(self, system, user, schema):
            self.calls += 1
            if self.calls == 1:
                raise LLMError("transient")
            return LLMResponse(parsed={"directives": [], "alerts": [], "explanation": "ok"})

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
