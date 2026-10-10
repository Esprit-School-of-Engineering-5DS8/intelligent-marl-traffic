from agents.ev_preemption import RuleBasedEVPreemption
from agents.supervisor.arbiter import Arbiter
from agents.supervisor.directive_layer import DirectiveLayer
from environment.ev import EVState, UpcomingTLS
from environment.topology import build_topology

PHASES = [(42, "GGrr"), (3, "yyrr"), (42, "rrGG"), (3, "rryy")]
LINKS = [[("n_in_0", "", "")], [("n_in_1", "", "")], [("e_in_0", "", "")], [("e_in_1", "", "")]]
TOPOLOGY = build_topology("T0", PHASES, LINKS)
TOPOLOGIES = {"T0": TOPOLOGY}
TLS_IDS = ["T0"]


def _ev(veh_id, link_index, distance_m, speed_m_s, tls_id="T0"):
    return EVState(
        veh_id=veh_id,
        edge_id="left0A0",
        lane_id="left0A0_0",
        speed_m_s=speed_m_s,
        next_tls=(UpcomingTLS(tls_id, link_index, distance_m, "r"),),
    )


def _state(axis="NS"):
    return {
        "current_axis": axis,
        "time_in_phase": 5,
        "in_transition": False,
        "ns_lanes": {"n_in_0", "n_in_1"},
        "ew_lanes": {"e_in_0", "e_in_1"},
        "lane_queues": {},
        "lane_waiting": {},
    }


def test_triggers_within_horizon_only():
    source = RuleBasedEVPreemption(TOPOLOGIES)
    close = source.candidates([_ev("ev_0", 2, 100.0, 10.0)])
    assert len(close) == 1 and close[0].action == 1  # EW link
    assert source.candidates([_ev("ev_0", 2, 400.0, 10.0)]) == []
    assert source.propose([]) == []


def test_reactive_distance_covers_stopped_ev():
    source = RuleBasedEVPreemption(TOPOLOGIES)
    envelope = source.propose([_ev("ev_0", 2, 30.0, 0.0)])[0]
    directive = envelope["directives"][0]
    assert directive["hold_s"] == 38.0  # eta = 30 / 1 m/s floor, + 8 s margin
    assert directive["eta_s"] == 30.0
    assert directive["phase"] == "EW"
    assert directive["ev"] == "ev_0"


def test_best_candidate_per_tls():
    source = RuleBasedEVPreemption(TOPOLOGIES)
    evs = [_ev("ev_close", 2, 50.0, 10.0), _ev("ev_far", 0, 150.0, 10.0)]
    envelope = source.propose(evs, t=7.0)[0]
    assert len(envelope["directives"]) == 1
    directive = envelope["directives"][0]
    assert directive["ev"] == "ev_close"
    assert directive["hold_s"] == 13.0  # eta 5 + margin 8


def test_hold_capped_at_40():
    source = RuleBasedEVPreemption(TOPOLOGIES)
    envelope = source.propose([_ev("ev_0", 2, 35.0, 0.0)])[0]
    assert envelope["directives"][0]["hold_s"] == 40.0  # eta 35 + 8 = 43


def test_proposed_directive_flows_through_arbiter_and_layer():
    source = RuleBasedEVPreemption(TOPOLOGIES)
    arbiter = Arbiter(TLS_IDS)
    layer = DirectiveLayer()
    ev = _ev("ev_0", 2, 100.0, 10.0)
    envelope = source.propose([ev], t=0.0)[0]
    result = arbiter.submit("emergency", envelope, 0.0, {"T0": _state("NS")})
    assert len(result.accepted) == 1 and result.rejected == []
    layer.install(result.accepted, 0.0)
    assert layer.apply("T0", _state("NS"), base_action=0, t=0.0) == 1


def test_release_directive_when_ev_passes():
    source = RuleBasedEVPreemption(TOPOLOGIES)
    arbiter = Arbiter(TLS_IDS)
    layer = DirectiveLayer()
    ev = _ev("ev_0", 2, 100.0, 10.0)
    result = arbiter.submit("emergency", source.propose([ev], t=0.0)[0], 0.0, {"T0": _state("NS")})
    layer.install(result.accepted, 0.0)
    assert layer.apply("T0", _state("NS"), 0, 0.0) == 1

    passed = EVState("ev_0", "right0A0", "right0A0_0", 10.0, next_tls=())
    envelopes = source.propose([passed], t=1.0)
    assert len(envelopes) == 1
    release = envelopes[0]["directives"][0]
    assert release["tls"] == "T0" and release["hold_s"] == 0.0

    result = arbiter.submit("emergency", envelopes[0], 1.0, {"T0": _state("NS")})
    assert len(result.accepted) == 1
    layer.install(result.accepted, 1.0)
    assert layer.apply("T0", _state("NS"), 0, 1.0) == 0


def test_unobservable_ev_keeps_issued_until_grace():
    source = RuleBasedEVPreemption(TOPOLOGIES)
    assert source.propose([_ev("ev_0", 2, 100.0, 10.0)], t=0.0)
    for t in (1.0, 2.0, 3.0, 4.0, 5.0):
        assert source.propose([], t=t) == []
        assert source._issued  # kept during the grace window
    assert source.propose([], t=6.0) == []
    assert source._issued == {}


def test_grace_keeps_preemption_while_ev_unobservable():
    source = RuleBasedEVPreemption(TOPOLOGIES)
    arbiter = Arbiter(TLS_IDS)
    layer = DirectiveLayer()
    ev = _ev("ev_0", 2, 100.0, 10.0)
    envelope = source.propose([ev], t=0.0)[0]
    result = arbiter.submit("emergency", envelope, 0.0, {"T0": _state("NS")})
    layer.install(result.accepted, 0.0)
    assert layer.apply("T0", _state("NS"), 0, 0.0) == 1

    for t in (1.0, 2.0, 3.0):  # EV on internal lanes: no proposals, preempt alive
        assert layer.apply("T0", _state("NS"), 0, t) == 1

    assert layer.apply("T0", _state("NS"), 0, 18.0) == 0  # eta 10 + margin 8 over
