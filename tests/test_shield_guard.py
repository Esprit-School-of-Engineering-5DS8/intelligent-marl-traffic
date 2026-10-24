"""Spillback guard and detector recall (FAILURES F-012, F-014)."""

from cotraffic.controllers.registry import GUARD_OPTIONS, base_method, make_controller
from cotraffic.envs.shield import MIN_GREEN, SPILLBACK, ShieldConfig, ShieldState, apply_shield

PHASES = [frozenset({0, 1}), frozenset({2, 3})]
OFF = ShieldConfig(min_green=10, max_green=60, max_red=90)
ON = ShieldConfig(min_green=10, max_green=60, max_red=90, spillback=0.8)


def state(demand, blocked=(), current=0, elapsed=20.0, phase_demand=(1.0, 1.0)):
    return ShieldState(
        current_phase=current,
        green_elapsed=elapsed,
        phase_links=PHASES,
        link_red_time={},
        links_with_demand=frozenset(demand),
        phase_demand=list(phase_demand),
        blocked_links=frozenset(blocked),
    )


def test_off_by_default_keeps_the_request():
    s = state(demand={0, 2}, blocked={0})
    assert apply_shield(0, s, OFF).phase == 0


def test_a_green_into_blocked_exits_is_moved_to_a_phase_that_can_flow():
    decision = apply_shield(0, state(demand={0, 2}, blocked={0}), ON)
    assert (decision.phase, decision.reason) == (1, SPILLBACK)


def test_no_switch_when_the_phase_still_moves_someone():
    assert apply_shield(0, state(demand={0, 1, 2}, blocked={0}), ON).phase == 0


def test_no_switch_when_every_phase_is_blocked():
    assert apply_shield(0, state(demand={0, 2}, blocked={0, 2}), ON).phase == 0


def test_minimum_green_comes_first():
    decision = apply_shield(1, state(demand={0, 2}, blocked={2}, elapsed=3.0), ON)
    assert (decision.phase, decision.reason) == (0, MIN_GREEN)


def test_guard_variants_reuse_the_base_controller():
    assert base_method("coop_full_guard") == "coop_full"
    mp = make_controller("mp_guard")
    assert mp.name == "mp_guard" and mp.agent_cfg["shield"] == GUARD_OPTIONS
    cfg = ShieldConfig.from_timing({"min_green": 10, "max_green": 60, "max_red": 90}, GUARD_OPTIONS)
    assert cfg.spillback == 0.8 and cfg.recall_failed
