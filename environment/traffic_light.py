"""
environment/traffic_light.py
Canonical per-intersection traffic-light agent (moved from the scenario runner).

Safety lives here, in code:
- minimum green time before switching away from a green phase,
- explicit green -> clearance -> yellow -> target transitions from the TLS
  program (no hard-coded phase indices),
- phase durations pinned after every setPhase so SUMO's built-in timer cannot
  override the controller (setPhaseDuration: long hold for green, program
  duration for clearance/yellow).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from environment._bootstrap import ensure_sumo_on_path

ensure_sumo_on_path()

import traci

from environment.topology import GREEN_HOLD_S, TLSTopology, discover_topology


class TrafficLightAgent:
    """Controls one intersection: phase transitions, min-green, observations."""

    def __init__(
        self,
        tls_id: str,
        topology: Optional[TLSTopology] = None,
        min_green: int = 10,
    ):
        self.tls_id = tls_id
        self.topology = topology if topology is not None else discover_topology(tls_id)
        self.min_green = int(min_green)
        self.current_phase = self.topology.ns_green_phase
        self.time_in_phase = 0
        self._transition: List[int] = []

    def initialize(self):
        """Pin the initial phase before the first simulation step."""
        self._transition = []
        self._set_phase(self.topology.ns_green_phase)

    def get_state(self) -> Dict[str, Any]:
        lane_queues: Dict[str, int] = {}
        lane_waiting: Dict[str, float] = {}
        lane_counts: Dict[str, int] = {}
        ns_queue = 0
        ew_queue = 0
        total_waiting = 0.0

        for lane_id in sorted(self.topology.controlled_lanes):
            halting = traci.lane.getLastStepHaltingNumber(lane_id)
            waiting = traci.lane.getWaitingTime(lane_id)
            lane_queues[lane_id] = halting
            lane_waiting[lane_id] = waiting
            lane_counts[lane_id] = traci.lane.getLastStepVehicleNumber(lane_id)
            total_waiting += waiting
            if lane_id in self.topology.ns_lanes:
                ns_queue += halting
            else:
                ew_queue += halting

        return {
            "tls_id": self.tls_id,
            "current_phase": self.current_phase,
            "time_in_phase": self.time_in_phase,
            "is_yellow": not self.topology.is_green_phase(self.current_phase),
            "in_transition": bool(self._transition),
            "total_queue": ns_queue + ew_queue,
            "total_waiting_time": total_waiting,
            "ns_queue": ns_queue,
            "ew_queue": ew_queue,
            "ns_lanes": self.topology.ns_lanes,
            "ew_lanes": self.topology.ew_lanes,
            "lane_queues": lane_queues,
            "lane_waiting": lane_waiting,
            "lane_counts": lane_counts,
        }

    def step_control(self, action: int):
        """Apply the policy's action (0 = NS green, 1 = EW green), safely."""
        self.time_in_phase += 1

        if self._transition:
            if self.time_in_phase >= self._phase_duration(self.current_phase):
                self._advance_transition()
            return

        desired_green = self.topology.green_phase_for_action(action)
        if desired_green != self.current_phase and self.time_in_phase >= self.min_green:
            self._transition = list(
                self.topology.transition_path(self.current_phase, desired_green)
            )
            self._advance_transition()

    def _advance_transition(self):
        self._set_phase(self._transition.pop(0))

    def _set_phase(self, phase_index: int):
        self.current_phase = phase_index
        self.time_in_phase = 0
        traci.trafficlight.setPhase(self.tls_id, phase_index)
        traci.trafficlight.setPhaseDuration(self.tls_id, self._phase_duration(phase_index))

    def _phase_duration(self, phase_index: int) -> float:
        if self.topology.is_green_phase(phase_index):
            return GREEN_HOLD_S
        return self.topology.phase(phase_index).duration
