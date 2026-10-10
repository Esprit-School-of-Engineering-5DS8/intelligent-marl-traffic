from environment.ev import EVState, UpcomingTLS
from environment.topology import build_topology

PHASES = [(42, "GGrr"), (3, "yyrr"), (42, "rrGG"), (3, "rryy")]
LINKS = [[("n_in_0", "", "")], [("n_in_1", "", "")], [("e_in_0", "", "")], [("e_in_1", "", "")]]
TOPOLOGY = build_topology("T0", PHASES, LINKS)
TOPOLOGIES = {"T0": TOPOLOGY}


def _ev(veh_id, link_index, distance_m, speed_m_s, tls_id="T0"):
    return EVState(
        veh_id=veh_id,
        edge_id="left0A0",
        lane_id="left0A0_0",
        speed_m_s=speed_m_s,
        next_tls=(UpcomingTLS(tls_id, link_index, distance_m, "r"),),
    )


def _preemption():
    from agents.ev_preemption import RuleBasedEVPreemption
    return RuleBasedEVPreemption(TOPOLOGIES)


def test_forces_ev_axis_when_eta_triggered():
    policy = _preemption()
    ev = _ev("ev_0", link_index=2, distance_m=100.0, speed_m_s=10.0)
    policy.begin_step([ev])
    assert policy.select_action("T0", base_action=0, evs=[ev]) == 1


def test_no_ev_keeps_base_action():
    policy = _preemption()
    policy.begin_step([])
    assert policy.select_action("T0", base_action=0, evs=[]) == 0


def test_far_ev_keeps_base_action():
    policy = _preemption()
    ev = _ev("ev_0", link_index=2, distance_m=400.0, speed_m_s=10.0)
    policy.begin_step([ev])
    assert policy.select_action("T0", base_action=0, evs=[ev]) == 0


def test_stopped_ev_close_forces_axis():
    policy = _preemption()
    ev = _ev("ev_0", link_index=2, distance_m=30.0, speed_m_s=0.0)
    policy.begin_step([ev])
    assert policy.select_action("T0", base_action=0, evs=[ev]) == 1


def test_release_after_ev_passes():
    policy = _preemption()
    ev = _ev("ev_0", link_index=2, distance_m=100.0, speed_m_s=10.0)
    policy.begin_step([ev])
    assert policy.select_action("T0", base_action=0, evs=[ev]) == 1
    passed = EVState(ev.veh_id, ev.edge_id, ev.lane_id, ev.speed_m_s, next_tls=())
    policy.begin_step([passed])
    assert policy.select_action("T0", base_action=0, evs=[passed]) == 0


def test_grace_keeps_preemption_while_ev_unobservable():
    policy = _preemption()
    ev = _ev("ev_0", link_index=2, distance_m=100.0, speed_m_s=10.0)
    policy.begin_step([ev])
    assert policy.select_action("T0", base_action=0, evs=[ev]) == 1

    for _ in range(3):
        policy.begin_step([])
        assert policy.select_action("T0", base_action=0, evs=[]) == 1

    for _ in range(3):
        policy.begin_step([])
    assert policy.select_action("T0", base_action=0, evs=[]) == 0


def test_earliest_eta_wins():
    policy = _preemption()
    close = _ev("ev_close", link_index=2, distance_m=50.0, speed_m_s=10.0)
    far = _ev("ev_far", link_index=0, distance_m=150.0, speed_m_s=10.0)
    policy.begin_step([far, close])
    assert policy.select_action("T0", base_action=0, evs=[far, close]) == 1

    for _ in range(6):
        policy.begin_step([far])
    assert policy.select_action("T0", base_action=0, evs=[far]) == 0


def test_closer_ev_overrides_active_preemption():
    policy = _preemption()
    far = _ev("ev_far", link_index=0, distance_m=150.0, speed_m_s=10.0)
    close = _ev("ev_close", link_index=2, distance_m=50.0, speed_m_s=10.0)
    policy.begin_step([far])
    assert policy.select_action("T0", base_action=1, evs=[far]) == 0
    policy.begin_step([far, close])
    assert policy.select_action("T0", base_action=1, evs=[far, close]) == 1


def test_lookahead_limit_ignores_distant_tls():
    policy = _preemption()
    ev = EVState(
        veh_id="ev_0", edge_id="left0A0", lane_id="left0A0_0", speed_m_s=10.0,
        next_tls=(UpcomingTLS("T1", 0, 50.0, "r"),
                  UpcomingTLS("T2", 0, 100.0, "r"),
                  UpcomingTLS("T3", 0, 150.0, "r"),
                  UpcomingTLS("T0", 2, 100.0, "r")))
    policy.begin_step([ev])
    assert policy.select_action("T0", base_action=0, evs=[ev]) == 0
