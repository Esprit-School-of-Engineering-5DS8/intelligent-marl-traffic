from agents.llm.schemas import Directive
from agents.supervisor.directive_layer import DirectiveLayer, DirectiveLayerConfig


def state(axis="NS", time_in_phase=0.0, ns_queue=0, ew_queue=0, in_transition=False):
    return {
        "current_axis": axis,
        "time_in_phase": time_in_phase,
        "in_transition": in_transition,
        "ns_lanes": {"n_0"},
        "ew_lanes": {"e_0"},
        "lane_queues": {"n_0": ns_queue, "e_0": ew_queue},
    }


def bias(ns=1.0, ew=1.0, ttl=30.0, issued=0.0):
    return Directive(tls_id="A", type="bias", ns=ns, ew=ew, ttl_s=ttl, issued_at=issued)


def hold(axis="NS", extra=10.0, ttl=30.0, issued=0.0):
    return Directive(tls_id="A", type="hold", axis=axis, extra_green_s=extra,
                     ttl_s=ttl, issued_at=issued)


def preempt(axis="NS", start=0.0, hold_s=20.0, ttl=30.0, issued=0.0, ev="ev0", eta=5.0,
            phase_index=None):
    return Directive(tls_id="A", type="preempt", axis=axis, start_in_s=start,
                     hold_s=hold_s, ttl_s=ttl, issued_at=issued, ev=ev, eta_s=eta,
                     phase_index=phase_index)


def serve_ped(axis="NS", min_green=10.0, ttl=30.0, issued=0.0):
    return Directive(tls_id="A", type="serve_ped", axis=axis, min_green_s=min_green,
                     ttl_s=ttl, issued_at=issued)


def test_passthrough_without_directives():
    layer = DirectiveLayer()
    assert layer.apply("A", state(), 1, 0.0) == 1
    assert layer.apply("A", state(), 0, 0.0) == 0


def test_bias_overrides_queue_scores():
    layer = DirectiveLayer()
    layer.install([bias(ns=2.0, ew=1.0)], 0.0)
    assert layer.apply("A", state(ns_queue=3, ew_queue=4), 1, 0.0) == 0


def test_neutral_bias_keeps_base():
    layer = DirectiveLayer()
    layer.install([bias()], 0.0)
    assert layer.apply("A", state(ns_queue=1, ew_queue=2), 1, 0.0) == 1
    assert layer.apply("A", state(ns_queue=2, ew_queue=2), 0, 0.0) == 0


def test_bias_expires_with_ttl():
    layer = DirectiveLayer()
    layer.install([bias(ns=2.0, ttl=10.0)], 0.0)
    assert layer.apply("A", state(ns_queue=3, ew_queue=4), 1, 9.0) == 0
    assert layer.apply("A", state(ns_queue=3, ew_queue=4), 1, 10.0) == 1


def test_install_replaces_same_type():
    layer = DirectiveLayer()
    layer.install([bias(ns=0.5)], 0.0)
    layer.install([bias(ns=2.0)], 1.0)
    assert layer.apply("A", state(ns_queue=3, ew_queue=4), 1, 1.0) == 0


def test_preempt_forces_axis_immediately():
    layer = DirectiveLayer()
    layer.install([preempt(axis="EW")], 0.0)
    assert layer.apply("A", state(axis="NS"), 0, 0.0) == 1


def test_preempt_waits_for_start_in():
    layer = DirectiveLayer()
    layer.install([preempt(axis="EW", start=10.0, hold_s=20.0)], 0.0)
    assert layer.apply("A", state(axis="NS"), 0, 5.0) == 0
    assert layer.apply("A", state(axis="NS"), 0, 10.0) == 1


def test_preempt_expires_after_hold_window():
    layer = DirectiveLayer()
    layer.install([preempt(axis="EW", start=0.0, hold_s=15.0)], 0.0)
    assert layer.apply("A", state(axis="NS"), 0, 14.0) == 1
    assert layer.apply("A", state(axis="NS"), 0, 15.0) == 0


def test_preempt_earliest_eta_wins_and_next_takes_over():
    layer = DirectiveLayer()
    layer.install([
        preempt(axis="NS", eta=20.0, hold_s=20.0, ev="ev_far"),
        preempt(axis="EW", eta=5.0, hold_s=5.0, ev="ev_close"),
    ], 0.0)
    assert layer.apply("A", state(axis="NS"), 0, 0.0) == 1
    assert layer.apply("A", state(axis="NS"), 0, 6.0) == 0


def test_hold_blocks_switch_until_extra_green_elapsed():
    layer = DirectiveLayer()
    layer.install([hold(axis="NS", extra=10.0)], 0.0)
    assert layer.apply("A", state(axis="NS", time_in_phase=5), 1, 0.0) == 0
    assert layer.apply("A", state(axis="NS", time_in_phase=6), 1, 1.0) == 0
    assert layer.apply("A", state(axis="NS", time_in_phase=15), 1, 10.0) == 1


def test_hold_respects_green_cap():
    layer = DirectiveLayer()
    layer.install([hold(axis="NS", extra=20.0)], 0.0)
    assert layer.apply("A", state(axis="NS", time_in_phase=44), 1, 1.0) == 0
    assert layer.apply("A", state(axis="NS", time_in_phase=45), 1, 2.0) == 1


def test_hold_wrong_axis_ignored():
    layer = DirectiveLayer()
    layer.install([hold(axis="EW")], 0.0)
    assert layer.apply("A", state(axis="NS", time_in_phase=5), 0, 0.0) == 0
    assert layer.apply("A", state(axis="NS", time_in_phase=5), 1, 0.0) == 1


def test_priority_preempt_over_everything():
    layer = DirectiveLayer()
    layer.install([
        bias(ns=2.0),
        hold(axis="NS", extra=20.0),
        serve_ped(axis="NS", min_green=10.0),
        preempt(axis="EW"),
    ], 0.0)
    assert layer.apply("A", state(axis="NS", time_in_phase=5, ns_queue=5, ew_queue=1), 0, 0.0) == 1


def test_serve_ped_forces_window_when_other_axis():
    layer = DirectiveLayer()
    layer.install([serve_ped(axis="EW", min_green=10.0)], 0.0)
    assert layer.apply("A", state(axis="NS", time_in_phase=5), 0, 0.0) == 1


def test_serve_ped_blocks_on_matching_axis():
    layer = DirectiveLayer()
    layer.install([serve_ped(axis="NS", min_green=10.0)], 0.0)
    assert layer.apply("A", state(axis="NS", time_in_phase=5), 1, 2.0) == 0
    assert layer.apply("A", state(axis="NS", time_in_phase=6), 1, 10.0) == 1


def test_starvation_guard_drops_and_cools_down():
    layer = DirectiveLayer(DirectiveLayerConfig(max_red_s=5.0, starvation_cooldown_s=10.0))
    actions = []
    for t in range(7):
        layer.install([bias(ns=2.0)], float(t))
        actions.append(layer.apply(
            "A", state(axis="EW", time_in_phase=1, ns_queue=3, ew_queue=4), 1, float(t)))
    assert actions[4] == 0
    assert actions[5] == 1
    assert actions[6] == 1
    events = layer.drain_events()
    assert len(events) == 1 and events[0]["kind"] == "starvation_guard"

    layer.install([bias(ns=2.0)], 15.0)
    assert layer.apply("A", state(axis="EW", time_in_phase=1, ns_queue=3, ew_queue=4), 1, 15.0) == 0


def test_preempt_extends_guard_cap():
    layer = DirectiveLayer(DirectiveLayerConfig(
        max_red_s=5.0, preempt_extension_s=5.0, starvation_cooldown_s=1.0))
    actions = []
    for t in range(12):
        layer.install([preempt(axis="NS", hold_s=20.0)], float(t))
        actions.append(layer.apply("A", state(axis="EW"), 1, float(t)))
    assert all(action == 0 for action in actions[:10])
    assert actions[10] == 1
    assert layer.drain_events()[0]["cap_s"] == 10.0


def test_guard_does_not_track_agreeing_base():
    layer = DirectiveLayer(DirectiveLayerConfig(max_red_s=2.0, starvation_cooldown_s=10.0))
    for t in range(5):
        layer.install([preempt(axis="NS", hold_s=20.0)], float(t))
        assert layer.apply("A", state(axis="NS"), 0, float(t)) == 0
    assert layer.drain_events() == []


# ── N-phase programs: one axis can own several green groups ────────────────
#
# Actions: 0 = N set (NS), 1 = E set (EW), 2 = S set (NS). The base policy may
# address any group; directives address axes, with an optional phase_index
# (pinned by the code-side reviewer) for the exact group.

def three_group_state(axis="NS", current_phase=0, time_in_phase=0.0,
                      queues=(0, 5, 7)):
    return {
        "current_axis": axis,
        "current_phase": current_phase,
        "time_in_phase": time_in_phase,
        "in_transition": False,
        "ns_lanes": {"n_0", "s_0"},
        "ew_lanes": {"e_0"},
        "group_lanes": (frozenset({"n_0"}), frozenset({"e_0"}), frozenset({"s_0"})),
        "group_phases": ((0,), (2,), (4,)),
        "axis_by_action": ("NS", "EW", "NS"),
        "lane_queues": {"n_0": queues[0], "e_0": queues[1], "s_0": queues[2]},
    }


def test_bias_scores_every_group_of_an_axis():
    layer = DirectiveLayer()
    layer.install([bias(ns=2.0, ew=1.0)], 0.0)
    # Raw queues would pick action 2 (s_0: 7); the NS x2 bias makes it 14 vs
    # 4 for EW, and 0 for the N group.
    assert layer.apply("A", three_group_state(queues=(0, 4, 7)), 1, 0.0) == 2
    # Neutral factor with the EW group leading still picks EW.
    layer.install([bias()], 0.0)
    assert layer.apply("A", three_group_state(queues=(1, 9, 2)), 0, 0.0) == 1


def test_hold_on_axis_with_multiple_groups_keeps_the_current_group():
    layer = DirectiveLayer()
    layer.install([hold(axis="NS", extra=10.0)], 0.0)
    # Current green is the S group (phase 4, action 2) of the NS axis: a hold
    # must keep that group, not force a switch to the N canonical phase.
    assert layer.apply("A", three_group_state(current_phase=4, time_in_phase=5), 1, 0.0) == 2
    # After the window elapses the base action passes through.
    assert layer.apply("A", three_group_state(current_phase=4, time_in_phase=15), 1, 10.0) == 1


def test_preempt_phase_index_targets_the_exact_group():
    layer = DirectiveLayer()
    layer.install([preempt(axis="NS", phase_index=2, start=0.0, hold_s=20.0)], 0.0)
    assert layer.apply("A", three_group_state(axis="EW"), 1, 0.0) == 2


def test_preempt_phase_index_inconsistent_with_axis_is_ignored():
    layer = DirectiveLayer()
    # phase_index 1 belongs to EW, the directive claims NS: fall back to the
    # first NS group (action 0), never the mismatching group.
    layer.install([preempt(axis="NS", phase_index=1, start=0.0, hold_s=20.0)], 0.0)
    assert layer.apply("A", three_group_state(axis="EW"), 1, 0.0) == 0
