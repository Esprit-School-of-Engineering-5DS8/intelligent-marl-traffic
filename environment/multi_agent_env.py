"""
environment/multi_agent_env.py
Core MultiAgentEnvironment — wraps SUMO/TraCI for the multi-agent loop.
Extracted from scenarios/grid_3x3/runner.py for reuse across all scenarios.
"""

import os
import sys
import csv
from typing import Dict, List, Any

# SUMO_HOME auto-detection
if "SUMO_HOME" not in os.environ:
    if sys.platform == "win32":
        default_win = r"C:\Program Files (x86)\Eclipse\Sumo"
        if os.path.exists(default_win):
            os.environ["SUMO_HOME"] = default_win
    else:
        default_linux = "/usr/share/sumo"
        if os.path.exists(default_linux):
            os.environ["SUMO_HOME"] = default_linux

sumo_home = os.environ.get("SUMO_HOME", "")
tools_dir = os.path.join(sumo_home, "tools") if sumo_home else ""
if tools_dir and tools_dir not in sys.path:
    sys.path.append(tools_dir)

try:
    import traci
except ImportError:
    raise ImportError(f"TraCI not found. SUMO_HOME='{sumo_home}'")


class MultiAgentEnv:
    """
    Generic multi-agent SUMO environment.
    Works with any .sumocfg file — 2x2, 3x3, or Monaco.
    """

    def __init__(self, sumocfg_path: str, use_gui: bool = False,
                 step_length: float = 1.0, delay_ms: int = 50):
        self.sumocfg_path = sumocfg_path
        self.use_gui = use_gui
        self.step_length = step_length
        self.delay_ms = delay_ms
        self.step_count = 0
        self.history: List[Dict[str, Any]] = []

    def start(self):
        binary = "sumo-gui" if self.use_gui else "sumo"
        cmd = [binary, "-c", self.sumocfg_path,
               "--step-length", str(self.step_length),
               "--no-warnings", "true", "--quit-on-end", "true"]
        if self.use_gui:
            cmd += ["--start", "true", "--delay", str(self.delay_ms)]
        traci.start(cmd)
        tls_ids = traci.trafficlight.getIDList()
        print(f"[Env] {len(tls_ids)} traffic lights: {list(tls_ids)}")
        return list(tls_ids)

    def step(self) -> Dict[str, Any]:
        traci.simulationStep()
        self.step_count += 1
        veh_ids = traci.vehicle.getIDList()
        n = len(veh_ids)
        total_wait = sum(traci.vehicle.getWaitingTime(v) for v in veh_ids)
        total_speed = sum(traci.vehicle.getSpeed(v) for v in veh_ids)
        total_co2 = sum(traci.vehicle.getCO2Emission(v) for v in veh_ids)
        total_fuel = sum(traci.vehicle.getFuelConsumption(v) for v in veh_ids)
        record = {
            "step": self.step_count,
            "active_vehicles": n,
            "arrived_vehicles": traci.simulation.getArrivedNumber(),
            "avg_speed_m_s": round(total_speed / n, 2) if n else 0.0,
            "total_waiting_time_s": round(total_wait, 2),
            "co2_mg_s": round(total_co2, 2),
            "fuel_ml_s": round(total_fuel, 2),
        }
        self.history.append(record)
        return record

    def close(self, output_csv: str = "simulation_metrics.csv"):
        try:
            traci.close()
        except Exception:
            pass
        if self.history:
            with open(output_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(self.history[0].keys()))
                writer.writeheader()
                writer.writerows(self.history)
            print(f"[Env] Metrics saved to {output_csv}")
