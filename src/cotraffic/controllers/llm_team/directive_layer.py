"""Slow-to-fast bridge: active directives become phase requests.

The environment shield still enforces min green, yellow and anti-starvation.
This layer only changes the desired green phase.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cotraffic.controllers.llm_team.arbiter import select_winner
from cotraffic.controllers.llm_team.schemas import ACTION_TO_AXIS, Directive


@dataclass(frozen=True)
class DirectiveLayerConfig:
    green_cap_s: float = 45.0
    max_red_s: float = 90.0
    preempt_extension_s: float = 60.0
    starvation_cooldown_s: float = 30.0
    bias_product_range: tuple[float, float] = (0.25, 4.0)


def _axes_of(state: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(state.get("axis_by_action") or ("NS", "EW"))  # type: ignore[arg-type]


def _groups_of(state: Mapping[str, object]) -> tuple[object, ...]:
    groups = state.get("group_lanes")
    if groups:
        return tuple(groups)  # type: ignore[arg-type]
    return (state.get("ns_lanes") or frozenset(), state.get("ew_lanes") or frozenset())


def active_window_end(directive: Directive) -> float:
    if directive.type == "preempt":
        start = directive.issued_at + (directive.start_in_s or 0.0)
        end = start + (directive.hold_s or 0.0)
        return min(directive.issued_at + directive.ttl_s, end)
    return directive.issued_at + directive.ttl_s


def is_active(directive: Directive, t: float) -> bool:
    if directive.type == "preempt":
        start = directive.issued_at + (directive.start_in_s or 0.0)
        return start <= t < active_window_end(directive)
    return directive.issued_at <= t < directive.issued_at + directive.ttl_s


class DirectiveLayer:
    def __init__(self, config: DirectiveLayerConfig | None = None) -> None:
        self.config = config or DirectiveLayerConfig()
        self._store: dict[str, dict[tuple[str, str | None], Directive]] = {}
        self._forced: dict[str, tuple[str, float, bool]] = {}
        self._cooldown: dict[str, float] = {}
        self.events: list[dict[str, object]] = []

    def install(self, directives: Iterable[Directive], t: float) -> None:
        for directive in directives:
            self._store.setdefault(directive.tls_id, {})[directive.key()] = directive

    def clear(self, tls_id: str | None = None) -> None:
        if tls_id is None:
            self._store.clear()
            self._forced.clear()
            self._cooldown.clear()
        else:
            self._store.pop(tls_id, None)
            self._forced.pop(tls_id, None)
            self._cooldown.pop(tls_id, None)

    def active(self, tls_id: str, t: float) -> list[Directive]:
        self._prune(tls_id, t)
        return [d for d in self._store.get(tls_id, {}).values() if is_active(d, t)]

    def drain_events(self) -> list[dict[str, object]]:
        events, self.events = self.events, []
        return events

    def apply(
        self, tls_id: str, state: Mapping[str, object], base_action: int, t: float
    ) -> int:
        if t < self._cooldown.get(tls_id, float("-inf")):
            return base_action
        active = self.active(tls_id, t)
        winner = select_winner(active, state)
        action = self._forced_action(winner, state, t) if winner is not None else None
        if action is None:
            action = self._bias_action(state, base_action, active)
        if action != base_action:
            action = self._guard(tls_id, action, winner, base_action, t, state)
        else:
            self._forced.pop(tls_id, None)
        return action

    def _action_for_axis(
        self, axis: str, state: Mapping[str, object], phase_index: int | None = None
    ) -> int | None:
        axes = _axes_of(state)
        if phase_index is not None and 0 <= phase_index < len(axes) and axes[phase_index] == axis:
            return phase_index
        for index, label in enumerate(axes):
            if label == axis:
                return index
        return None

    def _current_group_action(self, state: Mapping[str, object], axis: str) -> int | None:
        current_phase = state.get("current_phase")
        axes = _axes_of(state)
        for index, phases in enumerate(state.get("group_phases") or ()):  # type: ignore[arg-type]
            if current_phase in phases and index < len(axes) and axes[index] == axis:
                return index
        return None

    def _forced_action(
        self, directive: Directive, state: Mapping[str, object], t: float
    ) -> int | None:
        action = self._action_for_axis(directive.axis or "", state, directive.phase_index)
        if action is None:
            return None
        if directive.type == "preempt":
            return action
        current = state.get("current_axis")
        time_in_phase = float(state.get("time_in_phase", 0.0))  # type: ignore[arg-type]
        if directive.type == "hold":
            if current != directive.axis or state.get("in_transition"):
                return None
            elapsed = t - directive.issued_at
            if (
                elapsed < (directive.extra_green_s or 0.0)
                and time_in_phase < self.config.green_cap_s
            ):
                return self._current_group_action(state, directive.axis or "") or action
            return None

        if current == directive.axis:
            elapsed = t - directive.issued_at
            if (
                elapsed < (directive.min_green_s or 0.0)
                and time_in_phase < self.config.green_cap_s
            ):
                return self._current_group_action(state, directive.axis or "") or action
            return None
        return action

    def _bias_action(
        self, state: Mapping[str, object], base_action: int, active: list[Directive]
    ) -> int:
        biases = [d for d in active if d.type == "bias"]
        if not biases:
            return base_action
        ns_factor = 1.0
        ew_factor = 1.0
        for directive in biases:
            ns_factor *= directive.ns if directive.ns is not None else 1.0
            ew_factor *= directive.ew if directive.ew is not None else 1.0
        lo, hi = self.config.bias_product_range
        factors = {
            "NS": min(max(ns_factor, lo), hi),
            "EW": min(max(ew_factor, lo), hi),
        }
        lane_queues = state.get("lane_queues") or {}
        axes = _axes_of(state)
        best_action = 0
        best_score: float | None = None
        for index, lanes in enumerate(_groups_of(state)):
            queue = sum(q for lane, q in lane_queues.items() if lane in lanes)  # type: ignore[union-attr]
            factor = factors.get(axes[index] if index < len(axes) else "NS", 1.0)
            score = queue * factor
            if best_score is None or score > best_score:
                best_action, best_score = index, score
        return best_action

    def _guard(
        self,
        tls_id: str,
        action: int,
        winner: Directive | None,
        base_action: int,
        t: float,
        state: Mapping[str, object],
    ) -> int:
        axes = _axes_of(state)
        axis = axes[action] if 0 <= action < len(axes) else ACTION_TO_AXIS.get(action, "NS")
        previous = self._forced.get(tls_id)
        if previous is not None and previous[0] == axis:
            since, has_preempt = previous[1], previous[2]
        else:
            since, has_preempt = t, False
        if winner is not None and winner.type == "preempt":
            has_preempt = True
        cap = self.config.max_red_s + (
            self.config.preempt_extension_s if has_preempt else 0.0
        )
        if t - since >= cap:
            self._store.pop(tls_id, None)
            self._forced.pop(tls_id, None)
            self._cooldown[tls_id] = t + self.config.starvation_cooldown_s
            self.events.append(
                {
                    "t": t,
                    "tls": tls_id,
                    "kind": "starvation_guard",
                    "axis": axis,
                    "since": since,
                    "cap_s": cap,
                    "cooldown_until": t + self.config.starvation_cooldown_s,
                }
            )
            return base_action
        self._forced[tls_id] = (axis, since, has_preempt)
        return action

    def _prune(self, tls_id: str, t: float) -> None:
        slot = self._store.get(tls_id)
        if not slot:
            return
        for key, directive in list(slot.items()):
            if t >= active_window_end(directive):
                del slot[key]
        if not slot:
            self._store.pop(tls_id, None)
