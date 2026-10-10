"""
agents/ev_preemption.py
Rule-based emergency-vehicle pre-emption — baseline arm A3.

For each EV, for each of its next `lookahead_tls` traffic lights:
- compute ETA = distance / speed (with a floor on speed),
- if ETA <= eta_trigger_s (or the EV is within reactive_distance_m, which also
  covers a stopped EV at a red light), force the action that serves the EV's
  exact approach link (topology-derived, correct for turns),
- keep forcing until the EV passes the stop line (the TLS drops out of its
  next-TLS list) — this is the hold/release semantics of the preempt directive.

Two EVs wanting different axes at the same TLS: earliest ETA wins (arbiter
rule 3). No TraCI here: it consumes EVState snapshots, so it is unit-testable.

`begin_step(evs)` must be called once per simulation step before the per-TLS
`select_action` calls. It prunes stale preemptions with a grace window: while
an EV crosses a junction it sits on an internal lane and disappears from the
sensor list for a couple of steps — releasing the preemption then would let
the base policy commit to the opposite phase and the EV would arrive at red.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from environment.ev import EVState
from environment.topology import TLSTopology


@dataclass(frozen=True)
class PreemptionConfig:
    """
    eta_trigger_s must cover the worst-case time for a TLS that is (or just
    committed to) the opposite phase: in-flight transition (~3 s) + min_green
    (10 s) + yellow (3 s), with margin. At 20 s the base policy can start the
    opposite transition just before the EV enters the window and the EV loses
    the race; 25 s leaves ~9 s of margin.
    """
    eta_trigger_s: float = 25.0
    reactive_distance_m: float = 60.0
    lookahead_tls: int = 3
    min_speed_m_s: float = 1.0
    release_grace_steps: int = 5


@dataclass(frozen=True)
class ActivePreemption:
    veh_id: str
    action: int
    eta_s: float


class RuleBasedEVPreemption:
    """Overrides base actions with EV priority while an EV needs the phase."""

    def __init__(self, topologies: Dict[str, TLSTopology],
                 config: Optional[PreemptionConfig] = None):
        self.topologies = topologies
        self.config = config or PreemptionConfig()
        self._active: Dict[str, ActivePreemption] = {}
        self._missing_steps: Dict[str, int] = {}

    def begin_step(self, evs: List[EVState]):
        """Prune preemptions whose EV passed the TLS or has been gone too long."""
        for tls_id, active in list(self._active.items()):
            ev = next((candidate for candidate in evs if candidate.veh_id == active.veh_id), None)
            if ev is None:
                missing = self._missing_steps.get(tls_id, 0) + 1
                if missing > self.config.release_grace_steps:
                    del self._active[tls_id]
                    self._missing_steps.pop(tls_id, None)
                else:
                    self._missing_steps[tls_id] = missing
                continue

            self._missing_steps.pop(tls_id, None)
            if not any(nxt.tls_id == tls_id for nxt in ev.next_tls[:self.config.lookahead_tls]):
                del self._active[tls_id]

    def select_action(self, tls_id: str, base_action: int, evs: List[EVState]) -> int:
        candidate = self._best_candidate(tls_id, evs)
        if candidate is not None:
            active = self._active.get(tls_id)
            if active is None or active.veh_id == candidate.veh_id or candidate.eta_s <= active.eta_s:
                self._active[tls_id] = candidate
        active = self._active.get(tls_id)
        return active.action if active is not None else base_action

    def active_preemptions(self) -> Dict[str, ActivePreemption]:
        """Current preemptions (tls -> ActivePreemption), for logging."""
        return dict(self._active)

    def _best_candidate(self, tls_id: str, evs: List[EVState]) -> Optional[ActivePreemption]:
        topology = self.topologies[tls_id]
        best: Optional[ActivePreemption] = None
        for ev in evs:
            for nxt in ev.next_tls[:self.config.lookahead_tls]:
                if nxt.tls_id != tls_id:
                    continue
                action = topology.action_for_link(nxt.link_index)
                if action is None:
                    continue
                eta = nxt.distance_m / max(ev.speed_m_s, self.config.min_speed_m_s)
                reactive = nxt.distance_m <= self.config.reactive_distance_m
                if eta <= self.config.eta_trigger_s or reactive:
                    if best is None or eta < best.eta_s:
                        best = ActivePreemption(ev.veh_id, action, eta)
        return best
