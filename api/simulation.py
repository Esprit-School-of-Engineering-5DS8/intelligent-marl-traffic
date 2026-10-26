"""Real-time SUMO session manager for the 2x2 and 3x3 scenarios."""

from __future__ import annotations

import asyncio
import threading
import time
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {
    "grid-2x2": ROOT / "scenarios" / "grid_2x2" / "grid2x2.sumocfg",
    "grid-3x3": ROOT / "scenarios" / "grid_3x3" / "grid3x3.sumocfg",
}
SCENARIO_GEO_BOUNDS = {
    "grid-2x2": {"west": -97.7245, "east": -97.7192, "south": 30.2649, "north": 30.2704, "width": 400.0, "height": 400.0},
    "grid-3x3": {"west": -97.7262, "east": -97.7168, "south": 30.2649, "north": 30.2712, "width": 600.0, "height": 600.0},
}


def _net_file(scenario: str) -> Path:
    return SCENARIOS[scenario].parent / ("grid2x2.net.xml" if scenario == "grid-2x2" else "grid3x3.net.xml")


@lru_cache(maxsize=4)
def _transformer(scenario: str):
    from pyproj import Transformer
    location = ET.parse(_net_file(scenario)).getroot().find("location")
    offset_x, offset_y = (float(value) for value in location.get("netOffset", "0,0").split(","))
    return Transformer.from_crs("EPSG:32614", "EPSG:4326", always_xy=True), offset_x, offset_y


def _project_point(scenario: str, x: float, y: float) -> list[float]:
    try:
        # The strict demo grids are generated in a local 400/600m coordinate space.
        bounds = SCENARIO_GEO_BOUNDS[scenario]
        longitude = bounds["west"] + (x / bounds["width"]) * (bounds["east"] - bounds["west"])
        latitude = bounds["south"] + (y / bounds["height"]) * (bounds["north"] - bounds["south"])
        return [round(longitude, 7), round(latitude, 7)]
    except Exception:
        bounds = SCENARIO_GEO_BOUNDS[scenario]
        return [bounds["west"] + (x / bounds["width"]) * (bounds["east"] - bounds["west"]), bounds["south"] + (y / bounds["height"]) * (bounds["north"] - bounds["south"])]


def network_geojson(scenario: str) -> dict[str, Any]:
    config = SCENARIOS.get(scenario)
    if config is None:
        raise ValueError("unknown simulation scenario")
    net_file = _net_file(scenario)
    root = ET.parse(net_file).getroot()
    features: list[dict[str, Any]] = []
    for edge in root.findall("edge"):
        edge_id = edge.get("id", "")
        if edge_id.startswith(":"):
            continue
        lanes = edge.findall("lane")
        for lane in lanes:
            shape = lane.get("shape", "")
            points = []
            for pair in shape.split():
                try:
                    x, y = (float(value) for value in pair.split(",", 1))
                except (ValueError, TypeError):
                    continue
                points.append(_project_point(scenario, x, y))
            if len(points) >= 2:
                features.append({"type": "Feature", "properties": {"id": lane.get("id", edge_id), "edge": edge_id, "laneIndex": lane.get("index", "0"), "width": lane.get("width", "3.2")}, "geometry": {"type": "LineString", "coordinates": points}})
    return {"type": "FeatureCollection", "features": features}


class SimulationSession:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self.pending_steps = 0
        self.state: dict[str, Any] = {
            "status": "idle", "scenario": None, "simulationTime": 0,
            "clock": "00:00:00", "speed": 1, "vehicles": [], "signals": [],
            "metrics": {},
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.state)

    def start(self, scenario: str, speed: float = 1) -> dict[str, Any]:
        if scenario not in SCENARIOS:
            raise ValueError("only grid-2x2 and grid-3x3 support live simulation")
        self.stop()
        self.stop_event.clear()
        self.pause_event.clear()
        with self.lock:
            self.state.update({"status": "starting", "scenario": scenario, "simulationTime": 0, "speed": speed})
        self.thread = threading.Thread(target=self._run, args=(scenario,), daemon=True)
        self.thread.start()
        return self.snapshot()

    def pause(self) -> dict[str, Any]:
        self.pause_event.set()
        with self.lock:
            if self.state["status"] == "running": self.state["status"] = "paused"
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        self.pause_event.clear()
        with self.lock:
            if self.state["status"] == "paused": self.state["status"] = "running"
        return self.snapshot()

    def step(self, count: int = 1) -> dict[str, Any]:
        """Advance a paused run by N seconds, for stepping through a scenario."""
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
        if self.thread and self.thread.is_alive(): self.thread.join(timeout=3)
        self.close_connection()
        with self.lock: self.state["status"] = "idle"
        return self.snapshot()

    @staticmethod
    def close_connection() -> None:
        """Release the TraCI link.

        Without this, starting a second run (for example after switching from the
        3x3 to the 2x2 grid) fails with "Connection 'default' is already active".
        """
        try:
            import traci

            traci.close()
        except Exception:
            pass

    def set_speed(self, speed: float) -> dict[str, Any]:
        with self.lock: self.state["speed"] = max(0.25, min(float(speed), 20))
        return self.snapshot()

    # Link characters, best state first: a lane that has a green link and a red
    # one (permissive turn) is shown green.
    _LINK_ORDER = {"G": 5, "g": 4, "y": 3, "Y": 3, "r": 2, "R": 2}

    @classmethod
    def _signals(cls, traci: Any) -> list[dict[str, Any]]:
        """Signal state per controlled lane, straight from SUMO."""
        signals: list[dict[str, Any]] = []
        try:
            for tls_id in traci.trafficlight.getIDList():
                characters = traci.trafficlight.getRedYellowGreenState(tls_id)
                links = traci.trafficlight.getControlledLinks(tls_id)
                lanes: dict[str, str] = {}
                for index, group in enumerate(links):
                    if index >= len(characters):
                        break
                    character = characters[index]
                    for link in group:
                        lane_id = link[0]
                        if not lane_id:
                            continue
                        previous = lanes.get(lane_id)
                        if previous is None or cls._LINK_ORDER.get(character, 0) > cls._LINK_ORDER.get(previous, 0):
                            lanes[lane_id] = character
                if lanes:
                    signals.append({"id": tls_id, "lanes": lanes})
        except Exception:
            return signals
        return signals

    def _publish(self, traci: Any, scenario: str) -> None:
        sim_time = int(traci.simulation.getTime())
        vehicles = []
        for vehicle_id in traci.vehicle.getIDList():
            x, y = traci.vehicle.getPosition(vehicle_id)
            longitude, latitude = _project_point(scenario, x, y)
            speed = traci.vehicle.getSpeed(vehicle_id)
            vehicles.append({"id": vehicle_id, "x": x, "y": y, "lng": longitude, "lat": latitude, "angle": traci.vehicle.getAngle(vehicle_id), "speed": speed, "waiting": speed < 0.1})
        with self.lock:
            self.state.update({"simulationTime": sim_time, "clock": f"{sim_time // 3600:02d}:{sim_time % 3600 // 60:02d}:{sim_time % 60:02d}", "vehicles": vehicles, "signals": self._signals(traci), "metrics": {"vehicles": len(vehicles), "arrived": traci.simulation.getArrivedNumber()}})

    def _run(self, scenario: str) -> None:
        try:
            import traci
            # A previous run may have crashed before it could close its link.
            self.close_connection()
            binary = "sumo-gui" if False else "sumo"
            traci.start([binary, "-c", str(SCENARIOS[scenario]), "--step-length", "1"])
            with self.lock: self.state["status"] = "running"
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    with self.lock:
                        queued = self.pending_steps
                        self.pending_steps = 0
                    if queued <= 0:
                        time.sleep(0.05); continue
                    for _ in range(queued): traci.simulationStep()
                    self._publish(traci, scenario)
                    continue
                traci.simulationStep()
                self._publish(traci, scenario)
                if self.state["simulationTime"] >= 86400: break
                time.sleep(max(0.01, 1 / max(self.state["speed"], 0.25)))
        except Exception as error:
            with self.lock: self.state.update({"status": "error", "error": str(error)})
        finally:
            self.close_connection()


session = SimulationSession()
