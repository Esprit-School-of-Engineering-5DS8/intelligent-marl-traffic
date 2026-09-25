"""Evaluation metrics computed from SUMO's output files.

Definitions (also in the report, section 7):

* Population: every vehicle (car, bus, emergency vehicle; never the incident vehicle)
  whose *intended* departure time lies in the measured window
  ``[warmup, warmup + measure)``. Vehicles of the warm-up are simulated but not counted.
* Travel time: arrival - intended departure, so time spent waiting to enter the network
  counts. A vehicle still in the network (or never inserted) at the end of the
  cool-down gets ``end - intended departure`` (a censored lower bound) and is counted
  as unfinished. A vehicle that teleported gets ``teleport_penalty_s`` added: a
  teleport hides a jam and must never make a method look better.
* Waiting time: time at speed < 0.1 m/s plus the insertion delay. Time loss: time lost
  against driving at the desired speed, plus the insertion delay.
* Queue: mean number of halting vehicles in the network over the measured window
  (SUMO summary output). Throughput: vehicles that reached their destination during the
  measured window, per hour.
* Emissions (HBEFA4): totals over the population, per-km values = total / distance driven.
* Stops: number of times a vehicle came to a halt (SUMO ``waitingCount``).
* Safety: SSM conflicts with minimum time-to-collision < threshold inside the window,
  each pair of vehicles counted once; hard-braking events (whole episode, from SUMO's
  statistics); shield interventions (from the environment).
* Equity: 95th percentile and maximum of the waiting times; Gini coefficient of the
  waiting times (0 = everybody waits the same, 1 = one vehicle does all the waiting).
* People: person-weighted delay = sum(occupancy x time loss) / sum(occupancy), with the
  occupancies of ``configs/protocol.yaml``; pedestrians' waiting times from personinfo.
* Priority: emergency vehicles' travel time, delay (time loss) and free-flow time.
* Incident: travel time and time loss of the vehicles whose route crosses the blocked
  approach and that depart from 10 min before the incident to its end.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cotraffic.envs.rewards import vehicle_kind

WAIT_BIN_S = 15.0
VEHICLE_COLUMNS = [
    "id",
    "kind",
    "depart",
    "depart_delay",
    "arrival",
    "duration",
    "route_length",
    "waiting_time",
    "waiting_count",
    "time_loss",
    "co2_mg",
    "nox_mg",
    "fuel_mg",
]


def _f(el: ET.Element, key: str, default: float = 0.0) -> float:
    value = el.get(key)
    return float(value) if value not in (None, "") else default


def parse_tripinfo(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vehicles and persons of a tripinfo file (unfinished trips have arrival = -1)."""
    vehicles, persons = [], []
    for _, el in ET.iterparse(path):
        if el.tag == "tripinfo":
            em = el.find("emissions")
            vehicles.append(
                {
                    "id": el.get("id"),
                    "kind": vehicle_kind(el.get("id")),
                    "depart": _f(el, "depart"),
                    "depart_delay": _f(el, "departDelay"),
                    "arrival": _f(el, "arrival", -1.0),
                    "duration": _f(el, "duration"),
                    "route_length": _f(el, "routeLength"),
                    "waiting_time": _f(el, "waitingTime"),
                    "waiting_count": _f(el, "waitingCount"),
                    "time_loss": _f(el, "timeLoss"),
                    "co2_mg": _f(em, "CO2_abs") if em is not None else 0.0,
                    "nox_mg": _f(em, "NOx_abs") if em is not None else 0.0,
                    "fuel_mg": _f(em, "fuel_abs") if em is not None else 0.0,
                }
            )
            el.clear()
        elif el.tag == "personinfo":
            persons.append(
                {
                    "id": el.get("id"),
                    "depart": _f(el, "depart"),
                    "duration": _f(el, "duration"),
                    "waiting_time": _f(el, "waitingTime"),
                    "time_loss": _f(el, "timeLoss"),
                    "arrival": max((_f(w, "arrival", -1.0) for w in el.iter("walk")), default=-1.0),
                }
            )
            el.clear()
    return pd.DataFrame(vehicles, columns=VEHICLE_COLUMNS), pd.DataFrame(persons)


def planned_vehicles(route_files: list[Path], edge: str | None = None) -> pd.DataFrame:
    """Every vehicle SUMO was asked to insert, with its intended departure time and, when
    ``edge`` is given, whether its route uses that edge."""
    rows = []
    routes: dict[str, list[str]] = {}
    for path in route_files:
        for _, el in ET.iterparse(path):
            if el.tag == "route" and el.get("id"):
                routes[el.get("id")] = el.get("edges", "").split()
            elif el.tag == "vehicle":
                route = el.find("route")
                edges = route.get("edges", "").split() if route is not None else []
                rows.append(
                    {
                        "id": el.get("id"),
                        "planned_depart": _f(el, "depart"),
                        "uses_edge": edge in edges,
                    }
                )
            elif el.tag == "flow":
                begin, end, period = _f(el, "begin"), _f(el, "end"), _f(el, "period")
                uses = edge in routes.get(el.get("route", ""), [])
                if period > 0:
                    for k, t in enumerate(np.arange(begin, end, period)):
                        rows.append(
                            {
                                "id": f"{el.get('id')}.{k}",
                                "planned_depart": float(t),
                                "uses_edge": uses,
                            }
                        )
            if el.tag in ("vehicle", "flow", "person"):
                el.clear()
    return pd.DataFrame(rows, columns=["id", "planned_depart", "uses_edge"])


def parse_statistics(path: Path) -> dict[str, float]:
    root = ET.parse(path).getroot()
    out: dict[str, float] = {}
    for tag, keys in {
        "teleports": ("total", "jam", "yield", "wrongLane"),
        "safety": ("collisions", "emergencyStops", "emergencyBraking"),
        "vehicles": ("loaded", "inserted", "running", "waiting"),
        "personTeleports": ("total",),
    }.items():
        el = root.find(tag)
        for key in keys:
            out[f"{tag}_{key}"] = _f(el, key) if el is not None else 0.0
    return out


def parse_summary(path: Path) -> pd.DataFrame:
    rows = []
    for _, el in ET.iterparse(path):
        if el.tag == "step":
            rows.append(
                {
                    "time": _f(el, "time"),
                    "running": _f(el, "running"),
                    "waiting": _f(el, "waiting"),
                    "halting": _f(el, "halting"),
                    "arrived": _f(el, "arrived"),
                    "mean_waiting_time": _f(el, "meanWaitingTime"),
                    "mean_speed": _f(el, "meanSpeed"),
                }
            )
            el.clear()
    return pd.DataFrame(rows)


def count_conflicts(path: Path, ttc_threshold: float, begin: float, end: float) -> int:
    """SSM encounters with minimum TTC below the threshold, each vehicle pair once."""
    seen = set()
    if not path.is_file():
        return 0
    for _, el in ET.iterparse(path):
        if el.tag != "conflict":
            continue
        start = _f(el, "begin")
        ttc = el.find("minTTC")
        valid = ttc is not None and ttc.get("value") not in (None, "NA")
        if valid and begin <= start < end and float(ttc.get("value")) < ttc_threshold:
            pair = tuple(sorted((el.get("ego"), el.get("foe"))))
            seen.add((pair, start))
        el.clear()
    return len(seen)


def gini(values: np.ndarray) -> float:
    """Gini coefficient of non-negative values (0 when all equal or all zero)."""
    x = np.sort(np.asarray(values, dtype=float))
    if x.size == 0 or x.sum() <= 0:
        return 0.0
    n = x.size
    return float((2.0 * np.sum(np.arange(1, n + 1) * x) / (n * x.sum())) - (n + 1) / n)


def compute_metrics(
    output_dir: Path,
    route_files: list[Path],
    window: tuple[float, float],
    end_time: float,
    protocol: Mapping[str, Any],
    teleported: set[str] | frozenset[str] = frozenset(),
    ssm: bool = True,
    incident: Mapping[str, Any] | None = None,
) -> tuple[dict[str, float], pd.DataFrame, pd.DataFrame]:
    """All metrics of one episode, the per-minute time series of the network and the
    histogram of the vehicles' waiting times (for the equity figure)."""
    begin, finish = window
    penalty = float(protocol["evaluation"]["teleport_penalty_s"])
    occupancy = {k: float(v) for k, v in protocol["occupancy"].items()}
    vehicles, persons = parse_tripinfo(output_dir / "tripinfo.xml")
    planned = planned_vehicles(route_files, incident["edge"] if incident else None)
    planned = planned[~planned["id"].str.startswith("incident_")]
    pop = planned[(planned["planned_depart"] >= begin) & (planned["planned_depart"] < finish)]
    pop = pop.merge(vehicles, on="id", how="left")
    if pop.empty:
        raise ValueError("no vehicle departed in the measured window")
    pop["kind"] = pop["id"].map(vehicle_kind)
    inserted = pop["depart"].notna()
    finished = inserted & (pop["arrival"] >= 0)
    teleported_mask = pop["id"].isin(teleported)
    for col in (
        "depart_delay",
        "waiting_time",
        "time_loss",
        "waiting_count",
        "route_length",
        "co2_mg",
        "nox_mg",
        "fuel_mg",
    ):
        pop[col] = pop[col].fillna(0.0)

    travel = np.where(
        finished, pop["arrival"] - pop["planned_depart"], end_time - pop["planned_depart"]
    )
    travel = travel + np.where(teleported_mask, penalty, 0.0)
    never = ~inserted
    waiting = np.where(
        never, end_time - pop["planned_depart"], pop["waiting_time"] + pop["depart_delay"]
    )
    time_loss = np.where(
        never, end_time - pop["planned_depart"], pop["time_loss"] + pop["depart_delay"]
    )
    occ = pop["kind"].map(occupancy).fillna(1.0).to_numpy()
    distance_km = pop["route_length"].sum() / 1000.0

    m: dict[str, float] = {
        "vehicles": float(len(pop)),
        "completed": float(finished.sum()),
        "unfinished": float((~finished).sum()),
        "never_inserted": float(never.sum()),
        "teleported_vehicles": float(teleported_mask.sum()),
        "mean_travel_time": float(np.mean(travel)),
        "mean_travel_time_completed": float(np.mean(travel[finished & ~teleported_mask]))
        if (finished & ~teleported_mask).any()
        else float("nan"),
        "mean_waiting_time": float(np.mean(waiting)),
        "mean_time_loss": float(np.mean(time_loss)),
        "mean_depart_delay": float(pop["depart_delay"].mean()),
        "p25_waiting_time": float(np.percentile(waiting, 25)),
        "median_waiting_time": float(np.percentile(waiting, 50)),
        "p75_waiting_time": float(np.percentile(waiting, 75)),
        "p90_waiting_time": float(np.percentile(waiting, 90)),
        "p95_waiting_time": float(np.percentile(waiting, 95)),
        "max_waiting_time": float(np.max(waiting)),
        "gini_waiting_time": gini(waiting),
        "stops_per_vehicle": float(pop["waiting_count"].mean()),
        "co2_total_kg": float(pop["co2_mg"].sum() / 1e6),
        "co2_g_per_km": float(pop["co2_mg"].sum() / 1e3 / distance_km) if distance_km > 0 else 0.0,
        "nox_total_g": float(pop["nox_mg"].sum() / 1e3),
        "fuel_total_kg": float(pop["fuel_mg"].sum() / 1e6),
        "person_weighted_delay": float(np.sum(occ * time_loss) / np.sum(occ)),
        "distance_km": float(distance_km),
    }
    if incident:
        # vehicles whose route crosses the blocked approach, from 10 min before the incident
        # to its end: the network-wide mean dilutes a local event
        start, stop = float(incident["start"]), float(incident["end"])
        hit = (
            pop["uses_edge"]
            & (pop["planned_depart"] >= start - 600)
            & (pop["planned_depart"] < stop)
        ).to_numpy()
        m["incident_affected_vehicles"] = float(hit.sum())
        if hit.any():
            m["incident_affected_travel_time"] = float(np.mean(travel[hit]))
            m["incident_affected_time_loss"] = float(np.mean(time_loss[hit]))
    arrivals = vehicles[(vehicles["arrival"] >= begin) & (vehicles["arrival"] < finish)]
    arrivals = arrivals[~arrivals["id"].str.startswith("incident_")]
    m["throughput_per_h"] = float(len(arrivals) * 3600.0 / (finish - begin))

    for kind in ("bus", "emergency"):
        sel = (pop["kind"] == kind).to_numpy()
        prefix = "bus" if kind == "bus" else "ev"
        if sel.any():
            m[f"{prefix}_count"] = float(sel.sum())
            m[f"{prefix}_travel_time"] = float(np.mean(travel[sel]))
            m[f"{prefix}_delay"] = float(np.mean(time_loss[sel]))
            if kind == "emergency":
                m["ev_free_flow_time"] = float(
                    np.mean(pop.loc[sel, "duration"] - pop.loc[sel, "time_loss"])
                )
                m["ev_max_delay"] = float(np.max(time_loss[sel]))
    if not persons.empty:
        ped = persons[(persons["depart"] >= begin) & (persons["depart"] < finish)]
        if not ped.empty:
            m["ped_count"] = float(len(ped))
            m["ped_mean_waiting_time"] = float(ped["waiting_time"].mean())
            m["ped_max_waiting_time"] = float(ped["waiting_time"].max())
            m["ped_mean_time_loss"] = float(ped["time_loss"].mean())

    stats = parse_statistics(output_dir / "statistics.xml")
    m["teleports_total"] = stats["teleports_total"]
    m["collisions"] = stats["safety_collisions"]
    m["hard_braking_events"] = stats["safety_emergencyBraking"]
    if ssm:
        threshold = float(str(protocol["sumo"]["ssm"]["thresholds"]).split()[0])
        m["ssm_conflicts"] = float(
            count_conflicts(output_dir / "ssm.xml", threshold, begin, finish)
        )
        m["ssm_conflicts_per_1000_veh"] = 1000.0 * m["ssm_conflicts"] / max(1.0, m["vehicles"])

    summary = parse_summary(output_dir / "summary.xml")
    window_rows = summary[(summary["time"] >= begin) & (summary["time"] < finish)]
    m["mean_queue"] = float(window_rows["halting"].mean())
    m["mean_insertion_backlog"] = float(window_rows["waiting"].mean())
    series = (
        summary.assign(minute=(summary["time"] // 60).astype(int))
        .groupby("minute")
        .agg(
            halting=("halting", "mean"),
            running=("running", "mean"),
            waiting=("waiting", "mean"),
            mean_waiting_time=("mean_waiting_time", "mean"),
            mean_speed=("mean_speed", "mean"),
        )
        .reset_index()
    )
    edges = np.append(np.arange(0.0, 900.0 + 1e-9, WAIT_BIN_S), np.inf)
    counts, _ = np.histogram(waiting, bins=edges)
    distribution = pd.DataFrame(
        {"wait_from_s": edges[:-1], "wait_to_s": edges[1:], "vehicles": counts}
    )
    return m, series, distribution
