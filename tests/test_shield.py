import itertools

import pytest

from cotraffic.envs.shield import (
    INVALID,
    MAX_GREEN,
    MIN_GREEN,
    STARVATION,
    ShieldConfig,
    ShieldState,
    apply_shield,
)

CFG = ShieldConfig(min_green=10, max_green=60, max_red=90)
# two-phase intersection: phase 0 serves links 0-1 (north-south), phase 1 serves links 2-3
PHASES = (frozenset({0, 1}), frozenset({2, 3}))


def state(current=0, elapsed=20.0, red=None, demand=(), phase_demand=(5.0, 5.0), phases=PHASES):
    return ShieldState(
        current_phase=current,
        green_elapsed=elapsed,
        phase_links=phases,
        link_red_time=red or {},
        links_with_demand=frozenset(demand),
        phase_demand=phase_demand,
    )


def test_passes_through_a_legal_switch():
    d = apply_shield(1, state(elapsed=15), CFG)
    assert d.phase == 1 and not d.intervened


def test_keeps_phase_before_min_green():
    d = apply_shield(1, state(elapsed=9.9), CFG)
    assert d.phase == 0 and d.reason == MIN_GREEN


def test_keeping_the_phase_before_min_green_is_not_an_intervention():
    d = apply_shield(0, state(elapsed=2), CFG)
    assert d.phase == 0 and d.reason is None


@pytest.mark.parametrize("bad", [-1, 2, 7])
def test_invalid_action_keeps_current_phase(bad):
    d = apply_shield(bad, state(current=1, elapsed=30), CFG)
    assert d.phase == 1 and d.reason == INVALID


def test_max_green_switches_to_the_phase_with_most_demand():
    phases = (frozenset({0}), frozenset({1}), frozenset({2}))
    d = apply_shield(0, state(elapsed=60, phases=phases, phase_demand=(9, 2, 4)), CFG)
    assert d.phase == 2 and d.reason == MAX_GREEN


def test_max_green_does_not_switch_to_an_empty_intersection():
    d = apply_shield(0, state(elapsed=200, phase_demand=(3.0, 0.0)), CFG)
    assert d.phase == 0 and not d.intervened


def test_starvation_forces_the_starved_movement():
    s = state(current=0, elapsed=30, red={2: 95.0, 3: 95.0}, demand={2})
    d = apply_shield(0, s, CFG)
    assert d.phase == 1 and d.reason == STARVATION


def test_starvation_ignores_movements_without_demand():
    d = apply_shield(0, state(elapsed=30, red={2: 500.0}, demand=()), CFG)
    assert d.phase == 0 and not d.intervened


def test_starvation_respects_min_green():
    d = apply_shield(0, state(elapsed=5, red={2: 500.0}, demand={2}), CFG)
    assert d.phase == 0


def test_starvation_accepts_a_request_that_already_serves_the_movement():
    phases = (frozenset({0}), frozenset({1, 2}), frozenset({2}))
    s = state(elapsed=30, phases=phases, red={2: 120.0}, demand={2}, phase_demand=(1, 1, 1))
    d = apply_shield(2, s, CFG)
    assert d.phase == 2 and not d.intervened


def test_starvation_serves_the_longest_waiting_movement_first():
    phases = (frozenset({0}), frozenset({1}), frozenset({2}))
    s = state(
        elapsed=30, phases=phases, red={1: 100.0, 2: 140.0}, demand={1, 2}, phase_demand=(0, 9, 1)
    )
    d = apply_shield(0, s, CFG)
    assert d.phase == 2 and d.reason == STARVATION


def test_links_not_served_by_any_phase_never_trigger_starvation():
    d = apply_shield(0, state(elapsed=30, red={9: 1000.0}, demand={9}), CFG)
    assert d.phase == 0 and not d.intervened


def test_executed_phase_is_always_valid_and_min_green_is_never_violated():
    phases = (frozenset({0, 1}), frozenset({2}), frozenset({3, 4}), frozenset({1, 5}))
    reds = [{}, {2: 100.0}, {3: 91.0, 5: 200.0}, {0: 95.0}]
    demands = [(), (2,), (3, 5), (0, 2, 3)]
    for current, elapsed, requested, red, demand in itertools.product(
        range(4), (0, 5, 10, 30, 60, 90), range(-1, 6), reds, demands
    ):
        s = state(current, elapsed, red, demand, (1, 2, 0, 4), phases)
        d = apply_shield(requested, s, CFG)
        assert 0 <= d.phase < 4
        if elapsed < CFG.min_green:
            assert d.phase == current
