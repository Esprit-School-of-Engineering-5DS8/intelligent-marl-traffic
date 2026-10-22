"""Safety shield between a controller and the traffic light.

Every learning-based or pressure-based controller proposes a green phase; the shield
returns the phase that is actually executed. It enforces, in this order:

1. invalid (padded) actions keep the current phase;
2. minimum green: a green phase cannot be cut before ``min_green`` seconds;
3. anti-starvation: a movement with demand that has been red for more than
   ``max_red`` seconds is served next;
4. maximum green: a phase is not extended beyond ``max_green`` seconds while
   another phase has demand.

Yellow transitions are produced by the intersection model, never by the policy, so
no sequence of actions can produce an unsafe signal sequence. The shield is pure
logic (no SUMO access) so that it can be tested exhaustively.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

INVALID = "invalid"
MIN_GREEN = "min_green"
MAX_GREEN = "max_green"
STARVATION = "starvation"
REASONS = (INVALID, MIN_GREEN, MAX_GREEN, STARVATION)


@dataclass(frozen=True)
class ShieldConfig:
    min_green: float
    max_green: float
    max_red: float

    @classmethod
    def from_timing(cls, timing: Mapping[str, float]) -> ShieldConfig:
        return cls(float(timing["min_green"]), float(timing["max_green"]), float(timing["max_red"]))


@dataclass(frozen=True)
class ShieldState:
    current_phase: int
    green_elapsed: float
    phase_links: Sequence[frozenset[int]]
    link_red_time: Mapping[int, float]
    links_with_demand: frozenset[int]
    phase_demand: Sequence[float]

    @property
    def n_phases(self) -> int:
        return len(self.phase_links)


@dataclass(frozen=True)
class ShieldDecision:
    phase: int
    reason: str | None = None

    @property
    def intervened(self) -> bool:
        return self.reason is not None


def apply_shield(requested: int, state: ShieldState, cfg: ShieldConfig) -> ShieldDecision:
    """Return the phase to execute given the controller's ``requested`` phase.

    ``phase_demand[p]`` is the demand that phase ``p`` would serve beyond what the
    current phase already serves; it picks the target when the shield must switch.
    """
    current = state.current_phase
    reason: str | None = None
    if not 0 <= requested < state.n_phases:
        requested, reason = current, INVALID

    if state.green_elapsed < cfg.min_green:
        return ShieldDecision(current, MIN_GREEN if requested != current else reason)

    starving = [
        link
        for link in state.links_with_demand
        if state.link_red_time.get(link, 0.0) > cfg.max_red
        and link not in state.phase_links[current]
        and any(link in links for links in state.phase_links)
    ]
    if starving:
        worst = max(starving, key=lambda link: (state.link_red_time[link], -link))
        if worst in state.phase_links[requested]:
            return ShieldDecision(requested, reason)
        candidates = [p for p in range(state.n_phases) if worst in state.phase_links[p]]
        target = max(
            candidates,
            key=lambda p: (
                sum(link in state.phase_links[p] for link in starving),
                state.phase_demand[p],
                -p,
            ),
        )
        return ShieldDecision(target, STARVATION)

    if requested == current and state.green_elapsed >= cfg.max_green:
        others = [p for p in range(state.n_phases) if p != current and state.phase_demand[p] > 0]
        if others:
            target = max(others, key=lambda p: (state.phase_demand[p], -p))
            return ShieldDecision(target, MAX_GREEN)

    return ShieldDecision(requested, reason)
