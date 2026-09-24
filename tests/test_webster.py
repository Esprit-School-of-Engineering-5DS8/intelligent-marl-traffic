import pytest

from cotraffic.controllers.programs import webster_plan

ARGS = {
    "yellow": 3.0,
    "startup_lost": 2.0,
    "min_green": 10.0,
    "min_cycle": 40.0,
    "max_cycle": 120.0,
}


def test_webster_cycle_formula():
    # L = 2 x (3 + 2) = 10 s, Y = 0.6 -> C0 = (1.5 * 10 + 5) / 0.4 = 50 s
    plan = webster_plan([0.4, 0.2], **ARGS)
    assert plan.cycle == pytest.approx(50.0)
    # effective green 40 s split 2:1, plus the start-up loss
    assert plan.greens == pytest.approx((40 * 2 / 3 + 2, 40 / 3 + 2))


def test_light_demand_gives_the_minimum_cycle():
    plan = webster_plan([0.05, 0.05], **ARGS)
    assert plan.cycle == pytest.approx(40.0)
    assert plan.greens[0] == pytest.approx(plan.greens[1])


def test_oversaturated_intersection_uses_the_maximum_cycle():
    plan = webster_plan([0.6, 0.5], **ARGS)
    assert plan.cycle == pytest.approx(120.0)


def test_minimum_green_is_enforced():
    plan = webster_plan([0.7, 0.01], **ARGS)
    assert min(plan.greens) >= 10.0
    assert plan.cycle == pytest.approx(sum(plan.greens) + 2 * 3.0)


def test_no_flow_splits_evenly():
    plan = webster_plan([0.0, 0.0, 0.0], **ARGS)
    assert len(set(plan.greens)) == 1
