"""
agents/ped_priority.py
Rule-based pedestrian priority — arm `ped_priority`, the honest H4 baseline
and fallback for the Pedestrian agent.

A `ped_priority` run is a directive source, not a separate control path: it
proposes `serve_ped` envelopes that flow through the same arbiter and
DirectiveLayer as the LLM team (like A3 does for emergency vehicles).

Policy (deliberately a *sane* rule, not a strawman):
- candidates are crossings whose max wait exceeds `wait_trigger_s`;
- one window per TLS at a time, decided at most every `window_s` seconds so the
  signal does not thrash between the two crossings of the same intersection;
- hysteresis keeps the currently served axis while its wait is still worth
  serving (`min_release_s`) unless the other axis waits at least
  `switch_margin_s` longer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class PedPriorityConfig:
    wait_trigger_s: float = 15.0
    # Crossing windows must be long enough that a person can step onto the
    # crossing and clear it (SUMO persons do not start when they cannot finish
    # before red): alternating with short 12 s windows collapses throughput.
    min_green_s: float = 35.0
    window_s: float = 45.0
    min_release_s: float = 5.0
    switch_margin_s: float = 10.0
    max_targets: int = 2
    ttl_s: float = 46.0


def _value(state: Any, name: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(name, default)
    return getattr(state, name, default)


class RuleBasedPedestrianPriority:
    """Proposes serve_ped windows for the longest pedestrian waits."""

    def __init__(self, config: Optional[PedPriorityConfig] = None):
        self.config = config or PedPriorityConfig()
        self._served: Dict[str, str] = {}
        self._next_decision: Dict[str, float] = {}

    def propose(self, pedestrians: Sequence[Any], t: float = 0.0) -> List[Dict[str, Any]]:
        by_tls: Dict[str, List[Any]] = {}
        for state in pedestrians:
            by_tls.setdefault(str(_value(state, "tls_id", "")), []).append(state)

        directives = []
        for tls_id in sorted(by_tls):
            if len(directives) >= self.config.max_targets:
                break
            if t < self._next_decision.get(tls_id, 0.0):
                continue
            states = by_tls[tls_id]
            eligible = [s for s in states
                        if float(_value(s, "max_wait_s", 0.0) or 0.0) >= self.config.wait_trigger_s]
            if not eligible:
                self._served.pop(tls_id, None)
                continue
            longest = max(eligible, key=lambda s: float(_value(s, "max_wait_s", 0.0)))
            current = self._served.get(tls_id)
            current_state = next((s for s in states
                                  if _value(s, "axis") == current), None)
            choice = str(_value(longest, "axis"))
            if (current is not None and current_state is not None
                    and float(_value(current_state, "max_wait_s", 0.0)) >= self.config.min_release_s
                    and choice != current
                    and (float(_value(longest, "max_wait_s", 0.0))
                         - float(_value(current_state, "max_wait_s", 0.0))
                         < self.config.switch_margin_s)):
                choice = current
            self._served[tls_id] = choice
            self._next_decision[tls_id] = t + self.config.window_s
            directives.append({
                "tls": tls_id,
                "type": "serve_ped",
                "phase": choice,
                "min_green_s": self.config.min_green_s,
                "ttl_s": self.config.ttl_s,
            })

        if not directives:
            return []
        return [{
            "agent": "pedestrian",
            "t": t,
            "directives": directives,
            "alerts": [],
            "explanation": f"rule-based pedestrian window for {len(directives)} crossing(s)",
        }]
