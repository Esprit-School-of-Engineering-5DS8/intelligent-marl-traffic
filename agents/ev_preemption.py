"""
agents/ev_preemption.py
Rule-based emergency-vehicle pre-emption — baseline arm A3.

A3 is a *directive source*, not a separate control path: every step it proposes
`preempt` envelopes that run through the same arbiter and DirectiveLayer as the
LLM team (plan Appendix B), so A3 and A4 share the safety and arbitration code.

For each EV and each of its next `lookahead_tls` traffic lights:
- ETA = distance / speed with a floor on speed,
- trigger when ETA <= eta_trigger_s or the EV is within reactive_distance_m
  (which also covers a stopped EV at a red light),
- propose `preempt(phase=EV approach axis, start_in_s=0, hold_s=ETA+margin)`.
  The hold window is refreshed every step while the EV needs the phase; when
  the EV crosses a junction it disappears from the sensor list for a couple of
  steps (internal lanes), and the remaining hold window keeps the pre-emption
  alive, which is the grace behavior of the pre-Phase-2 implementation.
- once the EV is observed beyond a traffic light (or its route turns away from
  it), propose `preempt(..., hold_s=0)`, which releases the pre-emption
  immediately — the same release the old `begin_step()` pruning provided.

The 25 s trigger horizon (not the plan's 20 s) must be preserved: the base
policy can commit to the opposite phase just before the EV enters a 20 s
window; 25 s covers in-flight transition + min_green + yellow plus margin.
Axis comes from `topology.action_for_link(link_index)`, exact for turns.
No TraCI here: it consumes EVState snapshots, so it is unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from environment.ev import EVState
from environment.topology import TLSTopology


@dataclass(frozen=True)
class PreemptionConfig:
    eta_trigger_s: float = 25.0
    reactive_distance_m: float = 60.0
    lookahead_tls: int = 3
    min_speed_m_s: float = 1.0
    release_margin_s: float = 8.0
    release_grace_steps: int = 5
    max_hold_s: float = 40.0
    max_ttl_s: float = 60.0


@dataclass(frozen=True)
class EVCandidate:
    veh_id: str
    tls_id: str
    action: int
    axis: str
    phase_index: Optional[int]
    eta_s: float
    distance_m: float


class RuleBasedEVPreemption:
    """Proposes preempt directives for the EVs currently in the network."""

    def __init__(self, topologies: Dict[str, TLSTopology],
                 config: Optional[PreemptionConfig] = None):
        self.topologies = topologies
        self.config = config or PreemptionConfig()
        self._issued: Dict[Tuple[str, str], Tuple[str, int]] = {}

    def candidates(self, evs: List[EVState]) -> List[EVCandidate]:
        """Best (lowest-ETA) triggered candidate per TLS, across all EVs."""
        best: Dict[str, EVCandidate] = {}
        for ev in evs:
            for nxt in ev.next_tls[:self.config.lookahead_tls]:
                topology = self.topologies.get(nxt.tls_id)
                if topology is None:
                    continue
                action = topology.action_for_link(nxt.link_index)
                if action is None:
                    continue
                axis = topology.axis_by_action[action] if action < len(topology.axis_by_action) \
                    else "NS"
                multi_group = sum(1 for label in topology.axis_by_action if label == axis) > 1
                eta = nxt.distance_m / max(ev.speed_m_s, self.config.min_speed_m_s)
                if eta > self.config.eta_trigger_s and nxt.distance_m > self.config.reactive_distance_m:
                    continue
                candidate = EVCandidate(ev.veh_id, nxt.tls_id, action, axis,
                                        action if multi_group else None, eta, nxt.distance_m)
                current = best.get(nxt.tls_id)
                if current is None or eta < current.eta_s:
                    best[nxt.tls_id] = candidate
        return list(best.values())

    def propose(self, evs: List[EVState], t: float = 0.0) -> List[Dict[str, Any]]:
        """One envelope with a preempt per triggered TLS, plus releases."""
        directives: List[Dict[str, Any]] = []
        candidates = self.candidates(evs)
        best_keys = {(c.tls_id, c.veh_id): c for c in candidates}
        observed = {ev.veh_id: ev for ev in evs}

        for (tls_id, veh_id), candidate in best_keys.items():
            directives.append(self._preempt(tls_id, veh_id, candidate.axis, candidate.eta_s,
                                            phase_index=candidate.phase_index))
            self._issued[(tls_id, veh_id)] = (candidate.axis, 0)

        for key, (axis, missing) in list(self._issued.items()):
            if key in best_keys:
                continue
            tls_id, veh_id = key
            ev = observed.get(veh_id)
            if ev is None:
                # EV on an internal lane (or despawned): keep the pre-emption
                # alive for a short grace window, like begin_step() did.
                if missing + 1 > self.config.release_grace_steps:
                    del self._issued[key]
                else:
                    self._issued[key] = (axis, missing + 1)
                continue
            upcoming = {nxt.tls_id for nxt in ev.next_tls[:self.config.lookahead_tls]}
            if tls_id not in upcoming:
                directives.append(self._preempt(tls_id, veh_id, axis, eta_s=0.0, hold_s=0.0))
                del self._issued[key]
            else:
                self._issued[key] = (axis, 0)

        if not directives:
            return []
        return [{
            "agent": "emergency",
            "t": t,
            "directives": directives,
            "alerts": [],
            "explanation": f"rule-based pre-emption for {len(directives)} traffic light(s)",
        }]

    def _preempt(self, tls_id: str, veh_id: str, axis: str, eta_s: float,
                 hold_s: Optional[float] = None,
                 phase_index: Optional[int] = None) -> Dict[str, Any]:
        if hold_s is None:
            hold_s = min(self.config.max_hold_s, eta_s + self.config.release_margin_s)
        directive = {
            "tls": tls_id,
            "type": "preempt",
            "phase": axis,
            "ev": veh_id,
            "start_in_s": 0.0,
            "hold_s": hold_s,
            "eta_s": eta_s,
            "ttl_s": min(self.config.max_ttl_s, hold_s + 5.0),
        }
        if phase_index is not None:
            directive["phase_index"] = int(phase_index)
        return directive
