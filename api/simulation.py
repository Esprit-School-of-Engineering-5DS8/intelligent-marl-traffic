"""Live dashboard simulation, driven by the ``cotraffic`` domain.

The live run must be *the same* thing the study reports: the controller comes from
``make_controller`` (the active policy: learned checkpoint, LLM, or baseline), the episode
comes from ``evaluation_episode`` (the protocol's quick windows), and every phase change
passes the environment's safety shield. Nothing here talks to SUMO directly except to read
the state it publishes to the dashboard.
"""

from __future__ import annotations

import heapq
import math
import random
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter, deque
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

import pyproj

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api import policy
from cotraffic import config
from cotraffic.controllers.registry import make_controller
from cotraffic.envs.episodes import evaluation_episode
from cotraffic.envs.traffic_env import CoTrafficEnv
from cotraffic.forecast import project as project_forecast
from cotraffic.networks.build import ensure_network
from cotraffic.paths import RESULTS_DIR

# The dashboard's scenario ids → cotraffic network names (configs/networks/<name>.yaml).
# The grids are the real San Francisco Mission corridors; monaco and tunis are OSM too.
SCENARIOS = {
    "grid-2x2": "sf_mission_2x2",
    "grid-3x3": "sf_mission_3x3",
    "monaco": "monaco",
    "tunis": "tunis",
}
# The inverse map, so a request can name the network it wants and land on the
# scenario that simulates it.
NETWORK_SCENARIOS = {network: scenario for scenario, network in SCENARIOS.items()}
DEFAULT_SCENARIO = "grid-3x3"
DEMAND = "medium"
# The operator's demand dial on the live map. Each level is a fraction of the
# network's own live rate, so "high" is the calibrated live window and the other two
# thin it out. The live run regenerates demand every cycle, so a change lands within
# one window rather than needing a restart.
DEMAND_LEVELS: dict[str, float] = {"low": 0.45, "medium": 0.7, "high": 1.0}
DEFAULT_DEMAND_LEVEL = "high"
MIN_GREEN_S = 6.0
MAX_GREEN_S = 90.0
JUNCTION_HISTORY = 180
# The map is published once per simulated step, but never faster than this wall-clock
# gap: at high sim speeds the sub-steps are back to back and only add payload.
FRAME_MIN_WALL_S = 0.05


class NotRunning(RuntimeError):
    """The requested control or measurement needs a live run."""


def resolve_scenario(
    scenario: str | None = None, network: str | None = None
) -> str:
    """The live scenario a start request means, from either id it may name.

    A caller asking for a network gets that network, whatever the stored policy is
    pointed at; a caller naming both must name a matching pair, because silently
    running the *other* network is how a request for the 2x2 grid started 3x3.
    """
    if network is not None and network not in NETWORK_SCENARIOS:
        raise ValueError(f"unknown network {network!r}")
    if scenario is not None and scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    if network is None:
        return scenario or DEFAULT_SCENARIO
    requested = NETWORK_SCENARIOS[network]
    if scenario is not None and scenario != requested:
        raise ValueError(
            f"scenario {scenario!r} runs on {SCENARIOS[scenario]}, not the requested {network}"
        )
    return requested

# Real networks use the CRS in their own ``<location>`` tag (see
# ``_geo_projection``); this map is empty because every scenario now has geography.
GRID_BOUNDS = {}

_osm_bounds: dict[str, dict[str, float]] = {}


def live_demand(net_cfg: dict[str, Any]) -> tuple[str, float]:
    """Demand level and car-rate multiplier the live view runs a network at.

    One fixed level made a city-scale net look empty and a four-junction corridor
    look busy, so each network declares the rate its live window should carry
    (``demand.live_vehicles_per_hour``). Benchmark episodes do not use this: they
    keep the calibrated ``peak_vehicles_per_hour`` cell.
    """
    dem = net_cfg.get("demand") or {}
    peak = float(dem.get("peak_vehicles_per_hour") or 0.0)
    rate = dem.get("live_vehicles_per_hour")
    if rate and peak > 0:
        return "peak", float(rate) / peak
    return DEMAND, 1.0


def live_demand_scale(net_cfg: dict[str, Any], level: str) -> float:
    """The car-rate multiplier the live view runs one network at, for an operator level.

    The live view already runs each network at its own calibrated rate rather than a
    shared demand level (see :func:`live_demand`), so the operator dial multiplies
    *that* baseline instead of replacing it. ``high`` is therefore exactly the
    behaviour the live map had before the dial existed, and ``low``/``medium`` are
    fractions of it. Multiplying the shared ``level`` instead would have made the
    dial mean something different on every network.
    """
    if level not in DEMAND_LEVELS:
        raise ValueError(f"unknown demand level {level!r}")
    _, base = live_demand(net_cfg)
    return base * DEMAND_LEVELS[level]


def _bounds(scenario: str) -> dict[str, float]:
    """Fallback map extent: the configured OSM bbox for the scenario."""
    if scenario in GRID_BOUNDS:
        return GRID_BOUNDS[scenario]
    network = SCENARIOS[scenario]
    if network not in _osm_bounds:
        west, south, east, north = config.load("networks", network)["osm"]["bbox"]
        _osm_bounds[network] = {"west": west, "south": south, "east": east, "north": north}
    return _osm_bounds[network]


def _xy(pair: str) -> tuple[float, float] | None:
    """Parse a SUMO shape point; nets built in 3D (MoSTScenario) carry x,y,z."""
    parts = pair.split(",")
    if len(parts) < 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _net_file(scenario: str) -> Path:
    return ensure_network(SCENARIOS[scenario])


@lru_cache(maxsize=4)
def _extent(scenario: str) -> tuple[float, float, float, float]:
    """Bounding box of every lane shape in the network SUMO actually simulates."""
    xs: list[float] = []
    ys: list[float] = []
    for edge in ET.parse(_net_file(scenario)).getroot().findall("edge"):
        if edge.get("id", "").startswith(":"):
            continue
        for lane in edge.findall("lane"):
            for pair in (lane.get("shape") or "").split():
                point = _xy(pair)
                if point is None:
                    continue
                xs.append(point[0])
                ys.append(point[1])
    if not xs or not ys:
        return (0.0, 1.0, 0.0, 1.0)
    return (min(xs), max(xs), min(ys), max(ys))


@lru_cache(maxsize=4)
def _geo_projection(scenario: str) -> tuple[pyproj.Proj, tuple[float, float]] | None:
    """The network's projected CRS and SUMO's net offset, or ``None`` if missing.

    Real networks are built in a projected CRS (UTM zone 32 for Monaco and Tunis, zone 10
    for the San Francisco grids) and
    SUMO stores their coordinates shifted by ``netOffset``. The net's ``<location>`` tag
    names that CRS, so inverting it is what puts the roads on the basemap. Stretching the
    network's bounding box onto the geographic extent instead ignores the meridian
    convergence and the true scale, which rotated and shifted Monaco by over a kilometre.
    """
    location = ET.parse(_net_file(scenario)).getroot().find("location")
    if location is None:
        return None
    params = location.get("projParameter", "!")
    if params in ("", "!"):
        return None
    x_off, y_off = (float(value) for value in (location.get("netOffset") or "0,0").split(",")[:2])
    return pyproj.Proj(projparams=params), (x_off, y_off)


def _remaining_green(conn: Any, tls_id: str, sim_time: int) -> float | None:
    """Seconds left in the current phase, or None when the plan holds it open.

    A TLS on a fixed programme reports a real next switch; one held on a 86400s
    default phase reports a value far beyond any plausible green, which the panels
    must show as unknown rather than as a split.
    """
    try:
        remaining = float(conn.trafficlight.getNextSwitch(tls_id)) - float(sim_time)
    except Exception:
        return None
    if 0.0 < remaining <= MAX_GREEN_S:
        return round(remaining, 1)
    return None


def _project(scenario: str, x: float, y: float) -> list[float]:
    """SUMO network coordinates (x, y) → WGS84 [longitude, latitude]."""
    projection = _geo_projection(scenario)
    if projection is not None:
        proj, (x_off, y_off) = projection
        longitude, latitude = proj(x - x_off, y - y_off, inverse=True)
        return [round(longitude, 7), round(latitude, 7)]
    bounds = _bounds(scenario)
    min_x, max_x, min_y, max_y = _extent(scenario)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    longitude = bounds["west"] + (x - min_x) / span_x * (bounds["east"] - bounds["west"])
    latitude = bounds["south"] + (y - min_y) / span_y * (bounds["north"] - bounds["south"])
    return [round(longitude, 7), round(latitude, 7)]


def _thin(points: list[list[float]], max_points: int = 120) -> list[list[float]]:
    """Keep a route polyline small enough for the 4 Hz live snapshot."""
    if len(points) <= max_points:
        return points
    step = max(1, len(points) // max_points)
    thinned = points[::step]
    if thinned[-1] != points[-1]:
        thinned.append(points[-1])
    return thinned


def _vehicle_length(conn: Any, vehicle_id: str) -> float:
    """Body length of one vehicle, so the map can draw the crash at its real size."""
    try:
        value = float(conn.vehicle.getLength(vehicle_id))
    except Exception:
        return 4.5
    return round(value, 2) if value > 0 else 4.5


def _polyline_meters(points: list[list[float]]) -> float | None:
    """Great-circle length of a [lng, lat] polyline, in metres.

    Used as the dispatch approach distance when the ambulance has been added to the
    network but has not departed yet: TraCI cannot answer a driving distance for a
    vehicle that is not on a lane, and a null there would leave the panel's progress
    bar with nothing to measure against.
    """
    if not isinstance(points, list) or len(points) < 2:
        return None
    total = 0.0
    for (lng_a, lat_a), (lng_b, lat_b) in zip(points, points[1:]):
        try:
            ax, ay = float(lng_a), float(lat_a)
            bx, by = float(lng_b), float(lat_b)
        except (TypeError, ValueError):
            continue
        phi_a, phi_b = math.radians(ay), math.radians(by)
        d_phi = phi_b - phi_a
        d_lambda = math.radians(bx - ax)
        h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
        total += 2 * 6_371_000.0 * math.asin(min(1.0, math.sqrt(h)))
    return round(total, 1) if total > 0 else None


@lru_cache(maxsize=4)
def network_geojson(scenario: str) -> dict[str, Any]:
    """GeoJSON of the network the live session runs (same projection as the vehicles)."""
    if scenario not in SCENARIOS:
        raise ValueError("unknown simulation scenario")
    root = ET.parse(_net_file(scenario)).getroot()
    features: list[dict[str, Any]] = []
    for edge in root.findall("edge"):
        edge_id = edge.get("id", "")
        if edge_id.startswith(":"):
            continue
        for lane in edge.findall("lane"):
            if "pedestrian" in (lane.get("allow") or "").split():
                continue
            points = []
            for pair in (lane.get("shape") or "").split():
                point = _xy(pair)
                if point is not None:
                    points.append(_project(scenario, *point))
            if len(points) >= 2:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "id": lane.get("id", edge_id),
                        "edge": edge_id,
                        # The street name the net was imported with, so the panels can
                        # say "Mission Street" instead of a SUMO edge id.
                        "name": edge.get("name") or edge_id,
                        "laneIndex": lane.get("index", "0"),
                        "width": lane.get("width", "3.2"),
                    },
                    "geometry": {"type": "LineString", "coordinates": points},
                })

    lane_positions = signalLanePositions(scenario)
    signals_meta: list[dict[str, Any]] = []
    for junction in root.findall("junction"):
        if junction.get("type") != "traffic_light":
            continue
        try:
            x, y = float(junction.get("x", "")), float(junction.get("y", ""))
        except ValueError:
            continue
        longitude, latitude = _project(scenario, x, y)
        signals_meta.append({
            "id": junction.get("id", ""), "x": x, "y": y, "lng": longitude, "lat": latitude,
            "lanes": lane_positions.get(junction.get("id", ""), []),
        })
    # A joined TLS (`joinedS_…`) controls several junctions and has no junction
    # element of its own, so place its marker at the mean of its stop lines.
    known_signals = {signal["id"] for signal in signals_meta}
    for tls_id, lanes in lane_positions.items():
        if tls_id in known_signals or not lanes:
            continue
        signals_meta.append({
            "id": tls_id,
            "x": sum(entry["x"] for entry in lanes) / len(lanes),
            "y": sum(entry["y"] for entry in lanes) / len(lanes),
            "lng": sum(entry["lng"] for entry in lanes) / len(lanes),
            "lat": sum(entry["lat"] for entry in lanes) / len(lanes),
            "lanes": lanes,
        })

    # Supply exact motor-vehicle lane geometry for the Three.js view; leave
    # pedestrian lanes out of the road overlay entirely.
    sumo_lanes: list[dict[str, Any]] = []
    for edge in root.findall("edge"):
        edge_id = edge.get("id", "")
        if edge_id.startswith(":"):
            continue
        for lane in edge.findall("lane"):
            if "pedestrian" in (lane.get("allow") or "").split():
                continue
            points = []
            for pair in (lane.get("shape") or "").split():
                point = _xy(pair)
                if point is not None:
                    points.append([point[0], point[1]])
            if len(points) < 2:
                continue
            lane_data = {
                "id": lane.get("id", edge_id),
                "laneIndex": int(lane.get("index", "0") or 0),
                "width": float(lane.get("width", "3.2") or 3.2),
                "shape": points,
            }
            lane_data["allow"] = (lane.get("allow") or "").split()
            lane_data["disallow"] = (lane.get("disallow") or "").split()
            sumo_lanes.append(lane_data)
    return {
        "type": "FeatureCollection",
        "features": features,
        "signals": signals_meta,
        "sumoLanes": sumo_lanes,
    }


@lru_cache(maxsize=4)
def signalLanePositions(scenario: str) -> dict[str, list[dict[str, Any]]]:
    """Per-lane light positions: for each signalised junction, one entry per
    controlled lane (in TLS state-string order) at its stop-line end, in SUMO x/y.
    """
    import sumolib

    root = ET.parse(_net_file(scenario)).getroot()
    net = sumolib.net.readNet(str(_net_file(scenario)))
    result: dict[str, list[dict[str, Any]]] = {
        tls.getID(): [] for tls in net.getTrafficLights()
    }
    # Gather movement links by their incoming lane, then emit exactly one
    # signal head for every drivable inbound lane at each signalized junction.
    # Some imported lanes have no legal SUMO connection at that node; keep a
    # visible head for those too, with an empty linkIndices list (red fallback).
    controlled: dict[str, dict[str, set[int]]] = {
        tls_id: {} for tls_id in result
    }
    for elem in root.iter("connection"):
        tls_id = elem.get("tl")
        if tls_id not in controlled or elem.get("dir", "") == "s":
            continue
        lane_id = f"{elem.get('from', '')}_{elem.get('fromLane', '0')}"
        controlled[tls_id].setdefault(lane_id, set()).add(int(elem.get("linkIndex", "0")))

    # Every inbound lane each TLS names, straight movements included: a joined
    # signal (one controller over several junctions) has no node of its own, so
    # its lanes must come from the net's connections.
    tls_lanes: dict[str, set[str]] = {tls_id: set() for tls_id in result}
    for elem in root.iter("connection"):
        tls_id = elem.get("tl")
        if tls_id not in tls_lanes:
            continue
        tls_lanes[tls_id].add(f"{elem.get('from', '')}_{elem.get('fromLane', '0')}")

    for tls_id in result:
        entries: list[dict[str, Any]] = []
        try:
            node = net.getNode(tls_id)
            lanes = [lane for edge in node.getIncoming() for lane in edge.getLanes()]
        except KeyError:
            # Joined traffic light: its id belongs to no single junction node, so
            # derive the controlled lanes from the connections that reference it.
            lanes = []
            for lane_id in sorted(tls_lanes[tls_id]):
                try:
                    lanes.append(net.getLane(lane_id))
                except KeyError:
                    continue
        for lane in lanes:
            if not lane.allows("passenger"):
                continue
            shape = lane.getShape()
            if not shape:
                continue
            # Lane shapes are net-local — the same space vehicles arrive
            # in from TraCI — so use their stop-line endpoint directly.
            x, y = shape[-1][0], shape[-1][1]
            longitude, latitude = _project(scenario, x, y)
            entries.append({
                "lane": lane.getID(),
                "laneIndex": lane.getIndex(),
                "linkIndices": sorted(controlled[tls_id].get(lane.getID(), set())),
                "x": x,
                "y": y,
                "lng": longitude,
                "lat": latitude,
                "edge": lane.getEdge().getID(),
            })
        result[tls_id] = entries
    return result


@lru_cache(maxsize=4)
def _lanes_by_tls(scenario: str) -> dict[str, frozenset[str]]:
    """Inbound lanes controlled by each signal, for the per-junction metrics."""
    return {
        tls_id: frozenset(entry["lane"] for entry in entries)
        for tls_id, entries in signalLanePositions(scenario).items()
    }


# Weather the live run can be set to. Rain is part of the run, not just a map
# overlay: it is applied to the network's vehicle types, so the queue and speed
# numbers the dashboard publishes move with it.
WEATHER_EFFECTS: dict[str, dict[str, float | None]] = {
    # SUMO models rain through driver behaviour: a lower desired speed and a
    # longer headway between vehicles.
    "clear": {"speed_factor": 1.0, "tau": None},
    "rain": {"speed_factor": 0.75, "tau": 1.6},
}


class SimulationSession:
    """One live run at a time, on a background thread, mirroring ``run_episode``'s loop."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        # Each run owns its stop event: a retired run must never stop its successor.
        self._run_stop = threading.Event()
        self.pause_event = threading.Event()
        self.pending_steps = 0
        self._run_seq = 0
        self._pending_signals: deque[dict[str, Any]] = deque(maxlen=20)
        # Operator incidents are staged on the run thread (the only TraCI caller).
        self._pending_incidents: deque[dict[str, Any]] = deque(maxlen=5)
        # A clear request is applied by the run thread so it owns the TraCI call.
        self._pending_clear_incident = False
        # The crashed vehicle, held at 0 m/s for every step of the run.
        self._crash_hold: str | None = None
        # Whether the current run was launched with SUMO's own GUI attached. A GUI run
        # cannot use libsumo (it has no display), so it always goes through TraCI.
        self._gui = False
        self._junction_history: dict[str, deque[dict[str, Any]]] = {}
        self.state: dict[str, Any] = {
            "runId": None,
            "status": "idle",
            "scenario": None,
            "simulationTime": 0,
            "clock": "00:00:00",
            "speed": 1,
            "weather": "clear",
            "demandLevel": DEFAULT_DEMAND_LEVEL,
            "method": None,
            "vehicles": [],
            "pedestrians": [],
            "signals": [],
            "metrics": {},
            "events": [],
            "policy": None,
            "incident": None,
        }
        self._events: list[dict[str, Any]] = []
        self._event_keys: set[str] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=900)
        self._phase_state: dict[str, str] = {}
        self._phase_changes = 0
        self._controller_calls = 0
        self._last_decision_ms: float | None = None
        self._last_frame_wall = 0.0
        self._arrived_total = 0
        self._departed_total = 0
        # Completed live windows, so the published clock never jumps back to 0.
        self._time_offset = 0
        self._arrival_log: deque[tuple[int, int]] = deque(maxlen=600)
        self._event_seq = 0
        # Rain rescales the vehicle types; the base values are captured once so
        # clearing the rain restores the network's own calibration.
        self._weather = "clear"
        self._weather_base: dict[str, tuple[float, float]] = {}
        # Each vehicle's dry-road speed factor. SUMO copies speedFactor into a vehicle
        # when it is inserted, so the type alone cannot slow the traffic already driving.
        self._vehicle_speed_base: dict[str, float] = {}
        # The factor the population currently carries: a type or vehicle first seen while
        # it rains must still record its dry-road value as the base, not a rained-on one.
        self._weather_speed_factor = 1.0
        # The operator's demand dial. The run thread reads it when it builds each
        # cycle's episode, so a change applies to the next window without a restart.
        self._demand_level = DEFAULT_DEMAND_LEVEL
        # The run thread owns this link; set_weather only reads it to apply a
        # change mid-run, and never closes it.
        self._conn: Any | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.state)

    # --- controls -------------------------------------------------------------------

    def gui_status(self) -> dict[str, Any]:
        """Whether ``sumo-gui`` can be launched, and whether this run already has it.

        Checked on demand rather than cached: a SUMO install can appear (or be blocked
        by an application-control policy) between runs, and a stale answer would either
        hide a working button or offer one that cannot start.
        """
        from cotraffic.utils.sumo import SumoNotFoundError, binary

        with self.lock:
            attached = bool(self._gui)
            status = str(self.state.get("status") or "idle")
            scenario = self.state.get("scenario")
        try:
            path = binary("sumo-gui")
            available = True
            error = None
        except SumoNotFoundError as exc:
            path = None
            available = False
            error = str(exc)
        except Exception as exc:  # a broken install must not 500 the dashboard
            path = None
            available = False
            error = str(exc)
        return {
            "available": available,
            "path": path,
            "attached": attached,
            "status": status,
            "scenario": scenario,
            # A GUI run cannot use libsumo, so the dashboard can warn that it is slower.
            "backend": "traci" if attached else "libsumo",
        }

    def start(
        self,
        scenario: str,
        speed: float = 1,
        method_override: str | None = None,
        checkpoint_override: str | None = None,
        weather: str = "clear",
        demand_level: str | None = None,
        gui: bool = False,
    ) -> dict[str, Any]:
        if scenario not in SCENARIOS:
            raise ValueError(f"{scenario} is not a live scenario")
        if weather not in WEATHER_EFFECTS:
            raise ValueError(f"unknown weather {weather}")
        if demand_level is not None and demand_level not in DEMAND_LEVELS:
            raise ValueError(f"unknown demand level {demand_level}")
        network = SCENARIOS[scenario]
        # Each scenario runs the controller pinned to its own network: starting the 2x2
        # grid must not inherit the controller chosen for the 3x3 grid.
        method = policy.method_for(network)
        # Weights chosen by the UI travel through the policy layer, so a run can never
        # load a checkpoint that PUT /api/policy would have refused.
        if checkpoint_override and not method_override:
            raise ValueError("choosing weights also needs the controller method")
        if method_override is not None or checkpoint_override is not None:
            policy.update(method_override or method, network, checkpoint_override or "auto")
            method = policy.method_for(network)
        active = policy.scenario(network)
        # The checkpoint must match the network that actually runs, not the one the settings
        # page was last pointed at: a grid3x3 policy on the 2x2 grid would mis-shape the
        # observations the trained controller expects.
        ready, reason = policy.availability(method, network)
        if not ready:
            raise ValueError(reason or f"{method} is not available")
        checkpoint = policy.checkpoint_path(method, network)
        # Retire the current run without closing its TraCI link: the launcher below
        # waits for it to exit first, so two SUMO sessions never overlap. Overlapping
        # them closed the incoming run's connection and emptied the map.
        self._run_stop.set()
        stop_event = threading.Event()
        self._run_stop = stop_event
        self._reset_telemetry()
        # The weather belongs to the run: a restart keeps it, and the run thread
        # reads it on every decision, so a change applies without a restart.
        self._weather = weather
        self._weather_base.clear()
        self._vehicle_speed_base.clear()
        self._weather_speed_factor = 1.0
        # A GUI run is a different SUMO process, so it is decided at launch: attaching
        # the viewer to a run already in flight is not possible, and the caller restarts
        # to get one.
        self._gui = bool(gui)
        # A restart keeps the dial unless the caller names a level, so restarting a
        # run does not silently put the traffic back to its default.
        if demand_level is not None:
            self._demand_level = demand_level
        self.pause_event.clear()
        self._run_seq += 1
        run_id = f"live-{scenario}-{self._run_seq}"
        with self.lock:
            self.state.update(
                {
                    "runId": run_id,
                    "status": "starting",
                    "scenario": scenario,
                    "network": network,
                    "simulationTime": 0,
                    "speed": speed,
                    "weather": weather,
                    "demandLevel": self._demand_level,
                    "gui": self._gui,
                    "method": method,
                    "vehicles": [],
                    "pedestrians": [],
                    "signals": [],
                    "metrics": {},
                    "error": None,
                    "events": [],
                    "incident": None,
                    "policy": {
                        "method": method,
                        "label": policy.LABELS.get(method, method),
                        "network": network,
                        "checkpoint": str(checkpoint) if checkpoint else None,
                        "checkpointSource": active.get("checkpointSource"),
                    },
                }
            )
        self._events = []
        self._event_keys = set()
        self._event_seq = 0
        previous = self.thread
        self.thread = threading.Thread(
            target=self._run_after,
            args=(previous, scenario, method, checkpoint, stop_event),
            daemon=True,
        )
        self.thread.start()
        return self.snapshot()

    def pause(self) -> dict[str, Any]:
        self.pause_event.set()
        with self.lock:
            if self.state["status"] == "running":
                self.state["status"] = "paused"
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        self.pause_event.clear()
        with self.lock:
            if self.state["status"] == "paused":
                self.state["status"] = "running"
        return self.snapshot()

    def step(self, count: int = 1) -> dict[str, Any]:
        """Advance a paused run by N decisions, for stepping through a scenario."""
        with self.lock:
            if self.state["status"] not in ("paused", "running"):
                return self.snapshot()
            if self.state["status"] == "running":
                self.pause_event.set()
                self.state["status"] = "paused"
            self.pending_steps = min(1200, self.pending_steps + max(1, int(count)))
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        self._run_stop.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self._conn = None
        self._close_traci()
        with self.lock:
            self.state.update({"status": "idle", "vehicles": [], "pedestrians": [], "signals": []})
        return self.snapshot()

    def set_speed(self, speed: float) -> dict[str, Any]:
        with self.lock:
            self.state["speed"] = max(0.25, min(float(speed), 20))
        return self.snapshot()

    def set_weather(self, weather: str) -> dict[str, Any]:
        """Turn rain on or off for the running run.

        The change is published immediately and applied to the vehicle types on
        the next decision, so the map and the metrics agree. With no run started
        yet the condition is still remembered and carried into the next start.
        """
        if weather not in WEATHER_EFFECTS:
            raise ValueError(f"unknown weather {weather}")
        self._weather = weather
        conn = self._conn
        if conn is not None:
            self._apply_weather(conn)
        with self.lock:
            self.state["weather"] = weather
        return self.snapshot()

    def set_demand_level(self, level: str) -> dict[str, Any]:
        """Set how heavy the live traffic is, for the running run.

        The level is published immediately and picked up when the run thread builds
        the next cycle's episode, so the map keeps running: the current window finishes
        and the next one arrives at the new rate. With no run started yet the level is
        still remembered and carried into the next start.
        """
        if level not in DEMAND_LEVELS:
            raise ValueError(f"unknown demand level {level}")
        self._demand_level = level
        with self.lock:
            self.state["demandLevel"] = level
        return self.snapshot()

    def inject_incident(self, message: str | None = None) -> dict[str, Any]:
        """Publish an operator-reported collision on the running corridor.

        The event enters the same feed the derived incidents use, so the Live Map's
        queue card and the Events tab react immediately; the queue numbers behind it
        stay the run's measured ones.
        """
        with self.lock:
            if self.state.get("status") not in ("running", "paused"):
                raise ValueError("start a live run before injecting an incident")
            sim_time = int(self.state.get("simulationTime") or 0)
            clock = str(self.state.get("clock") or "00:00:00")
        self._append_event(
            "incident",
            "critical",
            sim_time,
            clock,
            message or "Operator-reported collision on the corridor",
            {"source": "operator"},
        )
        with self.lock:
            # The physical crash (a stopped car plus a dispatched ambulance) is staged
            # on the run thread; this only records the request and shows the report.
            self._pending_incidents.append({"message": message})
            self.state["events"] = list(self._events)
        return self.snapshot()

    def clear_incident(self) -> dict[str, Any]:
        """Release the stopped vehicle and retire the current incident.

        The run thread applies the change on its next decision, so the crash is not
        unpinned from a TraCI call made on the HTTP worker thread.
        """
        with self.lock:
            if self.state.get("status") not in ("running", "paused"):
                raise ValueError("start a live run before clearing an incident")
            if not (self.state.get("incident") or {}).get("active"):
                raise ValueError("no active incident to clear")
            self._pending_clear_incident = True
        return self.snapshot()

    def queue_signal(self, junction: str, green: float) -> dict[str, Any]:
        """Stage a green-time change for the running corridor's current phase.

        ``green`` is the duration in seconds for the phase the junction is in now, which
        is what the dashboard's Signal editor shows. The run loop applies it on its next
        tick (TraCI is only touched from that thread) and publishes a ``signalChange``
        event so the change is visible in the feed.
        """
        with self.lock:
            if self.state.get("status") not in ("running", "paused"):
                raise NotRunning("start a live run before changing a signal")
            known = {signal.get("id") for signal in self.state.get("signals") or []}
            if junction not in known:
                raise ValueError(f"unknown junction {junction!r}")
            if not MIN_GREEN_S <= float(green) <= MAX_GREEN_S:
                raise ValueError(
                    f"green must be between {MIN_GREEN_S:.0f}s and {MAX_GREEN_S:.0f}s"
                )
            self._pending_signals.append({"tls": junction, "green": float(green)})
        return self.snapshot()

    def _apply_pending_signals(self, conn: Any) -> None:
        """Drain queued signal changes on the run thread (the only TraCI caller)."""
        with self.lock:
            pending = list(self._pending_signals)
            self._pending_signals.clear()
        for request in pending:
            tls, green = request["tls"], request["green"]
            now = self._time_offset + int(conn.simulation.getTime())
            clock_label = str(self.state.get("clock") or "")
            try:
                conn.trafficlight.setPhaseDuration(tls, green)
            except Exception as error:  # SUMO refused: report it, keep the run alive
                self._append_event(
                    "modelError",
                    "warning",
                    now,
                    clock_label,
                    f"SUMO refused the signal change on {tls}: {error}",
                    {"tls": tls, "green": green, "source": "operator"},
                )
                continue
            self._append_event(
                "signalChange",
                "info",
                now,
                clock_label,
                f"Operator set {tls} green to {green:.0f}s",
                {"tls": tls, "green": green, "source": "operator"},
            )

    def _apply_pending_incidents(self, env: CoTrafficEnv, scenario: str) -> None:
        """Stage operator reports on the run thread (the only TraCI caller)."""
        conn = env.conn
        self._apply_pending_incident_clear(conn)
        with self.lock:
            pending = list(self._pending_incidents)
            self._pending_incidents.clear()
        for request in pending:
            try:
                self._stage_incident(conn, scenario, request.get("message"))
            except Exception as error:
                now = self._time_offset + int(conn.simulation.getTime())
                clock = str(self.state.get("clock") or "00:00:00")
                self._append_event(
                    "modelError",
                    "warning",
                    now,
                    clock,
                    f"Incident could not be staged: {error}",
                    {"source": "operator"},
                )
        with self.lock:
            self.state["events"] = list(self._events)

    def _apply_pending_incident_clear(self, conn: Any) -> None:
        """Release the crash and retire the incident on the run thread."""
        with self.lock:
            pending = self._pending_clear_incident
            self._pending_clear_incident = False
            incident = dict(self.state.get("incident") or {})
        if not pending:
            return
        self._crash_hold = None
        now = self._time_offset + int(conn.simulation.getTime())
        clock = f"{now // 3600:02d}:{now % 3600 // 60:02d}:{now % 60:02d}"
        if not incident:
            return
        response = list(incident.get("response") or [])
        response.append(
            self._response_action("cleared", "Safety", "Incident cleared", now, clock, "done")
        )
        with self.lock:
            self.state["incident"] = {**incident, "active": False, "cleared": True, "response": response}
        self._append_event(
            "incidentCleared",
            "info",
            now,
            clock,
            "Incident cleared — the corridor is flowing again",
            {"vehicleId": incident.get("vehicleId")},
        )
        with self.lock:
            self.state["events"] = list(self._events)

    def _stage_incident(self, conn: Any, scenario: str, message: str | None = None) -> None:
        """Stop a car, reroute traffic around it and send an ambulance to it."""
        now = self._time_offset + int(conn.simulation.getTime())
        clock = str(self.state.get("clock") or "00:00:00")
        crash = self._pick_crash_vehicle(conn)
        if crash is None:
            self._append_event(
                "incident",
                "warning",
                now,
                clock,
                "No ordinary car to stop — the corridor is empty.",
                {"source": "operator"},
            )
            return
        edge = str(conn.vehicle.getRoadID(crash) or "")
        lane = str(conn.vehicle.getLaneID(crash) or "")
        x, y = conn.vehicle.getPosition(crash)
        lng, lat = _project(scenario, x, y)
        try:
            street = str(conn.edge.getStreetName(edge) or "")
        except Exception:
            street = ""
        # SUMO rejects a zero max speed, so the crash is pinned at 0 m/s on every
        # simulated step instead (see _hold_crash_stopped).
        self._crash_hold = crash
        try:
            conn.vehicle.setSpeed(crash, 0.0)
        except Exception:
            pass
        blocked = self._lane_polyline(conn, scenario, lane) or self._edge_polyline(
            conn, scenario, edge
        )
        rerouted, diversion = self._reroute_around(conn, scenario, edge, crash)
        ambulance = self._dispatch_ambulance(conn, scenario, edge, x, y)
        ev_id = ambulance.get("id") if ambulance else None
        ev_route = list(ambulance.get("route") or []) if ambulance else []
        ev_edges = list(ambulance.get("edges") or []) if ambulance else []
        distance = self._ambulance_distance(conn, ev_id, x, y) if ev_id else None
        eta = None if distance is None else round(distance / 8.0)
        reroute_label = (
            f"Rerouted {len(rerouted)} vehicles around the incident"
            if rerouted
            else "No alternate route — holding traffic"
        )
        response = [
            self._response_action(
                "detection", "Detection", "Collision detected", now, clock, "done",
                {"vehicleId": crash, "edge": edge, "street": street},
            ),
            self._response_action(
                "blocked", "Safety", f"Lane blocked on {street or edge}", now, clock, "done",
                {"lane": lane},
            ),
            self._response_action(
                "reroute", "Routing", reroute_label, now, clock, "done",
                {"count": len(rerouted), "vehicles": rerouted[:8]},
            ),
        ]
        if ev_id:
            response.append(
                self._response_action(
                    "dispatch", "Dispatch", f"Ambulance {ev_id} dispatched", now, clock,
                    "active", {"etaS": eta, "distanceM": distance},
                )
            )
        else:
            response.append(
                self._response_action(
                    "dispatch", "Dispatch", "No ambulance route available", now, clock, "done"
                )
            )
        incident = {
            "vehicleId": crash,
            "edge": edge,
            "lane": lane,
            "street": street,
            "lng": lng,
            "lat": lat,
            "x": round(float(x), 2),
            "y": round(float(y), 2),
            "since": now,
            "ambulance": ev_id,
            "ambulanceRoute": ev_route,
            "ambulanceRouteEdges": ev_edges,
            "ambulanceDistanceM": distance,
            "ambulanceEtaS": eta,
            # The approach distance at dispatch, so the panel's progress bar is the
            # share actually covered instead of a bar that fills on a timer.
            "ambulanceStartM": distance if distance is not None else _polyline_meters(ev_route),
            "blocked": blocked,
            "diversion": diversion,
            "rerouted": rerouted,
            "reroutedCount": len(rerouted),
            "response": response,
            # The map draws the crash as a twitching body, so the pose it twitches
            # around is pinned here: the vehicle is held at 0 m/s and its heading is
            # frozen, otherwise SUMO's own step would rotate it under the animation.
            "angle": round(float(conn.vehicle.getAngle(crash) or 0.0), 2),
            "length": _vehicle_length(conn, crash),
            "ambulancePhase": "dispatched" if ev_id else "unavailable",
            "controller": self._controller_incident_response(conn, scenario, edge, crash),
            "active": True,
            "cleared": False,
        }
        if message:
            incident["message"] = message
        with self.lock:
            self.state["incident"] = incident
        self._append_event(
            "incident", "critical", now, clock,
            f"Collision: {crash} stopped on {street or edge}",
            {"source": "operator", "vehicleId": crash, "lng": lng, "lat": lat,
             "edge": edge, "street": street},
        )
        if rerouted:
            self._append_event(
                "reroute", "info", now, clock,
                f"Rerouted {len(rerouted)} vehicles around {street or edge}",
                {"count": len(rerouted), "vehicles": rerouted[:8], "diversion": diversion},
            )
        if ev_id:
            self._append_event(
                "evDispatch", "info", now, clock,
                f"Ambulance {ev_id} dispatched to {street or edge}",
                {"vehicleId": ev_id, "target": crash, "lng": lng, "lat": lat,
                 "route": ev_route, "etaS": eta},
            )

    def _reroute_around(
        self, conn: Any, scenario: str, edge: str, crash: str
    ) -> tuple[list[str], list[list[float]]]:
        """Reroute vehicles whose remaining route crosses the blocked edge."""
        candidates: list[str] = []
        for vehicle_id in conn.vehicle.getIDList():
            if vehicle_id == crash:
                continue
            try:
                if conn.vehicle.getVehicleClass(vehicle_id) in ("emergency", "bus"):
                    continue
                route = list(conn.vehicle.getRoute(vehicle_id))
                index = max(0, int(conn.vehicle.getRouteIndex(vehicle_id)))
                # A car already on the blocked edge cannot avoid it; only reroute
                # traffic that would still enter it.
                if edge in route[index + 1:]:
                    candidates.append(vehicle_id)
            except Exception:
                continue
        candidates = candidates[:40]
        if not candidates:
            return [], []
        rerouted: list[str] = []
        routes: list[tuple[str, list[str]]] = []
        try:
            # A very high effort makes the blocked edge unattractive to SUMO's own
            # routing, which is used as a fallback when the graph detour fails.
            conn.edge.setEffort(edge, 1_000_000.0)
            for vehicle_id in candidates:
                try:
                    before = list(conn.vehicle.getRoute(vehicle_id))
                    index = max(0, int(conn.vehicle.getRouteIndex(vehicle_id)))
                    current = str(conn.vehicle.getRoadID(vehicle_id) or "")
                    lane = str(conn.vehicle.getLaneID(vehicle_id) or "")
                except Exception:
                    continue
                # A body on a junction-internal edge cannot have its route replaced.
                if not current or current.startswith(":"):
                    continue
                destination = before[-1] if before else None
                after: list[str] = []
                remaining: list[str] = []
                alternate = self._alternate_route(conn, current, destination, edge)
                if (
                    alternate
                    and self._route_connected(conn, alternate)
                    and self._lane_can_reach(conn, lane, alternate[1])
                ):
                    try:
                        conn.vehicle.setRoute(vehicle_id, alternate)
                        after = list(conn.vehicle.getRoute(vehicle_id))
                        remaining = after
                    except Exception:
                        after = []
                if not after or edge in after:
                    try:
                        conn.vehicle.rerouteEffort(vehicle_id)
                    except Exception:
                        try:
                            conn.vehicle.rerouteTraveltime(vehicle_id)
                        except Exception:
                            continue
                    try:
                        after = list(conn.vehicle.getRoute(vehicle_id))
                        index = max(0, int(conn.vehicle.getRouteIndex(vehicle_id)))
                        remaining = after[index:]
                    except Exception:
                        continue
                if before == after or edge in remaining:
                    continue
                rerouted.append(vehicle_id)
                if len(routes) < 5:
                    routes.append((vehicle_id, remaining))
        finally:
            try:
                conn.edge.setEffort(edge, -1.0)
            except Exception:
                pass
        diversion = self._route_polyline(conn, scenario, routes[0][1]) if routes else []
        return rerouted, diversion

    def _alternate_route(
        self,
        conn: Any,
        current_edge: str | None,
        destination_edge: str | None,
        blocked_edge: str,
    ) -> list[str] | None:
        """Shortest connected path around the blocked edge, or ``None``."""
        if not current_edge or not destination_edge:
            return None
        if current_edge == blocked_edge or destination_edge == blocked_edge:
            return None
        if current_edge == destination_edge:
            return None
        try:
            start = conn.edge.getToJunction(current_edge)
            goal = conn.edge.getFromJunction(destination_edge)
        except Exception:
            return None
        if not start or not goal:
            return None
        if start == goal:
            return [current_edge, destination_edge]
        heap: list[tuple[float, str]] = [(0.0, start)]
        distances: dict[str, float] = {start: 0.0}
        previous: dict[str, tuple[str, str]] = {}
        visited: set[str] = set()
        while heap:
            cost, junction = heapq.heappop(heap)
            if junction in visited:
                continue
            visited.add(junction)
            if junction == goal:
                break
            try:
                outgoing = conn.junction.getOutgoingEdges(junction)
            except Exception:
                continue
            for next_edge in outgoing:
                if not next_edge or next_edge.startswith(":") or next_edge == blocked_edge:
                    continue
                try:
                    next_junction = conn.edge.getToJunction(next_edge)
                except Exception:
                    continue
                if not next_junction:
                    continue
                step = self._edge_cost(conn, next_edge) + 1.0
                new_cost = cost + step
                if new_cost >= distances.get(next_junction, float("inf")):
                    continue
                distances[next_junction] = new_cost
                previous[next_junction] = (junction, next_edge)
                heapq.heappush(heap, (new_cost, next_junction))
        if goal not in distances:
            return None
        reversed_edges: list[str] = []
        node = goal
        while node != start:
            parent, edge = previous.get(node, (None, None))
            if not parent or not edge:
                return None
            reversed_edges.append(edge)
            node = parent
        reversed_edges.reverse()
        return [current_edge, *reversed_edges, destination_edge]

    @staticmethod
    def _edge_cost(conn: Any, edge: str) -> float:
        try:
            length = float(conn.lane.getLength(f"{edge}_0"))
            speed = float(conn.lane.getMaxSpeed(f"{edge}_0"))
            return length / max(speed, 1.0)
        except Exception:
            return 30.0

    @staticmethod
    def _route_connected(conn: Any, edges: list[str]) -> bool:
        for current, following in pairwise(edges):
            try:
                if conn.edge.getToJunction(current) != conn.edge.getFromJunction(following):
                    return False
            except Exception:
                return False
        return True

    @staticmethod
    def _lane_can_reach(conn: Any, lane: str, edge: str) -> bool:
        """Whether the vehicle's current lane has a connection to the given edge."""
        if not lane or not edge:
            return False
        try:
            links = conn.lane.getLinks(lane)
        except Exception:
            return False
        for link in links:
            successor = str(link[0] or "") if link else ""
            if not successor:
                continue
            if successor.startswith(":"):
                try:
                    inner_links = conn.lane.getLinks(successor)
                except Exception:
                    continue
                for inner in inner_links:
                    inner_lane = str(inner[0] or "") if inner else ""
                    if inner_lane and not inner_lane.startswith(":") and inner_lane.rsplit("_", 1)[0] == edge:
                        return True
            elif successor.rsplit("_", 1)[0] == edge:
                return True
        return False

    def _dispatch_ambulance(
        self, conn: Any, scenario: str, target_edge: str, x: float, y: float
    ) -> dict[str, Any] | None:
        """Route an ambulance to the crash from a nearby edge; ``None`` if none is."""
        origins = self._ambulance_origins(conn, target_edge)
        best = None
        for origin in origins[:80]:
            try:
                route = conn.simulation.findRoute(origin, target_edge)
            except Exception:
                continue
            if route is None or len(route.edges) < 2:
                continue
            if best is None or len(route.edges) < len(best.edges):
                best = route
        if best is None:
            return None
        self._event_seq += 1
        route_id = f"ev_route_{self._event_seq}"
        vehicle_id = f"ev_dispatch_{self._event_seq}"
        edges = list(best.edges)
        try:
            conn.route.add(route_id, edges)
            # The ``emergency`` type is in the run's vtypes, so SUMO already knows it.
            conn.vehicle.add(vehicle_id, route_id, typeID="emergency")
        except Exception:
            return None
        return {
            "id": vehicle_id,
            "edges": edges,
            "route": self._route_polyline(conn, scenario, edges),
        }

    def _ambulance_origins(self, conn: Any, target_edge: str) -> list[str]:
        """Prefer edges around the crash so the dispatched ambulance is close."""
        origins: list[str] = []
        try:
            from_junction = conn.edge.getFromJunction(target_edge)
            to_junction = conn.edge.getToJunction(target_edge)
        except Exception:
            from_junction = to_junction = None
        for junction in (from_junction, to_junction):
            if not junction:
                continue
            try:
                origins.extend(conn.junction.getIncomingEdges(junction))
                origins.extend(conn.junction.getOutgoingEdges(junction))
            except Exception:
                continue
        clean = [
            edge for edge in dict.fromkeys(origins)
            if edge and not edge.startswith(":") and edge != target_edge
        ]
        if clean:
            return clean
        edges = [edge for edge in conn.edge.getIDList() if not edge.startswith(":")]
        if not edges:
            return []
        rng = random.Random(self._run_seq * 1000 + self._event_seq)
        return rng.sample(edges, min(120, len(edges)))

    def _edge_polyline(self, conn: Any, scenario: str, edge: str) -> list[list[float]]:
        """Projected shape of an edge, taken from its first lane."""
        if not edge:
            return []
        try:
            lane_count = int(conn.edge.getLaneNumber(edge) or 1)
        except Exception:
            lane_count = 1
        shape = []
        for index in range(max(1, lane_count)):
            try:
                candidate = conn.lane.getShape(f"{edge}_{index}")
            except Exception:
                continue
            if candidate and len(candidate) >= 2:
                shape = candidate
                break
        if not shape:
            return []
        return _thin([_project(scenario, px, py) for px, py in shape])

    def _lane_polyline(self, conn: Any, scenario: str, lane: str) -> list[list[float]]:
        """Projected shape of one lane, used to draw the blocked stretch."""
        if not lane:
            return []
        try:
            shape = conn.lane.getShape(lane)
        except Exception:
            shape = []
        if not shape:
            return []
        return _thin([_project(scenario, px, py) for px, py in shape])

    def _route_polyline(
        self, conn: Any, scenario: str, edges: list[str]
    ) -> list[list[float]]:
        points: list[list[float]] = []
        for edge in edges:
            coords = self._edge_polyline(conn, scenario, edge)
            if not coords:
                continue
            if points and coords and points[-1] == coords[0]:
                coords = coords[1:]
            points.extend(coords)
        return _thin(points)

    @staticmethod
    def _ambulance_distance(
        conn: Any, vehicle_id: str | None, x: float | None, y: float | None
    ) -> float | None:
        if not vehicle_id or x is None or y is None:
            return None
        try:
            value = float(conn.vehicle.getDrivingDistance2D(vehicle_id, x, y))
        except Exception:
            return None
        if value <= 0 or value >= 1_000_000:
            return None
        return round(value, 1)

    @staticmethod
    def _response_action(
        key: str,
        agent: str,
        label: str,
        at: int,
        clock: str,
        status: str = "done",
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "agent": agent,
            "label": label,
            "at": at,
            "clock": clock,
            "status": status,
            "detail": detail or {},
        }

    def _pick_crash_vehicle(self, conn: Any) -> str | None:
        """The slowest ordinary car on a busy road: the one that reads as the crash.

        Roads with traffic approaching them are preferred, because those vehicles
        are the ones the incident can visibly reroute. A road with a usable bypass
        wins over a busier chokepoint, so the map can show traffic actually diverting.
        """
        vehicle_ids = conn.vehicle.getIDList()
        info: dict[str, tuple[list[str], int, str, str, float]] = {}
        approaching: dict[str, int] = {}
        for vehicle_id in vehicle_ids:
            try:
                if conn.vehicle.getVehicleClass(vehicle_id) in ("emergency", "bus"):
                    continue
                route = list(conn.vehicle.getRoute(vehicle_id))
                index = max(0, int(conn.vehicle.getRouteIndex(vehicle_id)))
                road = str(conn.vehicle.getRoadID(vehicle_id) or "")
                if not road or road.startswith(":"):
                    continue
                lane = str(conn.vehicle.getLaneID(vehicle_id) or "")
                speed = float(conn.vehicle.getSpeed(vehicle_id))
                info[vehicle_id] = (route, index, road, lane, speed)
                for edge in set(route[index + 1:]):
                    approaching[edge] = approaching.get(edge, 0) + 1
            except Exception:
                continue
        if not info:
            return None
        roads: dict[str, list[str]] = {}
        for vehicle_id, (_route, _index, road, _lane, _speed) in info.items():
            roads.setdefault(road, []).append(vehicle_id)
        ranked = sorted(roads, key=lambda road: -approaching.get(road, 0))
        for road in ranked[:8]:
            if self._has_bypass(conn, road, info, set(roads[road])):
                return min(roads[road], key=lambda vehicle_id: info[vehicle_id][4])
        return min(roads[ranked[0]], key=lambda vehicle_id: info[vehicle_id][4])

    def _has_bypass(
        self,
        conn: Any,
        road: str,
        info: dict[str, tuple[list[str], int, str, str, float]],
        same_road: set[str],
    ) -> bool:
        """Whether at least one approaching vehicle can avoid the given road."""
        checked = 0
        for vehicle_id, (route, index, current, lane, _speed) in info.items():
            if vehicle_id in same_road or road not in route[index + 1:]:
                continue
            checked += 1
            if checked > 8:
                break
            alternate = self._alternate_route(conn, current, route[-1], road)
            if (
                alternate
                and self._route_connected(conn, alternate)
                and self._lane_can_reach(conn, lane, alternate[1])
            ):
                return True
        return False

    def _refresh_incident(self, conn: Any) -> None:
        """Keep the incident's ambulance ETA current and retire it when it clears."""
        with self.lock:
            incident = dict(self.state.get("incident") or {})
        if not incident or not incident.get("active"):
            return
        now = self._time_offset + int(conn.simulation.getTime())
        clock = f"{now // 3600:02d}:{now % 3600 // 60:02d}:{now % 60:02d}"
        try:
            present = incident.get("vehicleId") in conn.vehicle.getIDList()
        except Exception:
            return
        if not present:
            self._crash_hold = None
            response = list(incident.get("response") or [])
            response.append(
                self._response_action("cleared", "Safety", "Incident cleared", now, clock, "done")
            )
            with self.lock:
                self.state["incident"] = {
                    **incident, "active": False, "cleared": True, "response": response
                }
            self._append_event(
                "incidentCleared",
                "info",
                now,
                clock,
                "Incident cleared — the corridor is flowing again",
                {"vehicleId": incident.get("vehicleId")},
            )
            with self.lock:
                self.state["events"] = list(self._events)
            return
        ambulance = incident.get("ambulance")
        if not ambulance:
            return
        try:
            present_ev = ambulance in conn.vehicle.getIDList()
        except Exception:
            present_ev = False
        updated = dict(incident)
        # The ambulance leaves the network once its route ends, so a missing body after
        # dispatch means it finished the run — not that the dispatch failed. The old
        # guard only fired from "dispatched", so a unit that had already been published
        # as "enroute" stayed enroute forever and the panel froze on a stale ETA.
        if not present_ev:
            if incident.get("ambulancePhase") in ("dispatched", "enroute"):
                updated["ambulancePhase"] = "arrived"
                updated["ambulanceDistanceM"] = 0
                updated["ambulanceEtaS"] = 0
                updated["onScene"] = True
                response = list(incident.get("response") or [])
                response = [
                    {**action, "status": "done"} if action.get("key") == "dispatch" else action
                    for action in response
                ]
                if not any(action.get("key") == "onScene" for action in response):
                    response.append(
                        self._response_action(
                            "onScene", "Dispatch", "Ambulance arrived on scene", now, clock, "done"
                        )
                    )
                updated["response"] = response
                with self.lock:
                    self.state["incident"] = updated
            return
        distance = self._ambulance_distance(conn, ambulance, incident.get("x"), incident.get("y"))
        if distance is not None:
            updated["ambulanceDistanceM"] = distance
            updated["ambulanceEtaS"] = round(distance / 8.0)
            updated["ambulancePhase"] = "onScene" if distance <= 25 else "enroute"
        response = list(incident.get("response") or [])
        if distance is not None and distance <= 25 and not incident.get("onScene"):
            updated["onScene"] = True
            response = [
                {**action, "status": "done"} if action.get("key") == "dispatch" else action
                for action in response
            ]
            response.append(
                self._response_action(
                    "onScene", "Dispatch", "Ambulance on scene", now, clock, "done",
                    {"distanceM": distance},
                )
            )
            self._append_event(
                "evOnScene",
                "info",
                now,
                clock,
                f"Ambulance {ambulance} reached the incident",
                {"vehicleId": ambulance},
            )
            with self.lock:
                self.state["events"] = list(self._events)
        updated["response"] = response
        # The controller's own account of the incident is re-read every refresh: the
        # policy may have been switched mid-response, and a stale label would credit
        # the wrong controller for the preemption.
        updated["controller"] = self._controller_incident_response(
            conn, "", incident.get("edge") or "", incident.get("vehicleId") or ""
        )
        with self.lock:
            self.state["incident"] = updated

    def _hold_crash_stopped(self, conn: Any) -> None:
        """Keep the crashed vehicle at a standstill: SUMO would otherwise drive it on."""
        crash = self._crash_hold
        if not crash:
            return
        try:
            if crash in conn.vehicle.getIDList():
                conn.vehicle.setSpeed(crash, 0.0)
            else:
                self._crash_hold = None
        except Exception:
            self._crash_hold = None

    def _controller_incident_response(
        self, conn: Any, scenario: str, edge: str, crash: str
    ) -> dict[str, Any]:
        """What the active control policy did about the crash, in its own words.

        The reroute and the ambulance are staged by this session; the signals are the
        controller's. Reporting the policy's own preemption here is what makes the
        difference between policies visible during an incident instead of only in the
        aggregate metrics.
        """
        policy = self.state.get("policy") or {}
        label = str(policy.get("label") or policy.get("method") or "Controller")
        preempted: list[str] = []
        # A junction holding a long green while the ambulance is inbound is the
        # controller clearing the corridor; it is a measurement, not an inference.
        for signal in list(self.state.get("signals") or []):
            try:
                if float(signal.get("green") or 0) >= 30 and float(signal.get("duration") or 0) >= 30:
                    preempted.append(str(signal.get("id")))
            except Exception:
                continue
        return {
            "label": label,
            "method": policy.get("method"),
            "preempted": preempted[:6],
            "preemptedCount": len(preempted),
            "note": (
                f"{label} held {len(preempted)} junction(s) open for the response"
                if preempted
                else f"{label} is serving the corridor normally"
            ),
        }

    def junctions(self) -> dict[str, Any]:
        """Per-junction measured values plus their short time series."""
        with self.lock:
            current = {
                junction.get("id"): junction
                for junction in (self.state.get("metrics") or {}).get("junctions") or []
            }
            junctions: list[dict[str, Any]] = []
            for tls, history in self._junction_history.items():
                entry = dict(current.get(tls) or {"id": tls})
                if history:
                    latest = history[-1]
                    entry.update(
                        {
                            "t": latest["t"],
                            "queue": latest["queue"],
                            "pressure": latest["pressure"],
                            "avgSpeedKmh": latest["avgSpeedKmh"],
                        }
                    )
                entry["trend"] = list(history)
                junctions.append(entry)
            return {"runId": self.state.get("runId"), "junctions": junctions}

    def forecast(self, horizon_minutes: int = 15) -> dict[str, Any]:
        """Queue/throughput projection for the running corridor."""
        with self.lock:
            if self.state.get("status") not in ("running", "paused"):
                raise NotRunning("start a live run before forecasting")
            samples = list(self._history)
            run_id = self.state.get("runId")
        payload = project_forecast(samples, horizon_minutes=horizon_minutes)
        payload["runId"] = run_id
        return payload

    # --- run ------------------------------------------------------------------------

    @staticmethod
    def _close_traci() -> None:
        """Release the TraCI link if a run died before closing its environment."""
        try:
            import traci

            traci.close()
        except Exception:
            pass

    def _moving_objects(
        self, conn: Any, scenario: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Every vehicle and person the map draws, in network and geographic coordinates."""
        vehicles = []
        for vehicle_id in conn.vehicle.getIDList():
            x, y = conn.vehicle.getPosition(vehicle_id)
            longitude, latitude = _project(scenario, x, y)
            speed = conn.vehicle.getSpeed(vehicle_id)
            vehicles.append(
                {
                    "id": vehicle_id,
                    "x": x,
                    "y": y,
                    "lng": longitude,
                    "lat": latitude,
                    "angle": conn.vehicle.getAngle(vehicle_id),
                    "speed": speed,
                    "waiting": speed < 0.1,
                    "type": conn.vehicle.getTypeID(vehicle_id),
                    "lane": conn.vehicle.getLaneID(vehicle_id),
                    "waitingTime": conn.vehicle.getWaitingTime(vehicle_id),
                    "vehicleClass": conn.vehicle.getVehicleClass(vehicle_id),
                }
            )
        pedestrians = []
        for person_id in conn.person.getIDList():
            x, y = conn.person.getPosition(person_id)
            longitude, latitude = _project(scenario, x, y)
            try:
                speed = conn.person.getSpeed(person_id)
                angle = conn.person.getAngle(person_id)
            except Exception:
                speed = 0.0
                angle = 0.0
            pedestrians.append(
                {
                    "id": person_id,
                    "x": x,
                    "y": y,
                    "lng": longitude,
                    "lat": latitude,
                    "speed": speed,
                    "angle": angle,
                    "waiting": speed < 0.1,
                }
            )
        return vehicles, pedestrians

    def _signal_entries(self, conn: Any, sim_time: int) -> list[dict[str, Any]]:
        signals = []
        for tls_id in conn.trafficlight.getIDList():
            try:
                signals.append(
                    {
                        "id": tls_id,
                        "state": conn.trafficlight.getRedYellowGreenState(tls_id),
                        "phase": conn.trafficlight.getPhase(tls_id),
                        "duration": conn.trafficlight.getPhaseDuration(tls_id),
                        "nextSwitch": conn.trafficlight.getNextSwitch(tls_id),
                        # getPhaseDuration is the programme default (often 86400), so the
                        # panel gets the time actually left in this phase instead.
                        "green": _remaining_green(conn, tls_id, sim_time),
                    }
                )
            except Exception:
                continue
        return signals

    def _substep(
        self, env: CoTrafficEnv, scenario: str, stop_event: threading.Event
    ) -> None:
        """After every simulated step: refresh the map, then pace the wall clock.

        Pacing used to happen once per decision, so a 5 s decision was computed in one
        burst and the map jumped. Sleeping here spreads those steps over the same wall
        time, and the browser interpolates between them.
        """
        self._hold_crash_stopped(env.conn)
        self._publish_frame(env, scenario, stop_event)
        if self.pause_event.is_set() or stop_event.is_set():
            return
        steps = max(1.0, float(env.delta) / max(float(env.step_length), 1e-6))
        speed = max(float(self.state.get("speed", 1) or 1), 0.25)
        time.sleep(max(0.0, (1.0 / speed) / steps))

    def _owns_run(self, stop_event: threading.Event) -> bool:
        """Whether this thread still runs the session the dashboard is showing.

        A scenario switch sets the new run's scenario and runId, then waits for the old
        run to release SUMO. Until that old thread exits it was still publishing its own
        vehicles into the shared state, so the map read "Tunis" with San Francisco
        bodies (and inherited the retired run's clock offset): the vehicles vanished
        because they were drawn in the previous network's coordinates.
        """
        return self._run_stop is stop_event and not stop_event.is_set()

    def _publish_frame(
        self, env: CoTrafficEnv, scenario: str, stop_event: threading.Event
    ) -> None:
        """Publish one simulated sub-step: positions, not new metrics or events.

        The map needs the bodies between two decisions; the platform's metrics, events
        and trend stay on the decision cadence so their numbers keep their meaning.
        """
        if not self._owns_run(stop_event):
            return
        wall = time.monotonic()
        if wall - self._last_frame_wall < FRAME_MIN_WALL_S:
            return
        self._last_frame_wall = wall
        try:
            conn = env.conn
            raw_time = int(conn.simulation.getTime())
            sim_time = self._time_offset + raw_time
            vehicles, pedestrians = self._moving_objects(conn, scenario)
            signals = self._signal_entries(conn, raw_time)
        except Exception:  # a frame is a nicety; the run must never die for one
            return
        clock = f"{sim_time // 3600:02d}:{sim_time % 3600 // 60:02d}:{sim_time % 60:02d}"
        with self.lock:
            self.state.update(
                {
                    "simulationTime": sim_time,
                    "clock": clock,
                    "vehicles": vehicles,
                    "pedestrians": pedestrians,
                    "signals": signals,
                }
            )

    def _publish(
        self, env: CoTrafficEnv, scenario: str, stop_event: threading.Event
    ) -> None:
        # A retiring run must not overwrite the replacement's frames, metrics or events.
        if not self._owns_run(stop_event):
            return
        conn = env.conn
        self._refresh_incident(conn)
        raw_time = int(conn.simulation.getTime())
        sim_time = self._time_offset + raw_time
        vehicles, pedestrians = self._moving_objects(conn, scenario)
        signals = self._signal_entries(conn, raw_time)
        clock = f"{sim_time // 3600:02d}:{sim_time % 3600 // 60:02d}:{sim_time % 60:02d}"
        events = self._publish_events(vehicles, pedestrians, sim_time, clock, signals)
        with self.lock:
            self.state.update(
                {
                    "simulationTime": sim_time,
                    "trend": list(self._history)[-60:],
                    "clock": clock,
                    "events": events,
                    "vehicles": vehicles,
                    "pedestrians": pedestrians,
                    "signals": signals,
                    "metrics": {
                        "vehicles": len(vehicles),
                        "pedestrians": len(pedestrians),
                        "arrived": int(conn.simulation.getArrivedNumber()),
                        **self._metrics(env, scenario, vehicles, pedestrians, signals, sim_time, clock),
                        **self._controller_metrics(),
                    },
                }
            )

    def _reset_telemetry(self) -> None:
        self._history.clear()
        self._junction_history.clear()
        self._pending_signals.clear()
        self._pending_incidents.clear()
        self._pending_clear_incident = False
        self._crash_hold = None
        self._phase_state = {}
        self._phase_changes = 0
        self._controller_calls = 0
        self._last_decision_ms = None
        self._last_frame_wall = 0.0
        self._time_offset = 0
        self._arrived_total = 0
        self._departed_total = 0
        self._arrival_log.clear()
        self._vehicle_speed_base.clear()
        self._weather_speed_factor = 1.0

    def history(self) -> dict[str, Any]:
        """The live run's compact time series, for the dashboard's trend charts."""
        with self.lock:
            return {
                "runId": self.state.get("runId"),
                "scenario": self.state.get("scenario"),
                "status": self.state.get("status"),
                "samples": list(self._history),
            }

    def _append_event(
        self,
        kind: str,
        severity: str,
        sim_time: int,
        clock: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._event_seq += 1
        event = {
            "id": f"evt-{self._event_seq}",
            "kind": kind,
            "severity": severity,
            "t": sim_time,
            "clock": clock,
            "message": message,
            "detail": detail or {},
        }
        self._events.append(event)
        self._events = self._events[-40:]
        return event

    def _record_controller_event(
        self, checkpoint: Path | None, scenario: str, network: str
    ) -> None:
        """Say which controller/weights this run is actually using."""
        active = policy.scenario(network)
        self._append_event(
            "modelLoaded",
            "info",
            0,
            "00:00:00",
            f"{active.get('label') or active.get('method')} controlling {scenario}",
            {
                "method": active.get("method"),
                # The network that runs here, not the one the settings page is on.
                "network": network,
                "checkpoint": Path(checkpoint).name if checkpoint else None,
                "checkpointSource": active.get("checkpointSource"),
            },
        )

    def _controller_metrics(self) -> dict[str, Any]:
        """Counters of the active controller (LLM calls, tokens, fallbacks, cost)."""
        controller = getattr(self, "controller", None)
        if controller is None:
            return {}
        try:
            return dict(controller.metrics())
        except Exception:
            return {}

    def _comms(
        self,
        env: CoTrafficEnv,
        scenario: str,
        signals: list[dict[str, Any]],
        queued_counts: Counter,
        now: float,
    ) -> dict[str, Any]:
        """The coordination channel between signalised intersections.

        Every decision each intersection sends its downstream neighbours the triple
        ``[queue, releasing, pressure]`` (``CoTrafficEnv._messages``). ``releasing`` is
        the poke: the sender's light is green on the link that feeds the neighbour, so
        the neighbour knows traffic is about to arrive. This publishes that channel as
        it actually stands, so the map can show who is talking to whom and who is
        currently handing traffic over.
        """
        links = getattr(env, "neighbour_links", {}) or {}
        intersections = getattr(env, "intersections", {}) or {}
        geometry = getattr(env, "geometry", {}) or {}
        if not links:
            return {
                "enabled": False,
                "links": [],
                "total": 0,
                "pokes": 0,
                "greenOnly": 0,
                "maxQueue": 0,
            }

        points: dict[str, list[float]] = {}
        for tls_id, geo in geometry.items():
            try:
                points[tls_id] = _project(scenario, float(geo.x), float(geo.y))
            except Exception:
                continue

        entries: list[dict[str, Any]] = []
        pokes = 0
        green_only = 0
        max_queue = 0
        for tls_id, sides in links.items():
            upstream = intersections.get(tls_id)
            origin = points.get(tls_id)
            if upstream is None or origin is None:
                continue
            for side, link in sides.items():
                try:
                    neighbour_id, in_lanes, link_indices = link
                except Exception:
                    continue
                target = points.get(neighbour_id)
                if target is None:
                    continue
                # The sender's own phase decides the poke: green on the link that
                # feeds this neighbour is exactly what `releasing` reports.
                try:
                    releasing = bool(
                        not upstream.in_yellow
                        and bool(upstream.phase_links[upstream.phase] & link_indices)
                    )
                except Exception:
                    releasing = False
                try:
                    green_elapsed = round(float(upstream.green_elapsed(now)), 1)
                except Exception:
                    green_elapsed = None
                # `in_lanes` are the sender's own approach lanes feeding this link, so
                # this is the traffic actually about to be handed over — not the
                # receiver's queue, and not a count of cars anywhere on the corridor.
                queue = int(sum(queued_counts.get(lane, 0) for lane in in_lanes))
                # A green link with nothing behind it is not a hand-off. Counting it as
                # one made every junction look busy at once, because a green phase feeds
                # several neighbours simultaneously. A poke now requires traffic to move.
                handover = bool(releasing and queue > 0)
                if handover:
                    pokes += 1
                    max_queue = max(max_queue, queue)
                elif releasing:
                    green_only += 1
                entries.append(
                    {
                        "from": tls_id,
                        "to": neighbour_id,
                        "side": side,
                        "fromPoint": origin,
                        "toPoint": target,
                        "releasing": releasing,
                        "handover": handover,
                        "queue": queue,
                        "greenElapsedS": green_elapsed,
                    }
                )

        obs_cfg = getattr(env, "obs_cfg", None)
        return {
            # Whether the active controller actually reads these messages. Max-Pressure
            # and the learned policies do; a policy without the neighbour observation
            # still has the graph, but nothing is being exchanged over it.
            "enabled": bool(getattr(obs_cfg, "neighbours", False)),
            "links": entries,
            "total": len(entries),
            # `pokes` is hand-offs with traffic behind them; `greenOnly` is the green
            # links that are carrying nothing, kept so the two are never conflated.
            "pokes": pokes,
            "greenOnly": green_only,
            "maxQueue": max_queue,
        }

    def _metrics(
        self,
        env: CoTrafficEnv,
        scenario: str,
        vehicles: list[dict[str, Any]],
        pedestrians: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        sim_time: int,
        clock: str,
    ) -> dict[str, Any]:
        """Per-step numbers the dashboard plots. Every value is measured here."""
        conn = env.conn
        speeds = [float(v.get("speed") or 0.0) for v in vehicles]
        queued = [v for v in vehicles if v.get("waiting")]
        waits = [float(v.get("waitingTime") or 0.0) for v in vehicles]
        self._arrived_total += int(conn.simulation.getArrivedNumber())
        self._departed_total += int(conn.simulation.getDepartedNumber())
        self._arrival_log.append((sim_time, self._arrived_total))
        while self._arrival_log and sim_time - self._arrival_log[0][0] > 120:
            self._arrival_log.popleft()
        recent = [total for t, total in self._arrival_log if t >= sim_time - 60]
        throughput = float(max(0, recent[-1] - recent[0])) if len(recent) >= 2 else 0.0

        junctions: list[dict[str, Any]] = []
        try:
            lanes_by_tls = _lanes_by_tls(scenario)
        except Exception:
            lanes_by_tls = {}
        lane_counts = Counter(v.get("lane") for v in vehicles if v.get("lane"))
        queued_counts = Counter(v.get("lane") for v in queued if v.get("lane"))
        lane_speeds: dict[str, list[float]] = {}
        for vehicle in vehicles:
            lane = vehicle.get("lane")
            if lane:
                lane_speeds.setdefault(lane, []).append(float(vehicle.get("speed") or 0.0))
        signals_by_id = {signal["id"]: signal for signal in signals}
        for tls, lanes in lanes_by_tls.items():
            queue = sum(queued_counts[lane] for lane in lanes)
            carried = sum(lane_counts[lane] for lane in lanes)
            speeds = [speed for lane in lanes for speed in lane_speeds.get(lane, [])]
            average_speed = round(3.6 * sum(speeds) / len(speeds), 1) if speeds else 0.0
            signal = signals_by_id.get(tls, {})
            junction = {
                "id": tls,
                "lanes": len(lanes),
                "vehicles": carried,
                "queue": queue,
                # Queue per controlled lane: a pressure proxy, not a phase pressure.
                "pressure": round(queue / max(1, len(lanes)), 2),
                "queueShare": round(queue / carried, 3) if carried else 0.0,
                "avgSpeedKmh": average_speed,
                "duration": signal.get("duration"),
                "green": signal.get("green"),
                "phase": signal.get("phase"),
                "state": signal.get("state"),
            }
            junctions.append(junction)
            self._junction_history.setdefault(tls, deque(maxlen=JUNCTION_HISTORY)).append(
                {
                    "t": sim_time,
                    "queue": queue,
                    "pressure": junction["pressure"],
                    "avgSpeedKmh": average_speed,
                }
            )

        sample = {
            "t": sim_time,
            "clock": clock,
            "vehicles": len(vehicles),
            "queued": len(queued),
            # The forecast reads `queue`; the charts read `queued`. Publish both so the
            # run's own history feeds Predict without a translation layer.
            "queue": len(queued),
            "avgSpeedKmh": round(3.6 * sum(speeds) / len(speeds), 1) if speeds else 0.0,
            "arrived": self._arrived_total,
            "throughputPerMin": round(throughput, 1),
        }
        if not self._history or self._history[-1]["t"] != sim_time:
            self._history.append(sample)

        return {
            "queued": len(queued),
            "queueShare": round(len(queued) / len(vehicles), 3) if vehicles else 0.0,
            "avgSpeedKmh": sample["avgSpeedKmh"],
            "avgWaitingS": round(sum(waits) / len(waits), 1) if waits else 0.0,
            "arrivedTotal": self._arrived_total,
            "departedTotal": self._departed_total,
            "throughputPerMin": sample["throughputPerMin"],
            "signalPhaseChanges": self._phase_changes,
            "controllerCalls": self._controller_calls,
            "lastDecisionMs": self._last_decision_ms,
            "junctions": junctions,
            "comms": self._comms(env, scenario, signals, queued_counts, float(sim_time)),
        }

    def _publish_events(
        self, vehicles: list[dict[str, Any]], pedestrians: list[dict[str, Any]],
        sim_time: int, clock: str, signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rising-edge events of the live run, for the dashboard's Events tab.

        Events are derived from the state the session already publishes, so the tab shows
        what is happening in *this* run instead of the static demo copy.
        """
        active: dict[str, tuple[str, str]] = {}
        emergency = [
            v for v in vehicles
            if v.get("vehicleClass") == "emergency" or "emergency" in str(v.get("type") or "")
        ]
        if emergency:
            names = ", ".join(v["id"] for v in emergency[:3])
            active["emergency"] = (f"Emergency vehicle on the corridor ({names})", "critical")
        buses = [v for v in vehicles if v.get("vehicleClass") == "bus"]
        if buses:
            active["bus"] = (f"{len(buses)} bus in service", "info")
        queued = [v for v in vehicles if v.get("waiting")]
        if vehicles and len(queued) >= max(5, 0.35 * len(vehicles)):
            active["congestion"] = (
                f"{len(queued)} of {len(vehicles)} vehicles queued", "warning"
            )
        blocked = [v for v in vehicles if str(v.get("type") or "").startswith("incident")]
        if blocked:
            active["incident"] = ("Incident vehicle blocking a lane", "critical")
        if len(pedestrians) > 80:
            active["pedestrians"] = (
                f"{len(pedestrians)} pedestrians on the corridor", "info"
            )
        for key, (message, severity) in active.items():
            if key in self._event_keys:
                continue
            self._event_keys.add(key)
            self._event_seq += 1
            self._events.append(
                {
                    "id": f"evt-{self._event_seq}",
                    "kind": key,
                    "severity": severity,
                    "t": sim_time,
                    "clock": clock,
                    "message": message,
                    "detail": {},
                }
            )
        # Phase transitions are counted for the KPIs but are not published as events:
        # a 2x2 corridor changes them several times a second and they drown the feed.
        for signal in signals:
            previous = self._phase_state.get(signal["id"])
            if previous is not None and signal.get("state") != previous:
                self._phase_changes += 1
            self._phase_state[signal["id"]] = signal.get("state")
        self._events = self._events[-40:]
        self._event_keys &= set(active)
        return list(self._events)

    def _run_after(
        self,
        previous: threading.Thread | None,
        scenario: str,
        method: str,
        checkpoint: Path | None,
        stop_event: threading.Event,
    ) -> None:
        """Wait for the retired run to release SUMO, then start this one."""
        if previous is not None and previous is not threading.current_thread():
            previous.join()
        if stop_event.is_set():
            return
        self._run(scenario, method, checkpoint, stop_event)

    def _run(
        self,
        scenario: str,
        method: str,
        checkpoint: Path | None,
        stop_event: threading.Event,
    ) -> None:
        env: CoTrafficEnv | None = None
        try:
            protocol = config.load_protocol()
            network = SCENARIOS[scenario]
            controller = make_controller(method, checkpoint)
            # Published with every live frame so the dashboard can show the LLM team's
            # calls, tokens and fallbacks while the run is still going.
            self.controller = controller
            # The live map draws one shape per vehicle class, so the run also carries the
            # buses and the emergency vehicles, not just cars and pedestrians.
            net_cfg = config.load("networks", network)
            demand, _ = live_demand(net_cfg)
            unsupported = set(net_cfg.get("unsupported_scenarios", []))
            live = ["buses", "emergency"]
            if net_cfg.get("pedestrians", False):
                live.insert(0, "pedestrians")
            live_scenarios = tuple(name for name in live if name not in unsupported)
            cycle = {"n": 0}

            def next_episode(_rng: Any) -> Any:
                """A fresh quick window per cycle, so the live map never runs dry.

                One 20-minute episode emptied the map when it ended: demand stops at the
                measure window and the cooldown drains it. That was the other half of
                "the vehicles disappeared". Each cycle uses its own demand seed.
                """
                cycle["n"] += 1
                # Read the dial per cycle, not once per run: the operator can change it
                # while the map is running, and the next window picks it up.
                return evaluation_episode(
                    network,
                    demand,
                    live_scenarios,
                    seed=cycle["n"],
                    output_dir=RESULTS_DIR / "tmp" / f"live-{scenario}",
                    ssm=False,
                    quick=True,
                    protocol=protocol,
                    scale=live_demand_scale(net_cfg, self._demand_level),
                )

            env = CoTrafficEnv(
                network,
                next_episode,
                controller.agent_cfg,
                controlled=controller.controlled,
                runtime_scenarios=(),
                step_hooks=controller.step_hooks(),
                substep_hooks=(
                    lambda run_env, _now: self._substep(run_env, scenario, stop_event),
                ),
                compute_observations=controller.needs_observations,
                protocol=protocol,
                gui=self._gui,
            )
            env.run_id = str(self.state.get("runId") or f"live-{scenario}")
            self._conn = env.conn
            self._weather_base.clear()
            self._vehicle_speed_base.clear()
            self._weather_speed_factor = 1.0
            self._record_controller_event(checkpoint, scenario, network)
            while not stop_event.is_set():
                obs, _ = env.reset()
                controller.reset(env)
                with self.lock:
                    if self._run_stop is stop_event:
                        self.state["status"] = "running"
                obs = self._drive_cycle(env, controller, obs, scenario, stop_event)
                # The next window continues the same run: keep the clock monotonic. A
                # retired run must not push its offset onto the run that replaced it.
                if env.episode is not None and self._run_stop is stop_event:
                    self._time_offset += int(env.episode.end_time)
            if not stop_event.is_set():
                with self.lock:
                    if self._run_stop is stop_event:
                        self.state["status"] = "idle"
        except Exception as error:  # reported to the dashboard, thread ends cleanly
            with self.lock:
                if self._run_stop is stop_event:
                    self.state.update({"status": "error", "error": str(error)})
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception:
                    pass
            # A retired run must not close the connection of the run that replaced it.
            if self._run_stop is stop_event:
                self._conn = None
                self._close_traci()

    def _drive_cycle(
        self, env: CoTrafficEnv, controller: Any, obs: Any, scenario: str,
        stop_event: threading.Event,
    ) -> Any:
        """Step one episode's decisions until it ends or the run is retired."""
        while env.agents and not stop_event.is_set():
            self._apply_pending_incidents(env, scenario)
            self._apply_pending_signals(env.conn)
            self._apply_weather(env.conn)
            if self.pause_event.is_set():
                with self.lock:
                    queued = self.pending_steps
                    self.pending_steps = 0
                if queued <= 0:
                    time.sleep(0.05)
                    continue
                for _ in range(queued):
                    if not env.agents or stop_event.is_set():
                        break
                    obs = self._advance(env, controller, obs)
                self._publish(env, scenario, stop_event)
                continue
            obs = self._advance(env, controller, obs)
            self._publish(env, scenario, stop_event)
            # Wall pacing happens per simulated step in _substep, so the map gets
            # small frames spread across the decision instead of one jump.
        return obs

    def _apply_weather(self, conn: Any) -> None:
        """Bring the loaded network's vehicle types in line with the weather.

        SUMO has no weather switch, so rain is expressed the way SUMO models it
        for drivers: a lower speed factor and a longer desired headway. The base
        values are captured the first time a type is seen, which is what lets
        clearing the rain restore the network's calibration exactly.
        """
        effect = WEATHER_EFFECTS[self._weather]
        factor = float(effect["speed_factor"])
        # Undo the factor the population already carries when recording a base, so a
        # type or vehicle first seen mid-rain keeps its dry-road value as the base.
        applied = self._weather_speed_factor or 1.0
        try:
            type_ids = list(conn.vehicletype.getIDList())
        except Exception:
            type_ids = []
        for type_id in type_ids:
            base = self._weather_base.get(type_id)
            if base is None:
                try:
                    base = (
                        conn.vehicletype.getSpeedFactor(type_id) / applied,
                        conn.vehicletype.getTau(type_id),
                    )
                except Exception:
                    continue
                self._weather_base[type_id] = base
            try:
                conn.vehicletype.setSpeedFactor(type_id, base[0] * factor)
                conn.vehicletype.setTau(
                    type_id, base[1] if effect["tau"] is None else float(effect["tau"])
                )
            except Exception:
                continue
        # SUMO copies the type's speedFactor into a vehicle at insertion, so the type
        # change above only reached the traffic that arrived afterwards: the vehicles
        # already driving kept their dry-road desired speed and the rain read as doing
        # nothing. Their own factor (which carries each driver's speedDev) is the base.
        try:
            vehicle_ids = list(conn.vehicle.getIDList())
        except Exception:
            self._weather_speed_factor = factor
            return
        bases = self._vehicle_speed_base
        for vehicle_id in vehicle_ids:
            if vehicle_id not in bases:
                try:
                    bases[vehicle_id] = float(
                        conn.vehicle.getSpeedFactor(vehicle_id)
                    ) / applied
                except Exception:
                    continue
            try:
                conn.vehicle.setSpeedFactor(vehicle_id, bases[vehicle_id] * factor)
            except Exception:
                continue
        # Vehicles that left must not keep an entry (SUMO reuses ids like car.0).
        for gone in set(bases) - set(vehicle_ids):
            bases.pop(gone, None)
        self._weather_speed_factor = factor

    def _advance(self, env: CoTrafficEnv, controller, obs):
        started = time.perf_counter()
        actions = controller.act(env, obs)
        self._controller_calls += 1
        self._last_decision_ms = round((time.perf_counter() - started) * 1000, 2)
        obs, _rewards, _terminations, _truncations, _infos = env.step(actions)
        return obs


session = SimulationSession()
