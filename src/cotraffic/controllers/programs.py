"""Signal programs of the classical baselines: fixed-time (Webster) and actuated.

Both programs cycle through exactly the phases the agents choose from (one green per
group of compatible vehicle movements, crossings red during the yellow), so a baseline
differs from an agent only in *when* it switches, not in what it can show.

We compute Webster plans ourselves rather than with SUMO's ``tlsCycleAdaptation.py``:
that script treats the pedestrian-clearance variant of each green as a phase of its
own and gives it a full share of the cycle.
"""

from __future__ import annotations

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cotraffic import config
from cotraffic.demand.generator import DemandRequest, generate
from cotraffic.envs.intersection import Intersection, yellow_state
from cotraffic.envs.simulation import Simulation
from cotraffic.networks.build import ensure_network, network_dir
from cotraffic.networks.topology import load_net, pedestrian_edges, tls_geometry
from cotraffic.utils.sumo import binary


@dataclass(frozen=True)
class WebsterPlan:
    cycle: float
    greens: tuple[float, ...]
    flow_ratios: tuple[float, ...]


def webster_plan(
    flow_ratios: Sequence[float],
    yellow: float,
    startup_lost: float,
    min_green: float,
    min_cycle: float,
    max_cycle: float,
) -> WebsterPlan:
    """Webster (1958): optimal cycle ``C = (1.5 L + 5) / (1 - Y)``, greens proportional to
    the critical flow ratio of each phase.

    ``flow_ratios[p]`` is the critical flow ratio (flow / saturation flow) of phase p,
    ``L`` the lost time per cycle (yellow + start-up loss of every phase). When the
    intersection is oversaturated (Y close to 1) the cycle is capped at ``max_cycle``.
    Displayed greens include the start-up loss, so greens + yellows = cycle, unless a
    green had to be raised to ``min_green``.
    """
    n = len(flow_ratios)
    lost = n * (yellow + startup_lost)
    y_total = float(sum(flow_ratios))
    cycle = (1.5 * lost + 5.0) / (1.0 - y_total) if y_total < 0.95 else max_cycle
    cycle = min(max(cycle, min_cycle), max_cycle)
    effective = cycle - lost
    shares = [y / y_total for y in flow_ratios] if y_total > 0 else [1.0 / n] * n
    greens = tuple(max(min_green, effective * s + startup_lost) for s in shares)
    return WebsterPlan(sum(greens) + n * yellow, greens, tuple(float(y) for y in flow_ratios))


def _movement_flows(route_file: Path, begin: float, end: float) -> dict[tuple[str, str], float]:
    """Vehicles per hour on every (incoming edge, outgoing edge) pair, from routed vehicles."""
    counts: dict[tuple[str, str], float] = defaultdict(float)
    for _, el in ET.iterparse(route_file):
        if el.tag != "vehicle":
            continue
        depart = float(el.get("depart", "0"))
        if begin <= depart < end:
            route = el.find("route")
            edges = route.get("edges", "").split() if route is not None else []
            for a, b in zip(edges, edges[1:], strict=False):
                counts[(a, b)] += 1.0
        el.clear()
    scale = 3600.0 / (end - begin)
    return {k: v * scale for k, v in counts.items()}


def _intersections(network: str) -> dict[str, Intersection]:
    """Intersection models read from the network's default programs (short SUMO start)."""
    net_file = ensure_network(network)
    net = load_net(str(net_file))
    crossings, _ = pedestrian_edges(net)
    geometry = tls_geometry(
        net_file, float(config.load("networks", network)["neighbours"]["max_distance_m"])
    )
    protocol = config.load_protocol()
    sim = Simulation()
    conn = sim.start(
        [
            binary("sumo"),
            "--net-file",
            str(net_file),
            "--no-step-log",
            "true",
            "--no-warnings",
            "true",
        ]
    )
    try:
        yellow = float(protocol["timing"]["yellow_time"])
        return {
            tid: Intersection(conn, tid, geometry[tid], crossings, yellow, 1)
            for tid in sorted(geometry)
        }
    finally:
        sim.close()


def _critical_ratios(
    inter: Intersection, flows: Mapping[tuple[str, str], float], saturation: float
) -> list[float]:
    """Critical flow ratio of each phase: the most loaded lane among those it serves."""
    lane_flow: dict[str, float] = defaultdict(float)
    by_movement: dict[tuple[str, str], list] = defaultdict(list)
    for link in inter.links:
        if not link.crossing:
            key = (link.in_lane.rsplit("_", 1)[0], link.out_lane.rsplit("_", 1)[0])
            by_movement[key].append(link)
    for movement, links in by_movement.items():
        lanes = {lk.in_lane for lk in links}
        for lane in lanes:
            lane_flow[lane] += flows.get(movement, 0.0) / len(lanes)
    return [
        max((lane_flow[ln] / saturation for ln in lanes), default=0.0)
        for lanes in inter.phase_lanes
    ]


def _digest(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:8]


def _write_programs(
    path: Path,
    programs: Mapping[str, list[dict[str, Any]]],
    kind: str,
    program_id: str,
    params: Mapping[str, Any] | None = None,
) -> None:
    root = ET.Element("additional")
    for tid, phases in programs.items():
        tl = ET.SubElement(root, "tlLogic", id=tid, type=kind, programID=program_id, offset="0")
        for key, value in (params or {}).items():
            ET.SubElement(tl, "param", key=key, value=str(value))
        for ph in phases:
            ET.SubElement(tl, "phase", {k: str(v) for k, v in ph.items()})
    ET.indent(root)
    _atomic_write(path, ET.tostring(root, encoding="unicode") + "\n")


def _atomic_write(path: Path, text: str) -> None:
    """Write then rename, so a parallel run never reads a half-written file."""
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _cycle_phases(
    inter: Intersection,
    greens: Sequence[float],
    yellow: float,
    extra: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    phases = []
    n = inter.n_phases
    for p in range(n):
        phases.append(
            {"duration": round(greens[p], 1), "state": inter.green_states[p], **(extra or {})}
        )
        if n > 1:
            nxt = inter.green_states[(p + 1) % n]
            phases.append(
                {
                    "duration": yellow,
                    "state": yellow_state(inter.green_states[p], nxt, inter.crossing_signals),
                }
            )
    return phases


def webster_program(network: str, demand: str, scale: float = 1.0) -> Path:
    """Fixed-time plan tuned by Webster's method on the demand level ``demand``.

    Flows come from one realisation reserved for tuning (``webster_tuning_seed``), never
    from an evaluation seed, and cover the measured hour.
    """
    protocol = config.load_protocol()
    b, t, ev = protocol["baselines"], protocol["timing"], protocol["evaluation"]
    net_cfg, demand_cfg = config.load("networks", network), config.load("demand", demand)
    key = _digest(b, t, ev, net_cfg, demand_cfg, scale, 1)
    out = network_dir(network) / "tls" / f"ft_{demand}_{key}.add.xml"
    if out.is_file():
        return out
    bundle = generate(
        DemandRequest(
            network,
            demand,
            (),
            int(b["webster_tuning_seed"]),
            float(ev["warmup_s"]),
            float(ev["measure_s"]),
            scale,
        )
    )
    begin = float(ev["warmup_s"])
    flows = _movement_flows(bundle.route_files[0], begin, begin + float(ev["measure_s"]))
    programs, report = {}, {}
    for tid, inter in _intersections(network).items():
        ratios = _critical_ratios(inter, flows, float(b["saturation_flow_veh_h"]))
        plan = webster_plan(
            ratios,
            float(t["yellow_time"]),
            float(b["startup_lost_s"]),
            float(t["min_green"]),
            float(b["min_cycle_s"]),
            float(b["max_cycle_s"]),
        )
        programs[tid] = _cycle_phases(inter, plan.greens, float(t["yellow_time"]))
        report[tid] = {
            "cycle": round(plan.cycle, 1),
            "greens": [round(g, 1) for g in plan.greens],
            "Y": round(sum(plan.flow_ratios), 3),
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(out.with_suffix(".json"), json.dumps(report, indent=2))
    _write_programs(out, programs, "static", "ft")
    return out


def actuated_program(network: str) -> Path:
    """Gap-based actuated control on the same phases (SUMO's ``actuated`` type).

    A green lasts at least ``min_green`` and at most ``max_green``; it ends earlier when
    the gap between vehicles crossing the detectors exceeds ``actuated_max_gap_s``.
    """
    protocol = config.load_protocol()
    b, t = protocol["baselines"], protocol["timing"]
    key = _digest(b, t, config.load("networks", network), 1)
    out = network_dir(network) / "tls" / f"act_{key}.add.xml"
    if out.is_file():
        return out
    programs = {}
    for tid, inter in _intersections(network).items():
        greens = [float(t["min_green"])] * inter.n_phases
        extra = {"minDur": t["min_green"], "maxDur": t["max_green"]}
        programs[tid] = _cycle_phases(inter, greens, float(t["yellow_time"]), extra)
    params = {
        "max-gap": b["actuated_max_gap_s"],
        "detector-gap": b["actuated_detector_gap_s"],
        "show-detectors": "false",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_programs(out, programs, "actuated", "act", params)
    return out
