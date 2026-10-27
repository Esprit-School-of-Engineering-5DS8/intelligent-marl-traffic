"""The teammate's LLM team inside CoTraffic (controllers/team.py): environment view, local
client, latency model, and the two controllers team_rules and team_qwen."""

import json
from types import SimpleNamespace

import pytest
from test_llm_team_controller import BiasClient, FakeEnv

from cotraffic.controllers.llm_team.client import MockClient
from cotraffic.controllers.llm_team.controller import LLMTeamController
from cotraffic.controllers.llm_team.schemas import DIRECTIVE_ENVELOPE_SCHEMA, SchemaError
from cotraffic.controllers.llm_team.snapshot import build_states
from cotraffic.controllers.registry import make_controller
from cotraffic.controllers.team import (
    SCHEMA_NOTE,
    TEAM_NUM_CTX,
    LocalTeamClient,
    TeamController,
    TeamEnvView,
    delay_for,
    prompt_version,
)
from cotraffic.llm.client import Ollama, Options


def no_http(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("HTTP call attempted")

    monkeypatch.setattr("urllib.request.urlopen", fail)


def test_delay_modes():
    assert delay_for("measured", 7.5) == 7.5
    assert delay_for("zero", 7.5) == 0.0
    assert delay_for("double", 7.5) == 15.0
    assert delay_for("fixed:12", 7.5) == 12.0
    with pytest.raises(ValueError):
        delay_for("later", 1.0)


def test_registry_builds_both_team_controllers_without_any_http(monkeypatch):
    no_http(monkeypatch)
    rules = make_controller("team_rules")
    assert isinstance(rules._client, MockClient)
    assert rules.name == "team_rules" and rules.latency_mode == "zero"
    qwen = make_controller("team_qwen")
    assert isinstance(qwen._client, LocalTeamClient)
    assert qwen.name == "team_qwen" and qwen.latency_mode == "measured"
    assert qwen.options.num_ctx == TEAM_NUM_CTX
    env = FakeEnv()
    qwen.reset(env)  # building the team calls no model
    rules.reset(env)
    assert qwen.metrics()["llm_team_provider"] == "ollama"
    assert rules.metrics()["llm_team_provider"] == "mock"
    assert set(rules.act(env, {})) == {"A0", "B0"}
    assert prompt_version().startswith("team-v2/")


def test_zero_latency_reproduces_the_source_controller():
    ours = TeamController("team_qwen", client=BiasClient(), latency="zero")
    source = LLMTeamController(client=BiasClient(), max_calls=0)
    env_a, env_b = FakeEnv(), FakeEnv()
    ours.reset(env_a)
    source.reset(env_b)
    for t in (0.0, 5.0, 30.0, 65.0, 130.0):
        env_a.now = env_b.now = t
        assert ours.act(env_a, {}) == source.act(env_b, {})
    a, b = ours.metrics(), source.metrics()
    for key in ("llm_team_calls", "llm_team_directives", "llm_team_fallbacks"):
        assert a[key] == b[key], key


def test_an_answer_acts_only_after_its_delay_and_is_not_asked_twice():
    controller = TeamController("team_qwen", client=BiasClient(), latency="fixed:12")
    env = FakeEnv()
    controller.reset(env)
    controller.act(env, {})  # t = 0: the operator is asked
    sup = controller._supervisor
    assert controller.metrics()["llm_team_directives"] == 0 and len(sup.pending) == 1
    # the operator is due again (forced), but its answer is still on the way
    env.now = 5.0
    sup.tick(5.0, build_states(env, controller._phase_maps), force_roles=("operator",))
    assert controller._client.calls == 1 and controller.metrics()["llm_team_directives"] == 0
    env.now = 15.0  # first decision after the 12 s delay
    controller.act(env, {})
    m = controller.metrics()
    assert m["team_answers_delivered"] == 1 and m["llm_team_directives"] == 1
    assert m["team_delay_mean_s"] == 15.0 and m["team_answers_dropped"] == 0


def test_local_client_uses_json_mode_and_checks_the_schema(monkeypatch):
    sent = {}
    envelope = {"directives": [], "alerts": [], "explanation": "ok"}

    def post(self, path, body, timeout):
        sent.update(body)
        return {"message": {"content": json.dumps(envelope)}, "prompt_eval_count": 10}

    monkeypatch.setattr(Ollama, "_post", post)
    client = LocalTeamClient("qwen2.5:3b", Options())
    reply = client.complete("system", "user", DIRECTIVE_ENVELOPE_SCHEMA, max_tokens=123)
    assert sent["format"] == "json" and sent["options"]["num_predict"] == 123
    assert [m["role"] for m in sent["messages"]] == ["system", "system", "user"]
    assert sent["messages"][1]["content"].startswith(SCHEMA_NOTE)
    assert reply.parsed == envelope and reply.tokens_in == 10
    for text in ("not json", '{"directives": "all green"}'):
        monkeypatch.setattr(Ollama, "_post", lambda *a, text=text: {"message": {"content": text}})
        with pytest.raises(SchemaError):
            client.complete("system", "user", DIRECTIVE_ENVELOPE_SCHEMA)


def test_env_view_reads_what_the_source_environment_computed():
    tls = [("A0", 3, 120.0, "r"), ("B0", 1, 400.0, "r")]
    conn = SimpleNamespace(
        lane=SimpleNamespace(getWaitingTime=lambda ln: {"l1": 4.0, "l2": 0.0}[ln]),
        person=SimpleNamespace(
            getWaitingTime=lambda p: {"p1": 5.0, "p2": 2.0, "p3": 0.0}[p],
            getRoadID=lambda p: ":w0",
            getNextEdge=lambda p: ":c0",
        ),
        vehicle=SimpleNamespace(
            getRoadID=lambda v: "e1",
            getLaneID=lambda v: "e1_0",
            getSpeed=lambda v: 12.0,
            getNextTLS=lambda v: tls,
        ),
    )
    env = SimpleNamespace(
        conn=conn,
        now=42.0,
        intersections={"A0": SimpleNamespace(in_lanes=["l1", "l2"])},
        meas=SimpleNamespace(halting={"l1": 3.0}),
        ev_ids={"ev_0"},
        person_ids={"p1", "p2", "p3"},
        walkingareas={":w0"},
        crossing_owner={":c0": "A0"},
    )
    view = TeamEnvView(env)
    assert view.meas.waiting == {"l1": 4.0, "l2": 0.0} and view.meas.halting == {"l1": 3.0}
    assert [n.tls_id for n in view.ev_states[0].next_tls] == ["A0", "B0"]
    assert view.ped_wait_sum == {":c0": 7.0}
    assert view.now == 42.0 and view.crossing_owner == {":c0": "A0"}


@pytest.mark.sumo
def test_without_events_team_rules_requests_what_max_pressure_requests():
    from cotraffic.controllers.classical import MaxPressure
    from cotraffic.llm.rollout import EpisodeSpec, make_env

    team = make_controller("team_rules")
    mp = MaxPressure()
    env = make_env(EpisodeSpec("grid4x4", "peak", [], 1000), team.agent_cfg)
    try:
        obs, _ = env.reset(seed=1000)
        team.reset(env)
        mp.reset(env)
        steps = 0
        while env.now < 400:
            requested = {k: int(v) for k, v in mp.act(env, obs).items()}
            assert {k: int(v) for k, v in team.act(env, obs).items()} == requested
            obs, *_ = env.step(requested)
            steps += 1
    finally:
        env.close()
    assert steps > 50 and team.metrics()["llm_team_directives"] == 0


@pytest.mark.sumo
def test_team_rules_preempts_for_an_emergency_vehicle_behind_the_shield():
    from cotraffic.llm.rollout import EpisodeSpec, make_env

    team = make_controller("team_rules")
    env = make_env(EpisodeSpec("grid4x4", "peak", ["emergency"], 1000, mode="quick"), {})
    env.record_decisions = True
    try:
        obs, _ = env.reset(seed=1000)
        team.reset(env)
        while env.now < 1200 and team.preemptions == 0:
            obs, *_ = env.step(team.act(env, obs))
        decisions = list(env.decisions)
        n_phases = {tid: inter.n_phases for tid, inter in env.intersections.items()}
    finally:
        env.close()
    assert team.preemptions > 0
    # every executed phase is the shield's decision, and valid
    assert all(0 <= d["executed"] < n_phases[d["agent"]] for d in decisions)
