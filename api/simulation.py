"""Live dashboard simulation, driven by the ``cotraffic`` domain.

The live run must be *the same* thing the study reports: the controller comes from
``make_controller`` (the active policy: learned checkpoint, LLM, or baseline), the episode
comes from ``evaluation_episode`` (the protocol's quick windows), and every phase change
passes the environment's safety shield. Nothing here talks to SUMO directly except to read
the state it publishes to the dashboard.
"""

from __future__ import annotations

import sys
import threading
import time
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import api.policy as policy
from cotraffic import config
from cotraffic.controllers.registry import make_controller
from cotraffic.envs.episodes import evaluation_episode
from cotraffic.envs.traffic_env import CoTrafficEnv
from cotraffic.networks.build import ensure_network
from cotraffic.paths import RESULTS_DIR

# The dashboard's scenario ids → cotraffic network names (configs/networks/<name>.yaml).
SCENARIOS = {"grid-2x2": "grid2x2", "grid-3x3": "grid3x3"}
DEMAND = "medium"

# Where the (normalised) network extents are drawn on the map. The exact figures matter
# less than the fact that roads and vehicles share the same projection.
GEO_BOUNDS = {
    "grid-2x2": {"west": -97.7245, "east": -97.7192, "south": 30.2649, "north": 30.2704},
    "grid-3x3": {"west": -97.7262, "east": -97.7168, "south": 30.2649, "north": 30.2712},
}


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
                try:
                    x, y = (float(value) for value in pair.split(",", 1))
                except (ValueError, TypeError):
                    continue
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return (0.0, 1.0, 0.0, 1.0)
    return (min(xs), max(xs), min(ys), max(ys))


def _project(scenario: str, x: float, y: float) -> list[float]:
    bounds = GEO_BOUNDS[scenario]
    min_x, max_x, min_y, max_y = _extent(scenario)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    longitude = bounds["west"] + (x - min_x) / span_x * (bounds["east"] - bounds["west"])
    latitude = bounds["south"] + (y - min_y) / span_y * (bounds["north"] - bounds["south"])
    return [round(longitude, 7), round(latitude, 7)]


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
            points = []
            for pair in (lane.get("shape") or "").split():
                try:
                    x, y = (float(value) for value in pair.split(",", 1))
                except (ValueError, TypeError):
                    continue
                points.append(_project(scenario, x, y))
            if len(points) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "id": lane.get("id", edge_id),
                            "edge": edge_id,
                            "laneIndex": lane.get("index", "0"),
                            "width": lane.get("width", "3.2"),
                        },
                        "geometry": {"type": "LineString", "coordinates": points},
                    }
                )
    return {"type": "FeatureCollection", "features": features}


class SimulationSession:
    """One live run at a time, on a background thread, mirroring ``run_episode``'s loop."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pending_steps = 0
        self.state: dict[str, Any] = {
            "status": "idle",
            "scenario": None,
            "simulationTime": 0,
            "clock": "00:00:00",
            "speed": 1,
            "method": None,
            "vehicles": [],
            "signals": [],
            "metrics": {},
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.state)

    # --- controls -------------------------------------------------------------------

    def start(self, scenario: str, speed: float = 1) -> dict[str, Any]:
        if scenario not in SCENARIOS:
            raise ValueError("only grid-2x2 and grid-3x3 support live simulation")
        active = policy.current()
        method, network = active["method"], SCENARIOS[scenario]
        # The checkpoint must match the network that actually runs, not the one the settings
        # page was last pointed at: a grid4x4 policy on the 2x2 grid would mis-shape the
        # observations the trained controller expects.
        ready, reason = policy.availability(method, network)
        if not ready:
            raise ValueError(reason or f"{method} is not available")
        checkpoint = policy.checkpoint_path(method, network)
        self.stop()
        self.stop_event.clear()
        self.pause_event.clear()
        with self.lock:
            self.state.update(
                {
                    "status": "starting",
                    "scenario": scenario,
                    "network": network,
                    "simulationTime": 0,
                    "speed": speed,
                    "method": method,
                    "vehicles": [],
                    "signals": [],
                    "metrics": {},
                }
            )
        self.thread = threading.Thread(
            target=self._run, args=(scenario, method, checkpoint), daemon=True
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
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self._close_traci()
        with self.lock:
            self.state.update({"status": "idle", "vehicles": [], "signals": []})
        return self.snapshot()

    def set_speed(self, speed: float) -> dict[str, Any]:
        with self.lock:
            self.state["speed"] = max(0.25, min(float(speed), 20))
        return self.snapshot()

    # --- run ------------------------------------------------------------------------

    @staticmethod
    def _close_traci() -> None:
        """Release the TraCI link if a run died before closing its environment."""
        try:
            import traci

            traci.close()
        except Exception:
            pass

    def _publish(self, env: CoTrafficEnv, scenario: str) -> None:
        conn = env.conn
        sim_time = int(conn.simulation.getTime())
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
                }
            )
        signals = []
        for tls_id in conn.trafficlight.getIDList():
            try:
                signals.append(
                    {
                        "id": tls_id,
                        "state": conn.trafficlight.getRedYellowGreenState(tls_id),
                        "phase": conn.trafficlight.getPhase(tls_id),
                    }
                )
            except Exception:
                continue
        with self.lock:
            self.state.update(
                {
                    "simulationTime": sim_time,
                    "clock": f"{sim_time // 3600:02d}:{sim_time % 3600 // 60:02d}:{sim_time % 60:02d}",
                    "vehicles": vehicles,
                    "signals": signals,
                    "metrics": {
                        "vehicles": len(vehicles),
                        "arrived": int(conn.simulation.getArrivedNumber()),
                    },
                }
            )

    def _run(self, scenario: str, method: str, checkpoint: Path | None) -> None:
        env: CoTrafficEnv | None = None
        try:
            protocol = config.load_protocol()
            network = SCENARIOS[scenario]
            controller = make_controller(method, checkpoint)
            episode = evaluation_episode(
                network,
                DEMAND,
                (),
                seed=0,
                output_dir=RESULTS_DIR / "tmp" / f"live-{scenario}",
                ssm=False,
                quick=True,
                protocol=protocol,
            )
            env = CoTrafficEnv(
                network,
                lambda rng: episode,
                controller.agent_cfg,
                controlled=controller.controlled,
                runtime_scenarios=(),
                step_hooks=controller.step_hooks(),
                compute_observations=controller.needs_observations,
                protocol=protocol,
            )
            obs, _ = env.reset(seed=0)
            controller.reset(env)
            with self.lock:
                self.state["status"] = "running"
            while env.agents and not self.stop_event.is_set():
                if self.pause_event.is_set():
                    with self.lock:
                        queued = self.pending_steps
                        self.pending_steps = 0
                    if queued <= 0:
                        time.sleep(0.05)
                        continue
                    for _ in range(queued):
                        if not env.agents or self.stop_event.is_set():
                            break
                        obs = self._advance(env, controller, obs)
                    self._publish(env, scenario)
                    continue
                obs = self._advance(env, controller, obs)
                self._publish(env, scenario)
                speed = self.state.get("speed", 1) or 1
                time.sleep(max(0.0, min(1.0, 1.0 / max(float(speed), 0.25))))
            if not self.stop_event.is_set():
                with self.lock:
                    self.state["status"] = "idle"
        except Exception as error:  # reported to the dashboard, thread ends cleanly
            with self.lock:
                self.state.update({"status": "error", "error": str(error)})
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception:
                    pass
            self._close_traci()

    @staticmethod
    def _advance(env: CoTrafficEnv, controller, obs):
        actions = controller.act(env, obs)
        obs, _rewards, _terminations, _truncations, _infos = env.step(actions)
        return obs


session = SimulationSession()
