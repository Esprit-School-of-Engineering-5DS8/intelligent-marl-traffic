"""Seeded demand generation: cars, buses, emergency vehicles, pedestrians, incidents.

A *route bundle* is everything SUMO needs besides the network for one episode:
vehicle types, routed vehicles, buses, the incident vehicle and pedestrians. Bundles
are cached on disk under ``sumo_files/routes`` and keyed by a hash of every input,
so changing a config regenerates them automatically.

Each traffic component draws from its own random stream derived from the seed, so
two scenarios with the same seed share exactly the same car demand (common random
numbers make paired comparisons between scenarios meaningful).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

import numpy as np

from cotraffic import config
from cotraffic.demand.profiles import poisson_arrivals
from cotraffic.networks.build import ensure_network
from cotraffic.networks.topology import (
    OPPOSITE,
    SIDES,
    FringeEdge,
    fringe_edges,
    load_net,
    walkable_component,
)
from cotraffic.paths import CONFIG_DIR, ROUTES_DIR
from cotraffic.utils.proc import run
from cotraffic.utils.sumo import binary

STREAMS = ("cars", "emergency", "pedestrians", "buses")
# Bump when a code change alters the generated files, so cached bundles are rebuilt.
GENERATOR_VERSION = 3
# Scenario times in the configs refer to a 60-min demand hour; shorter hours scale them.
REFERENCE_HOUR_S = 3600.0


@dataclass(frozen=True)
class DemandRequest:
    network: str
    demand: str
    scenarios: tuple[str, ...] = ()
    seed: int = 0
    offset: float = 0.0  # start of the demand hour (the warm-up length in evaluation)
    duration: float = 3600.0  # length of the demand hour; vehicles depart in [0, offset + duration)
    scale: float = 1.0  # multiplies the car rate (demand calibration sweeps only)


@dataclass
class RouteBundle:
    directory: Path
    route_files: list[Path]
    additional_files: list[Path]
    meta: dict[str, Any] = field(default_factory=dict)


def _digest(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:10]


def _scenario_config(names: tuple[str, ...]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for name in names:
        merged = config.deep_merge(merged, config.load("scenarios", name))
    return merged


def _attrs(values: dict[str, Any]) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in values.items())


def write_vtypes(path: Path) -> None:
    vtypes = config.load_yaml(CONFIG_DIR / "vehicles.yaml")["vtypes"]
    lines = ["<additional>"]
    for vid, attrs in vtypes.items():
        lines.append(f"    <vType id={quoteattr(vid)} {_attrs(attrs)}/>")
    lines.append("</additional>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def reachable_exits(
    net, entries: list[FringeEdge], exits: list[FringeEdge], vclass: str = "passenger"
) -> dict[str, set[str]]:
    """Exits reachable from every entry, excluding the reverse direction of the entry itself.

    Real networks are connected but not strongly connected (one-way streets), so an
    origin-destination pair has to be checked before a trip is generated.
    """
    exit_ids = {x.edge_id for x in exits}
    out: dict[str, set[str]] = {}
    for entry in entries:
        start = net.getEdge(entry.edge_id)
        seen = {start.getID()}
        stack = [start]
        while stack:
            for nxt in stack.pop().getOutgoing():
                if nxt.getID() not in seen and nxt.allows(vclass):
                    seen.add(nxt.getID())
                    stack.append(nxt)
        reverse = {
            e.getID()
            for e in start.getToNode().getOutgoing()
            if e.getToNode() == start.getFromNode()
        }
        out[entry.edge_id] = (seen & exit_ids) - reverse
    return out


def _pick_od(
    rng: np.random.Generator,
    n: int,
    entries: list[FringeEdge],
    exits: list[FringeEdge],
    side_weights: dict[str, float],
    opposite_prob: float,
    reach: dict[str, set[str]],
) -> list[tuple[str, str]]:
    """Draw origin-destination pairs: origin side by weight x lanes, then the opposite
    side with probability ``opposite_prob``, otherwise one of the two lateral sides."""
    entries = [e for e in entries if reach.get(e.edge_id)]
    by_side_in = {s: [e for e in entries if e.side == s] for s in SIDES}
    sides = [s for s in SIDES if by_side_in[s]]
    w = np.array([side_weights.get(s, 1.0) * sum(e.lanes for e in by_side_in[s]) for s in sides])
    origin_sides = rng.choice(len(sides), size=n, p=w / w.sum())
    pairs = []
    for k in origin_sides:
        side = sides[k]
        o = by_side_in[side][rng.integers(len(by_side_in[side]))]
        feasible = reach[o.edge_id]
        out = {s: [x for x in exits if x.side == s and x.edge_id in feasible] for s in SIDES}
        opposite = OPPOSITE[side]
        others = [s for s in SIDES if s not in (side, opposite) and out[s]]
        if out[opposite] and (rng.uniform() < opposite_prob or not others):
            dest_side = opposite
        elif others:
            dest_side = others[rng.integers(len(others))]
        else:
            dest_side = side
        d = out[dest_side][rng.integers(len(out[dest_side]))]
        pairs.append((o.edge_id, d.edge_id))
    return pairs


def _route_trips(
    net_file: Path, trips: Path, vtypes: Path, out: Path, seed: int, random_factor: float
) -> None:
    run(
        [
            binary("duarouter"),
            "--net-file",
            net_file,
            "--route-files",
            trips,
            "--additional-files",
            vtypes,
            "--output-file",
            out,
            "--vtype-output",
            out.with_suffix(".types.xml"),
            "--seed",
            seed,
            "--weights.random-factor",
            random_factor,
            "--departlane",
            "best",
            "--departspeed",
            "max",
            "--no-step-log",
            "true",
            "--no-warnings",
            "true",
        ]
    )
    out.with_suffix(".types.xml").unlink(missing_ok=True)


def _line_route(net, entries, exits, line: dict[str, Any], reverse: bool) -> list[str]:
    """Edges of a bus line, given either by fringe sides/indices (grids) or by edge ids."""

    def fringe(items, side, index):
        on_side = [e for e in items if e.side == side]
        if not on_side:
            raise ValueError(f"bus line {line['id']}: no fringe edge on side {side}")
        return on_side[min(index, len(on_side) - 1)].edge_id

    if "from_edge" in line:
        key = "reverse_" if reverse else ""
        start, end = line[f"{key}from_edge"], line[f"{key}to_edge"]
    elif reverse:
        start = fringe(entries, line["to_side"], line["to_index"])
        end = fringe(exits, line["from_side"], line["from_index"])
    else:
        start = fringe(entries, line["from_side"], line["from_index"])
        end = fringe(exits, line["to_side"], line["to_index"])
    path, _cost = net.getShortestPath(net.getEdge(start), net.getEdge(end), vClass="bus")
    if not path:
        raise ValueError(f"bus line {line['id']}: no route from {start} to {end}")
    return [e.getID() for e in path]


def generate(request: DemandRequest, force: bool = False) -> RouteBundle:
    """Create (or reuse) the route bundle for ``request``."""
    net_cfg = config.load("networks", request.network)
    demand_cfg = config.load("demand", request.demand)
    scen_cfg = _scenario_config(request.scenarios)
    vtypes_cfg = config.load_yaml(CONFIG_DIR / "vehicles.yaml")
    key = _digest(
        [
            GENERATOR_VERSION,
            asdict(request),
            net_cfg.get("demand"),
            net_cfg.get("bus_lines"),
            net_cfg.get("incident"),
            demand_cfg,
            scen_cfg,
            vtypes_cfg,
            net_cfg.get("grid"),
        ]
    )
    tag = "+".join(request.scenarios) or "normal"
    level = request.demand if request.scale == 1.0 else f"{request.demand}_x{request.scale:g}"
    directory = ROUTES_DIR / request.network / f"{level}_{tag}_s{request.seed}_{key}"
    meta_file = directory / "meta.json"
    if meta_file.is_file() and not force:
        return _load_bundle(directory)
    if directory.exists():
        shutil.rmtree(directory)
    final_dir = directory
    # Build in a private directory and rename at the end: parallel runs may request the
    # same bundle, and a half-written bundle must never be visible.
    directory = final_dir.with_name(f"{final_dir.name}.tmp{os.getpid()}")
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)

    net_file = ensure_network(request.network)
    net = load_net(str(net_file))
    entries, exits = fringe_edges(net)
    reach = reachable_exits(net, entries, exits)
    streams = dict(
        zip(STREAMS, np.random.SeedSequence(request.seed).spawn(len(STREAMS)), strict=True)
    )
    rng = {name: np.random.default_rng(seq) for name, seq in streams.items()}
    end = request.offset + request.duration
    time_scale = request.duration / REFERENCE_HOUR_S
    dem = net_cfg["demand"]
    meta: dict[str, Any] = {"request": asdict(request), "network_file": str(net_file)}

    vtypes = directory / "vtypes.add.xml"
    write_vtypes(vtypes)

    # passenger cars
    rate = (
        float(dem["peak_vehicles_per_hour"]) * float(demand_cfg.get("level", 1.0)) * request.scale
    )
    times = poisson_arrivals(rate, 0.0, end, rng["cars"], demand_cfg.get("profile"), request.offset)
    ods = _pick_od(
        rng["cars"],
        len(times),
        entries,
        exits,
        dem.get("origin_side_weights", {}),
        float(dem.get("opposite_side_prob", 0.5)),
        reach,
    )
    trips = [
        (t, f"car_{i}", "car", o, d) for i, (t, (o, d)) in enumerate(zip(times, ods, strict=True))
    ]
    meta["cars"] = len(trips)

    # emergency vehicles on long routes (entry to the opposite side)
    evs = []
    if "emergency" in scen_cfg:
        ev_cfg = scen_cfg["emergency"]
        lo, hi = ev_cfg["count"]
        n_ev = int(rng["emergency"].integers(lo, hi + 1))
        w0, w1 = (float(w) * time_scale for w in ev_cfg["window_s"])
        departs = np.sort(rng["emergency"].uniform(request.offset + w0, request.offset + w1, n_ev))
        ev_ods = _pick_od(
            rng["emergency"], n_ev, entries, exits, dict.fromkeys(SIDES, 1.0), 1.0, reach
        )
        for k, (t, (o, d)) in enumerate(zip(departs, ev_ods, strict=True)):
            trips.append((float(t), f"ev_{k}", "emergency", o, d))
            evs.append({"id": f"ev_{k}", "depart": round(float(t), 2), "from": o, "to": d})
    meta["emergency"] = evs

    trips.sort(key=lambda x: x[0])
    trips_file = directory / "trips.xml"
    with trips_file.open("w", encoding="utf-8") as fh:
        fh.write("<routes>\n")
        for t, vid, vtype, o, d in trips:
            fh.write(
                f'    <trip id="{vid}" type="{vtype}" depart="{t:.2f}" from="{o}" to="{d}"/>\n'
            )
        fh.write("</routes>\n")
    vehicles = directory / "vehicles.rou.xml"
    _route_trips(
        net_file,
        trips_file,
        vtypes,
        vehicles,
        request.seed,
        float(dem.get("route_random_factor", 1.0)),
    )
    trips_file.unlink()
    route_files = [vehicles]

    # bus lines, both directions, fixed headway with a random phase per line
    if "buses" in scen_cfg:
        period = float(scen_cfg["buses"]["period_s"])
        bus_file = directory / "buses.rou.xml"
        lines_meta = []
        with bus_file.open("w", encoding="utf-8") as fh:
            fh.write("<routes>\n")
            flows = []
            for line in net_cfg.get("bus_lines", []):
                for reverse in (False, True):
                    lid = f"bus_{line['id']}_{'b' if reverse else 'a'}"
                    edges = _line_route(net, entries, exits, line, reverse)
                    fh.write(f'    <route id="{lid}" edges="{" ".join(edges)}"/>\n')
                    begin = float(rng["buses"].uniform(0.0, period))
                    flows.append((begin, lid))
                    lines_meta.append(
                        {"id": lid, "edges": len(edges), "first_departure": round(begin, 2)}
                    )
            for begin, lid in sorted(flows):
                fh.write(
                    f'    <flow id="{lid}" type="bus" route="{lid}" begin="{begin:.2f}" '
                    f'end="{end:.2f}" period="{period}" departLane="best"/>\n'
                )
            fh.write("</routes>\n")
        route_files.append(bus_file)
        meta["bus_lines"] = lines_meta

    # incident: a stopped vehicle blocking one lane
    if "incident" in scen_cfg:
        inc = scen_cfg["incident"]
        site = net_cfg["incident"]
        edge = net.getEdge(site["edge"])
        pos = float(site.get("position_frac", 0.5)) * edge.getLength()
        start = request.offset + float(inc["start_s"]) * time_scale
        inc_duration = float(inc["duration_s"]) * time_scale
        inc_file = directory / "incident.rou.xml"
        inc_file.write_text(
            "<routes>\n"
            f'    <vehicle id="incident_0" type="incident" depart="{start:.2f}" '
            f'departLane="{site["lane"]}" departPos="{pos:.1f}" departSpeed="0">\n'
            f'        <route edges="{edge.getID()}"/>\n'
            f'        <stop lane="{edge.getID()}_{site["lane"]}" endPos="{pos + 2.0:.1f}" '
            f'duration="{float(inc["duration_s"]):.0f}"/>\n'
            "    </vehicle>\n</routes>\n",
            encoding="utf-8",
        )
        route_files.append(inc_file)
        meta["incident"] = {
            "edge": edge.getID(),
            "lane": site["lane"],
            "position": round(pos, 1),
            "start": start,
            "end": start + inc_duration,
        }

    # pedestrians walking between random points of the street network
    if "pedestrians" in scen_cfg:
        rate = float(scen_cfg["pedestrians"]["persons_per_hour"])
        walkable = [net.getEdge(e) for e in walkable_component(net)]
        ped_times = poisson_arrivals(rate, 0.0, end, rng["pedestrians"])
        ped_file = directory / "persons.rou.xml"
        with ped_file.open("w", encoding="utf-8") as fh:
            fh.write("<routes>\n")
            for i, t in enumerate(ped_times):
                a, b = rng["pedestrians"].choice(len(walkable), size=2, replace=False)
                ea, eb = walkable[a], walkable[b]
                pa = rng["pedestrians"].uniform(0.0, ea.getLength())
                pb = rng["pedestrians"].uniform(0.0, eb.getLength())
                fh.write(
                    f'    <person id="ped_{i}" depart="{t:.2f}" departPos="{pa:.1f}">\n'
                    f'        <walk from="{ea.getID()}" to="{eb.getID()}" arrivalPos="{pb:.1f}"/>\n'
                    "    </person>\n"
                )
            fh.write("</routes>\n")
        route_files.append(ped_file)
        meta["pedestrians"] = len(ped_times)

    meta["route_files"] = [p.name for p in route_files]
    meta["additional_files"] = [vtypes.name]
    (directory / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    try:
        directory.rename(final_dir)
    except OSError:
        shutil.rmtree(directory, ignore_errors=True)  # another process finished first
        if not meta_file.is_file():
            raise
    return _load_bundle(final_dir)


def _load_bundle(directory: Path) -> RouteBundle:
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    routes = [directory / name for name in meta["route_files"]]
    extra = [directory / name for name in meta["additional_files"]]
    for path in routes + extra:
        if not path.is_file():
            raise FileNotFoundError(f"route bundle {directory} is incomplete: {path.name} missing")
    return RouteBundle(directory, routes, extra, meta)
