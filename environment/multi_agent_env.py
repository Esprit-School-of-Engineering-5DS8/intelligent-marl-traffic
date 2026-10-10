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

from environment.topology import discover_topology, neighbor_map_from_net, net_file_from_sumocfg
from environment.traffic_light import TrafficLightAgent


class MultiAgentEnv:
    """
    Generic multi-agent SUMO environment.
    Works with any .sumocfg file — 2x2, 3x3, or Monaco.
    """

    def __init__(self, sumocfg_path: str, use_gui: bool = False,
                 step_length: float = 1.0, delay_ms: int = 50,
                 seed: int = None, tripinfo_output: str = None,
                 min_green: int = 10, port: int = None):
        self.sumocfg_path = sumocfg_path
        self.use_gui = use_gui
        self.step_length = step_length
        self.delay_ms = delay_ms
        self.seed = seed
        self.tripinfo_output = tripinfo_output
        self.min_green = min_green
        self.port = port
        self.step_count = 0
        self.history: List[Dict[str, Any]] = []
        self.tls_ids: List[str] = []
        self.agents: Dict[str, TrafficLightAgent] = {}
        self.neighbors: Dict[str, Dict[str, str]] = {}

    def start(self):
        binary = "sumo-gui" if self.use_gui else "sumo"
        cmd = [binary, "-c", self.sumocfg_path,
               "--step-length", str(self.step_length),
               "--no-warnings", "true", "--quit-on-end", "true"]
        if self.seed is not None:
            cmd += ["--seed", str(self.seed)]
        if self.tripinfo_output:
            cmd += ["--tripinfo-output", self.tripinfo_output]
        if self.use_gui:
            cmd += ["--start", "true", "--delay", str(self.delay_ms)]
        traci.start(cmd, port=self.port)
        self.tls_ids = sorted(traci.trafficlight.getIDList())
        print(f"[Env] {len(self.tls_ids)} traffic lights: {self.tls_ids}")
        return list(self.tls_ids)

    def build_agents(self):
        """
        Build one TrafficLightAgent per TLS and pin initial phases.

        Only call this for controlled arms: initializing agents fixes the
        phase and disables SUMO's built-in program timer, so `sumo_default`
        runs must not call it.
        """
        for tls_id in self.tls_ids:
            topology = discover_topology(tls_id)
            agent = TrafficLightAgent(tls_id, topology, min_green=self.min_green)
            agent.initialize()
            self.agents[tls_id] = agent

        net_file = net_file_from_sumocfg(self.sumocfg_path)
        self.neighbors = neighbor_map_from_net(net_file, self.tls_ids)
        print(f"[Env] {len(self.agents)} agents initialized "
              f"(min_green={self.min_green}s, phases pinned)")
        return self.agents

    def get_states(self) -> Dict[str, Dict[str, Any]]:
        """Collect observation states from all agents."""
        if not self.agents:
            raise RuntimeError("build_agents() must be called before get_states()")
        return {tls_id: agent.get_state() for tls_id, agent in self.agents.items()}

    def apply_actions(self, actions: Dict[str, int]):
        """Dispatch actions to all agents (safety is enforced inside the agent)."""
        if not self.agents:
            raise RuntimeError("build_agents() must be called before apply_actions()")
        for tls_id, action in actions.items():
            agent = self.agents.get(tls_id)
            if agent is not None:
                agent.step_control(action)

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
            output_dir = os.path.dirname(os.path.abspath(output_csv))
            os.makedirs(output_dir, exist_ok=True)
            with open(output_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(self.history[0].keys()))
                writer.writeheader()
                writer.writerows(self.history)
            print(f"[Env] Metrics saved to {output_csv}")
