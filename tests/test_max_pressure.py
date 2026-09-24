from types import SimpleNamespace

from cotraffic.controllers.classical import MaxPressure, phase_pressure
from cotraffic.envs.intersection import Link


def make_inter(phase=0):
    links = [
        Link(0, "n_in", "s_out"),  # phase 0
        Link(1, "s_in", "n_out"),  # phase 0
        Link(2, "e_in", "w_out"),  # phase 1
        Link(3, "w_in", "e_out"),  # phase 1
        Link(4, "wa", "cross", "cross"),  # crossing, ignored by the pressure
    ]
    return SimpleNamespace(
        phase=phase,
        phase_links=[frozenset({0, 1, 4}), frozenset({2, 3})],
        link_by_index={lk.index: lk for lk in links},
    )


def meas(**counts):
    return SimpleNamespace(count=counts)


def test_pressure_is_upstream_minus_downstream():
    inter = make_inter()
    m = meas(n_in=10, s_out=2, s_in=4, n_out=0, e_in=3, w_out=5, w_in=1, e_out=0)
    assert phase_pressure(inter, m) == [10 - 2 + 4 - 0, 3 - 5 + 1 - 0]


def test_max_pressure_picks_the_largest_and_keeps_ties():
    mp = MaxPressure()
    env = SimpleNamespace(intersections={"J": make_inter(phase=0)})
    env.meas = meas(n_in=1, s_in=1, e_in=9, w_in=9)
    assert mp.act(env, {}) == {"J": 1}
    env.meas = meas(n_in=5, e_in=5)
    assert mp.act(env, {}) == {"J": 0}  # tie: keep the current phase
    env.intersections["J"].phase = 1
    assert mp.act(env, {}) == {"J": 1}
