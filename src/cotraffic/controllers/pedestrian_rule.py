"""PED-RULE-MP: Max-Pressure with a rule that serves pedestrians who have waited too long.

The fair reference for COOP-FULL's pedestrian results: the classical baselines choose
phases from vehicle counts only. At each decision, a crossing whose longest-waiting
pedestrian has waited more than ``ped_rule_wait_s`` (protocol; 30 s, the delay above
which the Highway Capacity Manual expects pedestrians to become impatient and cross
against the signal) requests the phase that gives it green; the other signals follow
Max-Pressure. Requests go through the shield like every controller of the environment.
"""

from __future__ import annotations

from typing import Any

from cotraffic.controllers.classical import MaxPressure
from cotraffic.controllers.ev_preemption import phase_for


def longest_waits(env) -> dict[str, float]:
    """Longest current wait (s) of the pedestrians waiting at each controlled crossing."""
    person = env.conn.person
    out: dict[str, float] = {}
    for pid in env.person_ids:
        if person.getRoadID(pid) not in env.walkingareas:
            continue
        wait = person.getWaitingTime(pid)
        crossing = person.getNextEdge(pid)
        if wait > 0 and crossing in env.crossing_owner:
            out[crossing] = max(out.get(crossing, 0.0), wait)
    return out


class PedestrianRule(MaxPressure):
    name = "ped_rule_mp"

    def __init__(self) -> None:
        super().__init__()
        self.requests = 0

    def reset(self, env) -> None:
        self.wait_s = float(env.protocol["baselines"]["ped_rule_wait_s"])
        self.requests = 0

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        actions = super().act(env, obs)
        waits = longest_waits(env)
        if not waits:
            return actions
        for tid, inter in env.intersections.items():
            due = [
                link for link in inter.crossing_links if waits.get(link.crossing, 0.0) > self.wait_s
            ]
            if not due:
                continue
            worst = max(due, key=lambda link: waits[link.crossing])
            if worst.index in inter.phase_links[inter.phase] and not inter.in_yellow:
                actions[tid] = inter.phase
            else:
                actions[tid] = phase_for(inter, worst.index)
                self.requests += 1
        return actions
