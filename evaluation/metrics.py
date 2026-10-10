"""
evaluation/metrics.py
Parse SUMO outputs into KPI summaries: tripinfo XML (per-vehicle) and the
per-step metrics CSV written by MultiAgentEnv.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def parse_tripinfo(path: str) -> Dict[str, Any]:
    """Parse a SUMO tripinfo file into per-vehicle records plus a summary."""
    root = ET.parse(path).getroot()
    vehicles: List[Dict[str, Any]] = []
    for tripinfo in root.findall("tripinfo"):
        vehicles.append({
            "id": tripinfo.get("id"),
            "duration": float(tripinfo.get("duration", 0.0)),
            "waiting_time": float(tripinfo.get("waitingTime", 0.0)),
            "time_loss": float(tripinfo.get("timeLoss", 0.0)),
            "route_length": float(tripinfo.get("routeLength", 0.0)),
            "depart": float(tripinfo.get("depart", 0.0)),
            "arrival": float(tripinfo.get("arrival", 0.0)),
        })

    summary = {
        "arrived_vehicles": len(vehicles),
        "mean_duration_s": _mean(v["duration"] for v in vehicles),
        "mean_tripinfo_waiting_s": _mean(v["waiting_time"] for v in vehicles),
        "mean_time_loss_s": _mean(v["time_loss"] for v in vehicles),
    }
    return {"vehicles": vehicles, "summary": summary}


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
