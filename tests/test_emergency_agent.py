import json

from agents.llm.client import LLMError, MockLLM
from agents.llm.emergency_agent import EmergencyAgent
from agents.supervisor.arbiter import Arbiter
from agents.supervisor.directive_layer import DirectiveLayer
from environment.ev import EVState, UpcomingTLS
from environment.snapshot import build_snapshot
from environment.topology import build_topology

PHASES = [(42, "GGrr"), (3, "yyrr"), (42, "rrGG"), (3, "rryy")]
LINKS = [[("n_in_0", "", "")], [("n_in_1", "", "")], [("e_in_0", "", "")], [("e_in_1", "", "")]]
TOPOLOGY = build_topology("T0", PHASES, LINKS)
TOPOLOGIES = {"T0": TOPOLOGY}
TLS_IDS = ["T0"]


def _ev_entry(ev_id="ev_0", link_index=2, distance_m=50.0, speed=10.0, tls="T0"):
    return {"id": ev_id, "edge": "left0T0", "speed": speed,
            "next_tls": [{"tls": tls, "link_index": link_index,
                          "dist_m": distance_m, "eta_s": round(distance_m / speed, 1),
                          "signal": "r"}]}


def _state(phase="NS"):
    return {"phase": phase, "time_in_phase_s": 5.0,
            "queue": {"ns": 2, "ew": 7}, "wait_s": {"ns": 1.0, "ew": 9.0}}


def _snapshot(evs=None, queues=None, phase="NS"):
    if evs is None:
        evs = [_ev_entry()]
    state = _state(phase)
    if queues is not None:
        state["queue"] = dict(queues)
    return {
        "t": 100.0,
        "intersections": {"T0": state},
        "alerts": [],
        "evs": evs,
        "blackboard": [],
    }


def _sequenced_responder(*replies):
    """Responder that returns one reply per call, repeating the last one."""
    calls = {"n": 0}

    def responder(system, user, schema):
        reply = replies[min(calls["n"], len(replies) - 1)]
        calls["n"] += 1
        return reply

    return responder


def _preempt(tls="T0", phase="EW", ev="ev_0", start=0, hold=18, eta=None, ttl=None):
    directive = {"tls": tls, "type": "preempt", "phase": phase, "ev": ev,
                 "start_in_s": start, "hold_s": hold}
    if eta is not None:
        directive["eta_s"] = eta
    if ttl is not None:
        directive["ttl_s"] = ttl
    return directive


def _make(responder=None, **kwargs):
    kwargs.setdefault("topologies", TOPOLOGIES)
    return EmergencyAgent(MockLLM(responder), **kwargs)


def _install(agent, call, t, states=None):
    arbiter = Arbiter(TLS_IDS)
    layer = DirectiveLayer()
    result = arbiter.submit("emergency", call.envelope, t,
                            states or {"T0": _state()})
    layer.install(result.accepted, t)
    return result, layer


def test_prompt_enriches_corridor_with_axis_and_queues():
    captured = {}

    def responder(system, user, schema):
        captured["user"] = user
        return {"directives": [], "alerts": [], "explanation": ""}

    agent = _make(responder)
    agent.ask(100.0, _snapshot())
    message = json.loads(captured["user"])
    ev = message["snapshot"]["evs"][0]
    assert ev["id"] == "ev_0" and ev["speed"] == 10.0
    assert message["snapshot"]["lead_time_s"] == 15.0

    corridor = ev["corridor"][0]
    assert corridor["needed_phase"] == "EW"      # link 2 is green in EW phase
    assert corridor["current_phase"] == "NS"
    assert corridor["queue_needed"] == 7 and corridor["queue_other"] == 2
    assert corridor["eta_s"] == 5.0


def test_review_rewrites_phase_eta_lead_and_coverage():
    def responder(system, user, schema):
        return {"directives": [_preempt(phase="NS", start=12, hold=5)],
                "alerts": [], "explanation": "go"}

    agent = _make(responder)
    snapshot = _snapshot(evs=[_ev_entry(distance_m=200.0)], queues={"ns": 2, "ew": 0})
    call = agent.ask(100.0, snapshot)
    directive = call.envelope["directives"][0]
    assert directive["phase"] == "EW"            # EV approach, not the model's NS
    assert directive["eta_s"] == 20.0
    assert directive["start_in_s"] == 5.0        # 12 clamped down to eta - lead_time
    assert directive["hold_s"] == 23.0           # eta - start + margin
    assert directive["ttl_s"] == 33.0            # start + hold + 5
    assert call.review["source"] == "llm"
    assert call.review["schedule"][0]["start_s"] == 5.0

    result, _ = _install(agent, call, 100.0)
    assert len(result.accepted) == 1 and result.rejected == []
    assert result.accepted[0].axis == "EW" and result.accepted[0].eta_s == 20.0


def test_queue_ahead_advances_start():
    def responder(system, user, schema):
        return {"directives": [_preempt(start=40, hold=5)],
                "alerts": [], "explanation": ""}

    agent = _make(responder, rule_fallback=False)
    snapshot = _snapshot(evs=[_ev_entry(distance_m=200.0)], queues={"ns": 2, "ew": 3})
    call = agent.ask(100.0, snapshot)
    directive = call.envelope["directives"][0]
    # 3 queued vehicles need ~6 s discharge: start = max(0, 20 - 15 - 6) = 0
    assert directive["start_in_s"] == 0.0
    assert directive["hold_s"] == 28.0           # eta - 0 + 8


def test_review_keeps_early_start_but_caps_at_zero():
    def responder(system, user, schema):
        return {"directives": [_preempt(start=0, hold=30)],
                "alerts": [], "explanation": ""}

    agent = _make(responder, rule_fallback=False)
    snapshot = _snapshot(evs=[_ev_entry(distance_m=200.0)], queues={"ns": 2, "ew": 0})
    call = agent.ask(100.0, snapshot)
    directive = call.envelope["directives"][0]
    assert directive["start_in_s"] == 0.0        # never later than the lead limit
    assert directive["hold_s"] == 30.0           # model hold above the coverage floor


def test_review_drops_hallucinated_and_far_preempts():
    def responder(system, user, schema):
        return {"directives": [
            _preempt(tls="T9", hold=10),
            _preempt(ev="ev_ghost", hold=10),
        ], "alerts": [], "explanation": ""}

    agent = _make(responder, rule_fallback=False)
    call = agent.ask(100.0, _snapshot())
    assert call.envelope["directives"] == []
    assert any("non-corridor" in note for note in call.review["notes"])


def test_review_drops_preempt_beyond_horizon():
    def responder(system, user, schema):
        return {"directives": [_preempt(hold=30)],
                "alerts": [], "explanation": ""}

    agent = _make(responder, rule_fallback=False)
    snapshot = _snapshot(evs=[_ev_entry(distance_m=400.0)])
    call = agent.ask(100.0, snapshot)
    assert call.envelope["directives"] == []
    assert any("horizon" in note for note in call.review["notes"])


def test_review_passes_release_for_active_ev():
    def responder(system, user, schema):
        return {"directives": [_preempt(hold=0)],
                "alerts": [], "explanation": "release"}

    agent = _make(responder, rule_fallback=False)
    snapshot = _snapshot()
    snapshot["evs"][0]["next_tls"] = []          # EV passed T0 already
    call = agent.ask(100.0, snapshot)
    assert len(call.envelope["directives"]) == 1
    assert call.envelope["directives"][0]["hold_s"] == 0


def test_grace_keeps_plan_while_ev_invisible():
    agent = _make(_sequenced_responder(
        {"directives": [_preempt(hold=18)], "alerts": [], "explanation": ""},
        {"directives": [], "alerts": [], "explanation": ""},
    ))
    first = agent.ask(100.0, _snapshot(evs=[_ev_entry(distance_m=100.0)]))
    assert len(first.envelope["directives"]) == 1

    # t=104, EV on an internal lane: invisible in the snapshot. The plan must
    # survive the grace window instead of being dropped as non-corridor.
    second = agent.ask(104.0, _snapshot(evs=[]))
    assert len(second.envelope["directives"]) == 1
    directive = second.envelope["directives"][0]
    assert directive["tls"] == "T0" and directive["ev"] == "ev_0"
    assert directive["hold_s"] >= 14.0           # covers the estimated ETA 6 + 8
    assert not any("non-corridor" in note for note in second.review["notes"])


def test_auto_release_when_ev_finished():
    agent = _make(_sequenced_responder(
        {"directives": [_preempt(hold=18)], "alerts": [], "explanation": ""},
        {"directives": [], "alerts": [], "explanation": ""},
    ))
    agent.ask(100.0, _snapshot(evs=[_ev_entry(distance_m=100.0)]))
    call = agent.ask(110.0, _snapshot(evs=[]))   # beyond the 6 s grace
    releases = [d for d in call.envelope["directives"] if d.get("hold_s") == 0]
    assert releases and releases[0]["ev"] == "ev_0"
    assert agent._plan == {}


def test_conflict_sequences_later_ev():
    def responder(system, user, schema):
        return {"directives": [
            _preempt(phase="EW", ev="ev_0", start=0, hold=16),
            _preempt(phase="NS", ev="ev_1", start=5, hold=23),
        ], "alerts": [], "explanation": ""}

    agent = _make(responder)
    snapshot = _snapshot(evs=[_ev_entry("ev_0", 2, 80.0),
                              _ev_entry("ev_1", 0, 200.0)])
    call = agent.ask(100.0, snapshot)
    by_ev = {d["ev"]: d for d in call.envelope["directives"]}
    assert "ev_0" in by_ev and "ev_1" in by_ev
    assert by_ev["ev_0"]["start_in_s"] == 0.0
    assert by_ev["ev_1"]["start_in_s"] == 16.0    # ev_0's window ends at 16
    assert any("delayed" in note for note in call.review["notes"])

    result, layer = _install(agent, call, 100.0)
    assert len(result.accepted) == 2
    assert layer.apply("T0", _state("NS"), base_action=0, t=105.0) == 1  # EW for ev_0
    assert layer.apply("T0", _state("NS"), base_action=0, t=125.0) == 0  # NS for ev_1


def test_same_phase_conflict_not_delayed():
    def responder(system, user, schema):
        return {"directives": [
            _preempt(phase="EW", ev="ev_0", start=0, hold=16),
            _preempt(phase="EW", ev="ev_1", start=5, hold=23),
        ], "alerts": [], "explanation": ""}

    agent = _make(responder)
    snapshot = _snapshot(evs=[_ev_entry("ev_0", 2, 80.0),
                              _ev_entry("ev_1", 2, 200.0)],
                         queues={"ns": 0, "ew": 0})
    call = agent.ask(100.0, snapshot)
    by_ev = {d["ev"]: d for d in call.envelope["directives"]}
    assert by_ev["ev_1"]["start_in_s"] == 5.0     # same phase, no conflict


def test_scheduled_window_survives_next_tick():
    agent = _make(_sequenced_responder(
        {"directives": [
            _preempt(phase="EW", ev="ev_0", start=0, hold=16),
            _preempt(phase="NS", ev="ev_1", start=5, hold=23),
        ], "alerts": [], "explanation": ""},
        {"directives": [], "alerts": [], "explanation": ""},
    ))
    swarm = _snapshot(evs=[_ev_entry("ev_0", 2, 80.0), _ev_entry("ev_1", 0, 200.0)])
    agent.ask(100.0, swarm)

    # t=110: ev_0 has passed (only ev_1 visible) and the model proposes
    # nothing. The scheduled ev_1 window (start 116) must be preserved and
    # ev_0's open preempt released.
    later = _snapshot(evs=[_ev_entry("ev_1", 0, 100.0)])
    call = agent.ask(110.0, later)
    by_ev = {d["ev"]: d for d in call.envelope["directives"]}
    assert by_ev["ev_1"]["start_in_s"] == 6.0     # 116 - 110, not restarted at 0
    assert any(d["ev"] == "ev_0" and d.get("hold_s") == 0
               for d in call.envelope["directives"])


def test_rule_fallback_when_model_returns_nothing():
    agent = _make()  # default mock responder: empty directives
    call = agent.ask(100.0, _snapshot())
    directives = call.envelope["directives"]
    assert len(directives) == 1
    directive = directives[0]
    assert directive["tls"] == "T0" and directive["phase"] == "EW"
    assert directive["ev"] == "ev_0" and directive["eta_s"] == 5.0
    assert directive["hold_s"] == 13.0            # eta + margin 8
    assert call.review["source"] == "rules"
    corridors = [a for a in call.envelope["alerts"] if a["kind"] == "ev_corridor"]
    assert corridors == [{"kind": "ev_corridor", "ev": "ev_0", "tls": ["T0"]}]


def test_rule_fallback_after_llm_failure():
    def boom(system, user, schema):
        raise LLMError("backend down")

    agent = _make(boom)
    call = agent.ask(100.0, _snapshot())
    assert call.failed and "backend down" in call.error
    assert call.attempts == 2
    assert len(call.envelope["directives"]) == 1
    assert call.review["source"] == "rules"


def test_no_rules_configured_means_no_fallback():
    agent = _make(rule_fallback=False)
    call = agent.ask(100.0, _snapshot())
    assert call.envelope["directives"] == []
    assert call.review["source"] == "llm"


def test_fallback_directive_forces_ev_axis_through_layer():
    agent = _make()
    call = agent.ask(100.0, _snapshot(phase="NS"))
    result, layer = _install(agent, call, 100.0)
    assert result.accepted and result.rejected == []
    assert layer.apply("T0", _state("NS"), base_action=0, t=100.0) == 1


def test_evstates_reconstruction_round_trips_snapshot():
    ev = EVState("ev_0", "left0T0", "left0T0_0", 10.0,
                 (UpcomingTLS("T0", 2, 50.0, "r"),))
    snapshot = build_snapshot(0.0, _snapshot()["intersections"], evs=[ev])
    states = EmergencyAgent._evstates(snapshot)
    assert states[0].veh_id == "ev_0"
    assert states[0].speed_m_s == 10.0
    assert states[0].next_tls[0].tls_id == "T0"
    assert states[0].next_tls[0].link_index == 2
    assert states[0].next_tls[0].distance_m == 50.0


# ── N-phase programs: exact group pinning and same-axis sequencing ─────────

THREE_PHASES = [
    (30, "GGrrrr"), (3, "yyrrrr"),
    (30, "rrGGrr"), (3, "rryyrr"),
    (30, "rrrrGG"), (3, "rrrryy"),
]
THREE_LINKS = [[("n_in_0", "", "")], [("n_in_1", "", "")],
               [("e_in_0", "", "")], [("e_in_1", "", "")],
               [("s_in_0", "", "")], [("w_in_0", "", "")]]
THREE_HEADINGS = {
    "n_in_0": (0.0, 1.0), "n_in_1": (0.0, 1.0),
    "e_in_0": (1.0, 0.0), "e_in_1": (1.0, 0.0),
    "s_in_0": (0.0, -1.0), "w_in_0": (-1.0, 0.0),
}
# groups: 0 = N set (NS), 1 = E set (EW), 2 = {S,W} set (NS)
THREE_TOPOLOGY = build_topology("T0", THREE_PHASES, THREE_LINKS, THREE_HEADINGS)
THREE_TOPOLOGIES = {"T0": THREE_TOPOLOGY}


def _multi_group_state(current_phase=0):
    return {
        "current_axis": "NS" if current_phase in (0, 4) else None,
        "current_phase": current_phase,
        "time_in_phase": 5.0,
        "in_transition": False,
        "ns_lanes": {"n_in_0", "s_in_0"},
        "ew_lanes": {"e_in_0"},
        "group_lanes": (frozenset({"n_in_0"}), frozenset({"e_in_0"}), frozenset({"s_in_0", "w_in_0"})),
        "group_phases": ((0,), (2,), (4,)),
        "axis_by_action": ("NS", "EW", "NS"),
        "lane_queues": {"n_in_0": 1, "e_in_0": 0, "s_in_0": 2, "w_in_0": 0},
        "lane_waiting": {"n_in_0": 5.0, "e_in_0": 0.0, "s_in_0": 10.0, "w_in_0": 0.0},
    }


def test_reviewer_pins_phase_index_for_multi_group_axes():
    def responder(system, user, schema):
        return {"directives": [_preempt(phase="EW", start=0, hold=18)],
                "alerts": [], "explanation": ""}

    agent = EmergencyAgent(MockLLM(responder), topologies=THREE_TOPOLOGIES)
    # link 4 is s_in_0: NS axis, group 2 of the program.
    snapshot = _snapshot(evs=[_ev_entry(link_index=4, distance_m=80.0)])
    call = agent.ask(100.0, snapshot)
    directive = call.envelope["directives"][0]
    assert directive["phase"] == "NS"
    assert directive["phase_index"] == 2
    assert any("phase" in note for note in call.review["notes"])
    assert call.review["schedule"][0]["phase_index"] == 2

    result, layer = _install(agent, call, 100.0,
                             states={"T0": _multi_group_state()})
    assert result.accepted and result.rejected == []
    assert layer.apply("T0", _multi_group_state(), base_action=0, t=100.0) == 2


def test_conflict_sequenced_across_groups_of_the_same_axis():
    def responder(system, user, schema):
        return {"directives": [
            _preempt(phase="NS", ev="ev_0", start=0, hold=16),
            _preempt(phase="NS", ev="ev_1", start=5, hold=23),
        ], "alerts": [], "explanation": ""}

    agent = EmergencyAgent(MockLLM(responder), topologies=THREE_TOPOLOGIES)
    snapshot = _snapshot(evs=[_ev_entry("ev_0", 4, 80.0),   # S approach, group 2
                              _ev_entry("ev_1", 0, 200.0)])  # N approach, group 0
    call = agent.ask(100.0, snapshot)
    by_ev = {d["ev"]: d for d in call.envelope["directives"]}
    # Same axis name but different green groups -> the TLS can only run one,
    # so the later EV is sequenced after the earlier window (16 s).
    assert by_ev["ev_0"]["phase_index"] == 2
    assert by_ev["ev_1"]["phase_index"] == 0
    assert by_ev["ev_0"]["start_in_s"] == 0.0
    assert by_ev["ev_1"]["start_in_s"] == 16.0
    assert any("delayed" in note for note in call.review["notes"])
