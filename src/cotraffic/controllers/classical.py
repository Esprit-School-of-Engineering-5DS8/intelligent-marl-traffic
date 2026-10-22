"""Classical baselines: fixed-time (Webster), actuated and Max-Pressure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cotraffic.controllers.base import Controller
from cotraffic.controllers.programs import actuated_program, webster_program


class FixedTime(Controller):
    """Webster plan tuned for the demand level being evaluated (a fair, not a strawman,
    fixed-time baseline: it knows the average demand of the hour in advance)."""

    name = "ft"
    controlled = False

    def __init__(self, scale: float = 1.0) -> None:
        super().__init__()
        self.scale = scale

    def additional_files(self, network: str, demand: str) -> list[Path]:
        return [webster_program(network, demand, self.scale)]


class Actuated(Controller):
    """SUMO's gap-based actuated control with our minimum and maximum greens."""

    name = "act"
    controlled = False

    def additional_files(self, network: str, demand: str) -> list[Path]:
        return [actuated_program(network)]


def phase_pressure(inter, meas) -> list[float]:
    """Max-Pressure weight of each phase: sum over its green vehicle links of
    (vehicles on the incoming lane - vehicles on the outgoing lane)."""
    count = meas.count
    weights = []
    for links in inter.phase_links:
        total = 0.0
        for index in links:
            link = inter.link_by_index[index]
            if link.crossing:
                continue
            total += count.get(link.in_lane, 0.0) - count.get(link.out_lane, 0.0)
        weights.append(total)
    return weights


class MaxPressure(Controller):
    """Varaiya (2013): at each decision, request the phase with the largest pressure.

    The request goes through the same shield as the learning agents (minimum and
    maximum green, anti-starvation). Ties keep the current phase.
    """

    name = "mp"

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        actions = {}
        for tid, inter in env.intersections.items():
            weights = phase_pressure(inter, env.meas)
            best = max(weights)
            actions[tid] = inter.phase if weights[inter.phase] >= best else weights.index(best)
        return actions
