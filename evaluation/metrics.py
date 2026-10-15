"""
evaluation/metrics.py
Parse SUMO outputs into KPI summaries: tripinfo XML (per-vehicle) and the
per-step metrics CSV written by MultiAgentEnv.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Sequence

EV_PREFIX = "ev_"
INCIDENT_PREFIX = "incident_"


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def parse_tripinfo(path: str,
                   exclude_prefixes: Sequence[str] = (EV_PREFIX, INCIDENT_PREFIX),
                   ) -> Dict[str, Any]:
    """
    Parse a SUMO tripinfo file into per-vehicle records plus a civilian summary.

    Emergency vehicles (`ev_*`) and incident blockers (`incident_*`) are
    excluded from the main summary; they are reported separately via
    `summarize_evs`.
    """
    root = ET.parse(path).getroot()
    vehicles: List[Dict[str, Any]] = []
    for tripinfo in root.findall("tripinfo"):
        vehicles.append({
            "id": tripinfo.get("id"),
            "duration": float(tripinfo.get("duration", 0.0)),
            "waiting_time": float(tripinfo.get("waitingTime", 0.0)),
            "waiting_count": int(tripinfo.get("waitingCount", 0)),
            "time_loss": float(tripinfo.get("timeLoss", 0.0)),
            "route_length": float(tripinfo.get("routeLength", 0.0)),
            "depart": float(tripinfo.get("depart", 0.0)),
            "arrival": float(tripinfo.get("arrival", 0.0)),
        })

    civilian = [v for v in vehicles
                if not any(str(v["id"]).startswith(prefix) for prefix in exclude_prefixes)]
    summary = {
        "arrived_vehicles": len(civilian),
        "vehicles_total": len(vehicles),
        "mean_duration_s": _mean(v["duration"] for v in civilian),
        "mean_tripinfo_waiting_s": _mean(v["waiting_time"] for v in civilian),
        "mean_time_loss_s": _mean(v["time_loss"] for v in civilian),
    }
    return {"vehicles": vehicles, "summary": summary}


def summarize_evs(vehicles: Sequence[Dict[str, Any]], prefix: str = EV_PREFIX) -> Dict[str, Any]:
    """Aggregate emergency-vehicle trip records from `parse_tripinfo`."""
    evs = [v for v in vehicles if str(v["id"]).startswith(prefix)]
    return {
        "ev_count": len(evs),
        "ev_mean_duration_s": _mean(v["duration"] for v in evs),
        "ev_mean_waiting_s": _mean(v["waiting_time"] for v in evs),
        "ev_mean_waiting_count": _mean(v["waiting_count"] for v in evs),
        "ev_max_duration_s": max((v["duration"] for v in evs), default=0.0),
    }


def summarize_pedestrians(path: str) -> Dict[str, Any]:
    """Aggregate `<personinfo>` records from the tripinfo file (S4 KPIs)."""
    root = ET.parse(path).getroot()
    waits = [float(info.get("waitingTime", 0.0)) for info in root.findall("personinfo")]
    durations = [float(info.get("duration", 0.0)) for info in root.findall("personinfo")]
    if waits:
        ordered = sorted(waits)
        index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
        p95 = ordered[index]
    else:
        p95 = 0.0
    return {
        "ped_count": len(waits),
        "ped_mean_waiting_s": _mean(waits),
        "ped_p95_waiting_s": p95,
        "ped_mean_duration_s": _mean(durations),
    }


def summarize_step_csv(path: str) -> Dict[str, Any]:
    """Summarize the per-step metrics CSV written by MultiAgentEnv.close()."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {
            "steps": 0,
            "mean_step_waiting_time_s": 0.0,
            "mean_speed_m_s": 0.0,
            "arrived_vehicles": 0,
        }

    waiting = [float(row["total_waiting_time_s"]) for row in rows]
    speeds = [float(row["avg_speed_m_s"]) for row in rows if int(row["active_vehicles"]) > 0]
    arrived = sum(int(row["arrived_vehicles"]) for row in rows)
    return {
        "steps": len(rows),
        "mean_step_waiting_time_s": _mean(waiting),
        "mean_speed_m_s": _mean(speeds),
        "arrived_vehicles": arrived,
    }
