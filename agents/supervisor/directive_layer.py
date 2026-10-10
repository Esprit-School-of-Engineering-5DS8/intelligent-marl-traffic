"""
agents/supervisor/directive_layer.py
The slow-to-fast bridge (plan sections 4.1 and 4.3).

Holds active directives (with TTL), picks the winning directive per
intersection and turns it into an action override for the base policy:

- `preempt`      : force the EV's axis through the normal transition,
- `serve_ped`    : guarantee a pedestrian window on an axis,
- `hold`         : keep the current green until `extra_green_s` elapsed
                   (capped at `green_cap_s` seconds in phase),
- `bias`         : re-rank the queue-pressure scores of the two axes,
- no directive   : the base action passes through untouched.

Never unsafe: min-green, yellow and transition logic stay inside
`environment.traffic_light.TrafficLightAgent`; this layer only changes the
*desired* green axis. It touches no TraCI, so it is fully unit-testable.

Starvation guard (plan 4.4 rule 4): if directives cause an action override
that favors the same axis continuously for longer than `max_red_s`, the layer
drops all directives for that TLS and enters a cooldown. An EV pre-emption may
extend the cap by at most `preempt_extension_s`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from agents.llm.schemas import ACTION_TO_AXIS, AXIS_TO_ACTION, Directive
from agents.supervisor.arbiter import select_winner


@dataclass(frozen=True)
class DirectiveLayerConfig:
    green_cap_s: float = 45.0
    max_red_s: float = 90.0
    preempt_extension_s: float = 60.0
    starvation_cooldown_s: float = 30.0
    bias_product_range: Tuple[float, float] = (0.25, 4.0)


def _key(directive: Directive) -> Tuple[str, Optional[str]]:
    return directive.key()


def active_window_end(directive: Directive) -> float:
    """Last sim-time at which the directive can still have an effect."""
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
    def __init__(self, config: Optional[DirectiveLayerConfig] = None):
        self.config = config or DirectiveLayerConfig()
        self._store: Dict[str, Dict[Tuple[str, Optional[str]], Directive]] = {}
        self._forced: Dict[str, Tuple[str, float, bool]] = {}
        self._cooldown: Dict[str, float] = {}
        self.events: List[Dict[str, Any]] = []

    def install(self, directives: Iterable[Directive], t: float) -> None:
        """Add/replace directives (one slot per type, per EV for preempts)."""
        for directive in directives:
            self._store.setdefault(directive.tls_id, {})[_key(directive)] = directive

    def clear(self, tls_id: Optional[str] = None) -> None:
        if tls_id is None:
            self._store.clear()
            self._forced.clear()
            self._cooldown.clear()
        else:
            self._store.pop(tls_id, None)
            self._forced.pop(tls_id, None)
            self._cooldown.pop(tls_id, None)

    def active(self, tls_id: str, t: float) -> List[Directive]:
        self._prune(tls_id, t)
        return [d for d in self._store.get(tls_id, {}).values() if is_active(d, t)]

    def drain_events(self) -> List[Dict[str, Any]]:
        events, self.events = self.events, []
        return events

    def apply(self, tls_id: str, state: Mapping[str, Any], base_action: int,
              t: float) -> int:
        """Turn base_action into the directive-aware action for one TLS."""
        if t < self._cooldown.get(tls_id, float("-inf")):
            return base_action

        active = self.active(tls_id, t)
        winner = select_winner(active, state)
        action: Optional[int] = None
        if winner is not None:
            action = self._forced_action(winner, state, t)
        if action is None:
            action = self._bias_action(state, base_action, active)

        if action != base_action:
            action = self._guard(tls_id, action, winner, base_action, t)
        else:
            self._forced.pop(tls_id, None)
        return action

    def _forced_action(self, directive: Directive, state: Mapping[str, Any],
                       t: float) -> Optional[int]:
        action = AXIS_TO_ACTION[directive.axis]
        if directive.type == "preempt":
            return action

        current = state.get("current_axis")
        time_in_phase = float(state.get("time_in_phase", 0.0))
        if directive.type == "hold":
            if current != directive.axis or state.get("in_transition"):
                return None
            elapsed = t - directive.issued_at
            if (elapsed < (directive.extra_green_s or 0.0)
                    and time_in_phase < self.config.green_cap_s):
                return action
            return None

        # serve_ped: block switching while the window is owed, otherwise make
        # sure the crossing-green phase arrives (below preempt in priority).
        if current == directive.axis:
            elapsed = t - directive.issued_at
            if (elapsed < (directive.min_green_s or 0.0)
                    and time_in_phase < self.config.green_cap_s):
                return action
            return None
        return action

    def _bias_action(self, state: Mapping[str, Any], base_action: int,
                     active: List[Directive]) -> int:
        biases = [d for d in active if d.type == "bias"]
        if not biases:
            return base_action

        ns_factor = 1.0
        ew_factor = 1.0
        for directive in biases:
            ns_factor *= directive.ns if directive.ns is not None else 1.0
            ew_factor *= directive.ew if directive.ew is not None else 1.0
        lo, hi = self.config.bias_product_range
        ns_factor = min(max(ns_factor, lo), hi)
        ew_factor = min(max(ew_factor, lo), hi)

        lane_queues = state.get("lane_queues") or {}
        ns_queue = sum(q for lane, q in lane_queues.items() if lane in (state.get("ns_lanes") or ()))
        ew_queue = sum(q for lane, q in lane_queues.items() if lane in (state.get("ew_lanes") or ()))
        return 0 if ns_queue * ns_factor >= ew_queue * ew_factor else 1

    def _guard(self, tls_id: str, action: int, winner: Optional[Directive],
               base_action: int, t: float) -> int:
        axis = ACTION_TO_AXIS[action]
        previous = self._forced.get(tls_id)
        if previous is not None and previous[0] == axis:
            since, has_preempt = previous[1], previous[2]
        else:
            since, has_preempt = t, False
        if winner is not None and winner.type == "preempt":
            has_preempt = True

        cap = self.config.max_red_s + (self.config.preempt_extension_s if has_preempt else 0.0)
        if t - since >= cap:
            self._store.pop(tls_id, None)
            self._forced.pop(tls_id, None)
            self._cooldown[tls_id] = t + self.config.starvation_cooldown_s
            self.events.append({
                "t": t,
                "tls": tls_id,
                "kind": "starvation_guard",
                "axis": axis,
                "since": since,
                "cap_s": cap,
                "cooldown_until": t + self.config.starvation_cooldown_s,
            })
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
