"""
environment/traffic_light.py
Canonical per-intersection traffic-light agent (moved from the scenario runner).

Safety lives here, in code:
- minimum green time before switching away from a green phase,
- explicit green -> clearance -> yellow -> target transitions from the TLS
  program (no hard-coded phase indices),
- phase durations pinned after every setPhase so SUMO's built-in timer cannot
  override the controller (setPhaseDuration: long hold for canonical green
  phases, program duration for clearance/yellow).

`ensure_static_program` converts real-world actuated/delay_based/NEMA programs
(e.g. MoST Monaco) to an equivalent static copy before the controller pins
phases: on actuated programs SUMO caps a pinned green at the phase's `maxDur`
and advances the phase behind the controller's back.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from environment._bootstrap import ensure_sumo_on_path

ensure_sumo_on_path()

import traci

from environment.topology import GREEN_HOLD_S, TLSTopology, discover_topology

TRAFFICLIGHT_TYPE_STATIC = 0x00
STATIC_PROGRAM_ID = "marl_static"


def ensure_static_program(tls_id: str) -> bool:
    """
    Replace a non-static TLS program with an equivalent static copy.

    Actuated/delay_based/NEMA logic lets SUMO's own controller advance phases
    (a pinned `setPhaseDuration` is capped by the phase's `maxDur`), which
    would silently override the MARL controller. The static copy keeps the
    exact same phase states and durations. Returns True when a conversion
    happened; no-op (and no extra TraCI writes) on already-static programs.
    """
    program = traci.trafficlight.getAllProgramLogics(tls_id)[0]
    if int(program.type) == TRAFFICLIGHT_TYPE_STATIC:
        return False

    from sumolib.net import Phase as SumoPhase

    phases = [
        SumoPhase(phase.duration, phase.state, phase.minDur, phase.maxDur,
                  phase.next, phase.name)
        for phase in program.phases
    ]
    logic = traci.trafficlight.Logic(
        STATIC_PROGRAM_ID, TRAFFICLIGHT_TYPE_STATIC,
        program.currentPhaseIndex, phases, dict(getattr(program, "subParameter", {}) or {}),
    )
    traci.trafficlight.setProgramLogic(tls_id, logic)
    traci.trafficlight.setProgram(tls_id, STATIC_PROGRAM_ID)
    return True


class TrafficLightAgent:
    """Controls one intersection: phase transitions, min-green, observations."""

    def __init__(
        self,
        tls_id: str,
        topology: Optional[TLSTopology] = None,
        min_green: int = 10,
        step_length: float = 1.0,
    ):
        self.tls_id = tls_id
        self.topology = topology if topology is not None else discover_topology(tls_id)
        self.min_green = int(min_green)
        self.step_length = float(step_length)
        self.current_phase = self.topology.ns_green_phase
        self.time_in_phase = 0.0
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

        current_axis = None
        if self.topology.is_green_phase(self.current_phase):
            current_axis = self.topology.axis_for_phase(self.current_phase)

        group_lanes = self.topology.group_lanes or (
            self.topology.ns_lanes, self.topology.ew_lanes)

        return {
            "tls_id": self.tls_id,
            "current_phase": self.current_phase,
            "current_axis": current_axis,
            "time_in_phase": self.time_in_phase,
            "is_yellow": not self.topology.is_green_phase(self.current_phase),
            "in_transition": bool(self._transition),
            "total_queue": ns_queue + ew_queue,
            "total_waiting_time": total_waiting,
            "ns_queue": ns_queue,
            "ew_queue": ew_queue,
            "ns_lanes": self.topology.ns_lanes,
            "ew_lanes": self.topology.ew_lanes,
            # N-phase support: one lane set / phase group / axis label per
            # action; the base policy may select any group, the LLM layer only
            # addresses the two axes.
            "group_lanes": group_lanes,
            "group_queues": tuple(
                sum(lane_queues.get(lane, 0) or 0 for lane in lanes)
                for lanes in group_lanes
            ),
            "axis_by_action": self.topology.axis_by_action or ("NS", "EW"),
            "group_phases": self.topology.group_phases,
            "lane_queues": lane_queues,
            "lane_waiting": lane_waiting,
            "lane_counts": lane_counts,
        }

    def step_control(self, action: int):
        """Apply the policy's action (index of a green group), safely."""
        self.time_in_phase += self.step_length

        if self._transition:
            if self.time_in_phase >= self._phase_duration(self.current_phase):
                self._advance_transition()
            return

        desired_green = self.topology.group_phase_for_action(action)
        if desired_green != self.current_phase and self.time_in_phase >= self.min_green:
            self._transition = list(
                self.topology.transition_path(self.current_phase, desired_green)
            )
            self._advance_transition()

    def _advance_transition(self):
        self._set_phase(self._transition.pop(0))

    def _set_phase(self, phase_index: int):
        self.current_phase = phase_index
        self.time_in_phase = 0.0
        traci.trafficlight.setPhase(self.tls_id, phase_index)
        traci.trafficlight.setPhaseDuration(self.tls_id, self._phase_duration(phase_index))

    def _phase_duration(self, phase_index: int) -> float:
        # Only the canonical green phases are pinned with a long duration.
        # Programs have extra phases that keep vehicle greens while the
        # crossing signals change (end-of-green grace); those must run with
        # their programmed duration so transitions advance to yellow.
        if self.topology.is_hold_phase(phase_index):
            return GREEN_HOLD_S
        return self.topology.phase(phase_index).duration
