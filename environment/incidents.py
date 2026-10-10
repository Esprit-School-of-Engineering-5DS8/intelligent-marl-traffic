"""
environment/incidents.py
Incident injection for scenario S3: block an interior edge by stopping one
vehicle per lane for a fixed duration.

Usage requires the scenario config to disable teleporting
(`<time-to-teleport value="-1"/>`), otherwise SUMO removes the queued vehicles
after the teleport timeout and the incident stops being an incident.

The injector retries insertion every step, so it works whether or not the lane
already has traffic. Blockers added by the injector get ids prefixed
`incident_` and are excluded from civilian KPIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

BLOCKER_PREFIX = "incident_"


@dataclass(frozen=True)
class IncidentSpec:
    edge_id: str
    start_s: float
    duration_s: float
    blocker_type: str = "passenger"


class IncidentInjector:
    """Schedules and applies the incident; call `apply(sim_time)` every step."""

    def __init__(self, spec: IncidentSpec, traci_module=None):
        self.spec = spec
        self._traci = traci_module
        self._done = False
        self._blocked: Dict[str, bool] = {}
        self.blockers: List[str] = []

    @property
    def traci(self):
        if self._traci is None:
            from environment._bootstrap import ensure_sumo_on_path

            ensure_sumo_on_path()
            import traci
            self._traci = traci
        return self._traci

    def apply(self, sim_time: float):
        if self._done or sim_time < self.spec.start_s:
            return
        if not self._blocked:
            self._blocked = {lane_id: False for lane_id in self._lane_ids()}
            print(f"[incident] t={sim_time:.0f}s blocking {self.spec.edge_id} "
                  f"for {self.spec.duration_s:.0f}s ({len(self._blocked)} lanes)")
        self._block_pending_lanes(sim_time)
        if sim_time >= self.spec.start_s + self.spec.duration_s:
            self._done = True
            print(f"[incident] t={sim_time:.0f}s incident over on {self.spec.edge_id}")

    def _lane_ids(self) -> List[str]:
        traci = self.traci
        edge = self.spec.edge_id
        return sorted(lane_id for lane_id in traci.lane.getIDList()
                      if lane_id.rsplit("_", 1)[0] == edge)

    def _block_pending_lanes(self, sim_time: float):
        traci = self.traci
        remaining = max(1.0, self.spec.start_s + self.spec.duration_s - sim_time)
        for lane_id, blocked in list(self._blocked.items()):
            if blocked:
                continue
            lane_index = int(lane_id.rsplit("_", 1)[1])
            stop_pos = max(0.0, traci.lane.getLength(lane_id) - 0.1)

            vehicles = traci.lane.getLastStepVehicleIDs(lane_id)
            if vehicles:
                veh_id = max(vehicles, key=traci.vehicle.getLanePosition)
                traci.vehicle.setStop(veh_id, self.spec.edge_id, pos=stop_pos,
                                      laneIndex=lane_index, duration=remaining)
                self._blocked[lane_id] = True
                self.blockers.append(veh_id)
                continue

            blocker_id = f"{BLOCKER_PREFIX}{lane_id}"
            route_id = f"{BLOCKER_PREFIX}route_{lane_id}"
            if blocker_id not in traci.vehicle.getIDList():
                if route_id not in traci.route.getIDList():
                    traci.route.add(route_id, [self.spec.edge_id])
                try:
                    traci.vehicle.add(blocker_id, route_id, typeID=self.spec.blocker_type,
                                      depart="now", departLane=str(lane_index),
                                      departPos="free", departSpeed="0")
                except traci.exceptions.TraCIException:
                    pass
            else:
                traci.vehicle.setStop(blocker_id, self.spec.edge_id, pos=stop_pos,
                                      laneIndex=lane_index, duration=remaining)
                self._blocked[lane_id] = True
                self.blockers.append(blocker_id)
