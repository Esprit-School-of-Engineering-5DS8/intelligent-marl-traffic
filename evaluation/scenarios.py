"""
evaluation/scenarios.py
Scenario registry: maps experiment scenario names to their config file and
runtime injection specs. Scenario variants share the base network and demand
files; only the config differs, so the baseline net stays untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from environment.incidents import IncidentSpec


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    folder: str
    cfg: str
    description: str = ""
    incident: Optional[IncidentSpec] = None


SCENARIOS: Dict[str, ScenarioSpec] = {
    "grid_2x2": ScenarioSpec(
        "grid_2x2", "grid_2x2", "grid2x2.sumocfg", "2x2 grid, base demand"),
    "grid_3x3": ScenarioSpec(
        "grid_3x3", "grid_3x3", "grid3x3.sumocfg", "S0: 3x3 grid, base demand (1200 veh)"),
    "grid_3x3_peak": ScenarioSpec(
        "grid_3x3_peak", "grid_3x3", "grid3x3.peak.sumocfg", "S1: peak demand (2400 veh)"),
    "grid_3x3_ev": ScenarioSpec(
        "grid_3x3_ev", "grid_3x3", "grid3x3.ev.sumocfg",
        "S2: one diagonal EV at t=600 in peak demand"),
    "grid_3x3_ev2": ScenarioSpec(
        "grid_3x3_ev2", "grid_3x3", "grid3x3.ev2.sumocfg",
        "S2: two overlapping EVs (t=600, 615) in peak demand"),
    "grid_3x3_ev_incident": ScenarioSpec(
        "grid_3x3_ev_incident", "grid_3x3", "grid3x3.ev_incident.sumocfg",
        "S2: one EV at t=600 while B1B0 is blocked t=620..860 (teleport disabled)",
        incident=IncidentSpec(edge_id="B1B0", start_s=620.0, duration_s=240.0)),
    "grid_3x3_incident": ScenarioSpec(
        "grid_3x3_incident", "grid_3x3", "grid3x3.incident.sumocfg",
        "S3: interior edge A1A0 blocked for 300 s (teleport disabled)",
        incident=IncidentSpec(edge_id="A1A0", start_s=1200.0, duration_s=300.0)),
}
