from agents.llm.client import LLMError, MockLLM
from agents.llm.pedestrian_agent import PedestrianAgent
from agents.supervisor.arbiter import Arbiter
from agents.supervisor.directive_layer import DirectiveLayer

TLS_IDS = ["A1", "B1"]


def _ped(tls="A1", axis="NS", waiting=4, max_wait=22.0, mean_wait=10.0):
    return {"tls": tls, "axis": axis, "waiting": waiting,
            "max_wait_s": max_wait, "mean_wait_s": mean_wait}


def _snapshot(pedestrians=None):
    snapshot = {
        "t": 100.0,
        "intersections": {
            "A1": {"phase": "NS", "time_in_phase_s": 5.0,
                   "queue": {"ns": 6, "ew": 3}, "wait_s": {"ns": 40.0, "ew": 12.0}},
        },
        "alerts": [],
        "evs": [],
        "blackboard": [],
    }
    if pedestrians is not None:
        snapshot["pedestrians"] = pedestrians
    return snapshot


def _make(responder=None, **kwargs):
    return PedestrianAgent(MockLLM(responder), **kwargs)


def _state(axis="NS"):
    return {"current_axis": axis, "time_in_phase": 5.0, "in_transition": False,
            "ns_lanes": {"n0"}, "ew_lanes": {"e0"},
            "lane_queues": {"n0": 6, "e0": 3}, "lane_waiting": {}}


def test_valid_serve_ped_gets_floor_and_ttl():
    def responder(system, user, schema):
        return {"directives": [{"tls": "A1", "type": "serve_ped", "phase": "NS",
                                "min_green_s": 2, "ttl_s": 5}],
                "alerts": [], "explanation": "people waiting"}

    agent = _make(responder)
    call = agent.ask(100.0, _snapshot([_ped()]))
    directive = call.envelope["directives"][0]
    assert directive["min_green_s"] == 15.0         # floored to a crossable window
    assert directive["ttl_s"] == 25.0               # min_green + 10
    assert call.review["source"] == "llm"


def test_hallucinated_or_empty_crossings_dropped():
    def responder(system, user, schema):
        return {"directives": [
            {"tls": "A1", "type": "serve_ped", "phase": "EW", "min_green_s": 12},
            {"tls": "B1", "type": "serve_ped", "phase": "NS", "min_green_s": 12},
        ], "alerts": [], "explanation": ""}

    agent = _make(responder, rule_fallback=False)
    call = agent.ask(100.0, _snapshot([_ped()]))    # only A1/NS has waiters
    assert call.envelope["directives"] == []
    assert any("no pedestrians" in note for note in call.review["notes"])


def test_zero_waiting_group_not_served():
    def responder(system, user, schema):
        return {"directives": [{"tls": "A1", "type": "serve_ped", "phase": "NS",
                                "min_green_s": 12}], "alerts": [], "explanation": ""}

    agent = _make(responder, rule_fallback=False)
    call = agent.ask(100.0, _snapshot([_ped(waiting=0)]))
    assert call.envelope["directives"] == []


def test_rule_fallback_serves_longest_wait():
    agent = _make()  # default mock: empty directives
    call = agent.ask(100.0, _snapshot([
        _ped("A1", "NS", waiting=6, max_wait=25.0),
        _ped("B1", "EW", waiting=3, max_wait=17.0),
        _ped("B1", "NS", waiting=1, max_wait=9.0),
    ]))
    directives = call.envelope["directives"]
    assert [(d["tls"], d["phase"]) for d in directives] == [("A1", "NS"), ("B1", "EW")]
    assert call.review["source"] == "rules"
    assert all(d["min_green_s"] == 18.0 for d in directives)


def test_rule_fallback_ignores_short_waits():
    agent = _make()
    call = agent.ask(100.0, _snapshot([_ped("A1", "NS", waiting=2, max_wait=9.0)]))
    assert call.envelope["directives"] == []
    assert call.review["source"] == "llm"


def test_failure_falls_back_to_rules():
    def boom(system, user, schema):
        raise LLMError("backend down")

    agent = _make(boom)
    call = agent.ask(100.0, _snapshot([_ped("A1", "NS", waiting=5, max_wait=21.0)]))
    assert call.failed and call.attempts == 2
    assert len(call.envelope["directives"]) == 1
    assert call.review["source"] == "rules"


def test_ped_surge_published_for_long_waits():
    agent = _make(rule_fallback=False)
    call = agent.ask(100.0, _snapshot([
        _ped("A1", "NS", waiting=5, max_wait=24.0),
        _ped("B1", "EW", waiting=2, max_wait=8.0),
    ]))
    surges = [a for a in call.envelope["alerts"] if a["kind"] == "ped_surge"]
    assert surges == [{"kind": "ped_surge", "tls": "A1", "axis": "NS",
                       "waiting": 5, "max_wait_s": 24.0}]


def test_serve_ped_flows_through_arbiter_and_layer():
    def responder(system, user, schema):
        return {"directives": [{"tls": "A1", "type": "serve_ped", "phase": "NS",
                                "min_green_s": 12}], "alerts": [], "explanation": ""}

    agent = _make(responder)
    call = agent.ask(100.0, _snapshot([_ped()]))
    arbiter = Arbiter(TLS_IDS)
    layer = DirectiveLayer()
    result = arbiter.submit("pedestrian", call.envelope, 100.0, {"A1": _state()})
    assert len(result.accepted) == 1 and result.rejected == []
    layer.install(result.accepted, 100.0)
    # The base policy wants to switch away, the owed window blocks it.
    assert layer.apply("A1", _state("NS"), base_action=1, t=102.0) == 0
    assert layer.apply("A1", _state("NS"), base_action=1, t=115.0) == 1
