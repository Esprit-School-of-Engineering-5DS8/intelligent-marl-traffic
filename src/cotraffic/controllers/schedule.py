"""A network-level strategy played window by window (phase B: strategy oracle, placebo).

A schedule gives one mode for the whole network per window of ``window_s`` seconds:

* ``coop``: COOP-FULL;
* ``mp``: Max-Pressure at every junction;
* ``mix``: the best fixed hybrid of phase A, either H1 (Max-Pressure where the neighbourhood
  is congested, by quantile threshold) or H2 (COOP-FULL with a bias towards Max-Pressure);

with emergency pre-emption (EV-RULE, switching) and the shield in every mode. The H1
strategy observes the congestion at every decision, whatever the mode, so that its
one-minute history is the same as if it had been active all along.
"""

from __future__ import annotations

from typing import Any

from cotraffic.controllers.combined import EvRuleGuide
from cotraffic.controllers.hybrid import CongestionStrategy, HybridPolicy

MODES = ("coop", "mp", "mix")


class ScheduleStrategy:
    name = "schedule"

    def __init__(
        self, schedule: list[str], window_s: float = 300.0, h1: CongestionStrategy | None = None
    ):
        bad = set(schedule) - set(MODES)
        if bad:
            raise ValueError(f"unknown modes {sorted(bad)}; expected {MODES}")
        self.schedule, self.window_s, self.h1 = list(schedule), float(window_s), h1

    def reset(self, env) -> None:
        if self.h1 is not None:
            self.h1.reset(env)

    def mode_at(self, now: float) -> str:
        """Mode of the window holding ``now`` (COOP-FULL after the end of the schedule)."""
        k = int(now // self.window_s)
        return self.schedule[k] if k < len(self.schedule) else "coop"

    def modes(self, env) -> dict[str, str]:
        h1 = self.h1.modes(env) if self.h1 is not None else {}  # history kept in every mode
        mode = self.mode_at(env.now)
        if mode == "mp":
            return dict.fromkeys(env.intersections, "mp")
        if mode == "mix":
            return h1
        return {}

    def summary(self) -> dict[str, Any]:
        n = max(1, len(self.schedule))
        return {
            "schedule": " ".join(self.schedule),
            **{f"windows_{m}": round(self.schedule.count(m) / n, 4) for m in MODES},
        }


class ScheduledPolicy(HybridPolicy):
    """COOP-FULL, Max-Pressure or the mix, window by window, with EV-RULE pre-emption.

    ``mix`` = ("h1", quantile threshold) or ("h2", beta)."""

    def __init__(self, base, schedule: list[str], mix: tuple[str, float], window_s: float = 300.0):
        kind, value = mix
        if kind not in ("h1", "h2"):
            raise ValueError("mix must be ('h1', threshold) or ('h2', beta)")
        h1 = CongestionStrategy(value, period_s=window_s) if kind == "h1" else None
        super().__init__(base, ScheduleStrategy(schedule, window_s, h1), ev_guide=EvRuleGuide())
        self.mix = (kind, float(value))
        self.name = "scheduled"

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        kind, value = self.mix
        in_mix = self.strategy.mode_at(env.now) == "mix"
        self.mp_beta = value if (kind == "h2" and in_mix) else 0.0
        return super().act(env, obs)

    def summary(self) -> dict[str, Any]:
        return {**super().summary(), "mix": f"{self.mix[0]}:{self.mix[1]:g}"}
