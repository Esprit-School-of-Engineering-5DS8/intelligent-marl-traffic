#!/usr/bin/env python3
"""
runner.py
Multi-Agent Traffic Light Control Starter for 2x2 SUMO Grid.
Compatible with both WSL Ubuntu and native Windows environments.

Features:
- Connects to SUMO via TraCI (GUI or headless).
- Multi-Agent structure: 4 traffic light agents (A0, A1, B0, B1).
- Pre-built controllers:
  * 'sumo_default' : SUMO default pre-timed logic
  * 'fixed'        : Custom fixed-time coordination
  * 'max_pressure' : Decentralized adaptive pressure-based heuristic
  * 'custom'       : Modular placeholder ready for Reinforcement Learning (Q-learning, PPO, MADDPG)
- Real-time metric tracking: waiting time, queue lengths, average speed, throughput, CO2 emissions.
- Exports metrics to CSV for data analysis and visualization.
"""

import os
import sys
import csv
import time
import argparse
from typing import Dict, List, Any

# Auto-detect SUMO_HOME for both Windows and Linux / WSL
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
    print(f"Error: Unable to import TraCI. SUMO_HOME='{sumo_home}'", file=sys.stderr)
    print("Please ensure SUMO is installed and SUMO_HOME/tools is accessible.", file=sys.stderr)
    sys.exit(1)


class TrafficLightAgent:
    """
    Represents an autonomous agent controlling one intersection in the 2x2 grid.
    Handles phase transitions, clearance yellow phases, minimum green durations,
    and state/reward observation.
    """
    def __init__(self, tls_id: str, min_green: int = 10, yellow_time: int = 3):
        self.tls_id = tls_id
        self.min_green = min_green
        self.yellow_time = yellow_time

        # Available green phases in grid2x2.net.xml:
        # Phase 0: North-South Green (GGGggrrrrrGGGggrrrrr)
        # Phase 1: North-South Yellow (yyyyyrrrrryyyyyrrrrr)
        # Phase 2: East-West Green (rrrrrGGGggrrrrrGGGgg)
        # Phase 3: East-West Yellow (rrrrryyyyyrrrrryyyyy)
        self.green_phases = [0, 2]
        self.yellow_phases = {0: 1, 2: 3}  # map current green -> corresponding yellow

        self.current_phase = 0
        self.target_phase = 0
        self.time_in_phase = 0
        self.is_yellow = False

        # Query incoming lanes
        self.incoming_lanes = list(set(traci.trafficlight.getControlledLanes(self.tls_id)))

    def get_state(self) -> Dict[str, Any]:
        """
        Extracts observations for the agent:
        - Queue length (halting vehicles with speed < 0.1 m/s)
        - Approaching vehicle counts
        - Total waiting time on incoming approaches
        - Active phase & time in phase
        """
        queue_lengths = {}
        waiting_times = {}
        vehicle_counts = {}

        total_queue = 0
        total_waiting = 0

        for lane_id in self.incoming_lanes:
            halting = traci.lane.getLastStepHaltingNumber(lane_id)
            waiting = traci.lane.getWaitingTime(lane_id)
            veh_count = traci.lane.getLastStepVehicleNumber(lane_id)

            queue_lengths[lane_id] = halting
            waiting_times[lane_id] = waiting
            vehicle_counts[lane_id] = veh_count

            total_queue += halting
            total_waiting += waiting

        return {
            "tls_id": self.tls_id,
            "current_phase": self.current_phase,
            "time_in_phase": self.time_in_phase,
            "is_yellow": self.is_yellow,
            "total_queue": total_queue,
            "total_waiting_time": total_waiting,
            "lane_queues": queue_lengths,
            "lane_waiting": waiting_times,
            "lane_counts": vehicle_counts
        }

    def compute_reward(self, state: Dict[str, Any]) -> float:
        """
        Computes the step reward for this agent.
        Standard MARL reward: negative waiting time and queue penalty.
        """
        reward = -(state["total_waiting_time"] * 0.1 + state["total_queue"] * 1.0)
        return float(reward)

    def step_control(self, action: int):
        """
        Processes agent action (0 = North-South Green, 1 = East-West Green).
        Safely enforces yellow transition phases and minimum green times.
        """
        self.time_in_phase += 1
        desired_green = self.green_phases[action % len(self.green_phases)]

        if self.is_yellow:
            if self.time_in_phase >= self.yellow_time:
                self.is_yellow = False
                self.current_phase = self.target_phase
                self.time_in_phase = 0
                traci.trafficlight.setPhase(self.tls_id, self.current_phase)
        else:
            if desired_green != self.current_phase and self.time_in_phase >= self.min_green:
                yellow_phase = self.yellow_phases.get(self.current_phase, 1)
                self.is_yellow = True
                self.target_phase = desired_green
                self.time_in_phase = 0
                traci.trafficlight.setPhase(self.tls_id, yellow_phase)


class MultiAgentEnvironment:
    """
    Manages the 2x2 multi-agent environment and metric collection.
    """
    def __init__(self, sumocfg_path: str, use_gui: bool = False, step_length: float = 1.0, delay_ms: int = 50):
        self.sumocfg_path = sumocfg_path
        self.use_gui = use_gui
        self.step_length = step_length
        self.delay_ms = delay_ms
        self.agents: Dict[str, TrafficLightAgent] = {}
        self.step_count = 0
        self.history: List[Dict[str, Any]] = []

    def start(self):
        """Launches SUMO and initializes agents."""
        binary = "sumo-gui" if self.use_gui else "sumo"
        sumo_cmd = [
            binary,
            "-c", self.sumocfg_path,
            "--step-length", str(self.step_length),
            "--no-warnings", "true",
            "--quit-on-end", "true"
        ]

        if self.use_gui:
            sumo_cmd.extend(["--start", "true", "--delay", str(self.delay_ms)])

        print(f"[MultiAgentEnvironment] Starting simulation with {binary} (delay: {self.delay_ms if self.use_gui else 0}ms)...")
        traci.start(sumo_cmd)

        tls_ids = traci.trafficlight.getIDList()
        print(f"[MultiAgentEnvironment] Discovered {len(tls_ids)} traffic lights: {list(tls_ids)}")

        for tls_id in sorted(tls_ids):
            self.agents[tls_id] = TrafficLightAgent(tls_id)

    def get_states(self) -> Dict[str, Dict[str, Any]]:
        """Collects observation states from all agents."""
        return {tls_id: agent.get_state() for tls_id, agent in self.agents.items()}

    def apply_actions(self, actions: Dict[str, int]):
        """Dispatches actions to all agents."""
        for tls_id, action in actions.items():
            if tls_id in self.agents:
                self.agents[tls_id].step_control(action)

    def step(self):
        """Advances simulation by one step and records system-wide metrics."""
        traci.simulationStep()
        self.step_count += 1

        veh_ids = traci.vehicle.getIDList()
        num_vehicles = len(veh_ids)
        
        total_waiting_time = 0.0
        total_speed = 0.0
        total_co2 = 0.0
        total_fuel = 0.0

        for v in veh_ids:
            total_waiting_time += traci.vehicle.getWaitingTime(v)
            total_speed += traci.vehicle.getSpeed(v)
            total_co2 += traci.vehicle.getCO2Emission(v)
            total_fuel += traci.vehicle.getFuelConsumption(v)

        avg_speed = (total_speed / num_vehicles) if num_vehicles > 0 else 0.0
        arrived = traci.simulation.getArrivedNumber()

        record = {
            "step": self.step_count,
            "active_vehicles": num_vehicles,
            "arrived_vehicles": arrived,
            "avg_speed_m_s": round(avg_speed, 2),
            "total_waiting_time_s": round(total_waiting_time, 2),
            "co2_mg_s": round(total_co2, 2),
            "fuel_ml_s": round(total_fuel, 2)
        }
        self.history.append(record)
        return record

    def close(self, output_csv: str = "simulation_metrics.csv"):
        """Closes TraCI and saves metrics to CSV."""
        try:
            traci.close()
        except Exception:
            pass
        print(f"\n[MultiAgentEnvironment] Simulation complete ({self.step_count} steps).")

        if self.history:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            csv_path = os.path.join(script_dir, output_csv)
            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(self.history[0].keys()))
                writer.writeheader()
                writer.writerows(self.history)
            print(f"[MultiAgentEnvironment] Saved performance log to: {csv_path}")

            avg_speeds = [r["avg_speed_m_s"] for r in self.history if r["active_vehicles"] > 0]
            total_arrived = sum(r["arrived_vehicles"] for r in self.history)
            mean_wait = sum(r["total_waiting_time_s"] for r in self.history) / len(self.history)

            print("=" * 60)
            print("         SIMULATION SUMMARY STATISTICS (2x2)   ")
            print("=" * 60)
            print(f"Total Steps Simulated  : {self.step_count}")
            print(f"Total Vehicles Arrived : {total_arrived}")
            print(f"Network Mean Speed     : {sum(avg_speeds)/len(avg_speeds):.2f} m/s" if avg_speeds else "N/A")
            print(f"Mean Step Waiting Time : {mean_wait:.2f} s")
            print("=" * 60)


# =====================================================================
# Controllers
# =====================================================================

def select_action_fixed(tls_id: str, step: int) -> int:
    """Fixed-time controller: cycles phase every 30 steps."""
    cycle_length = 60
    return 0 if (step % cycle_length) < 30 else 1

def select_action_max_pressure(state: Dict[str, Any]) -> int:
    """
    Max-Pressure / Queue-Greedy Controller for 2x2 grid.
    Compares halting vehicle queues on North-South approaches vs East-West approaches.
    Returns 0 for North-South green, 1 for East-West green.
    """
    ns_queue = 0
    ew_queue = 0
    for lane_id, queue in state["lane_queues"].items():
        if any(marker in lane_id for marker in ["top", "bottom", "A0A1", "A1A0", "B0B1", "B1B0"]):
            ns_queue += queue
        else:
            ew_queue += queue

    return 0 if ns_queue >= ew_queue else 1

def select_action_custom_rl(tls_id: str, state: Dict[str, Any]) -> int:
    """Placeholder for Multi-Agent Reinforcement Learning policy."""
    return select_action_max_pressure(state)


def main():
    parser = argparse.ArgumentParser(description="2x2 SUMO Multi-Agent Starter Simulation")
    parser.add_argument("--gui", action="store_true", help="Launch SUMO graphical interface (sumo-gui)")
    parser.add_argument("--steps", type=int, default=1000, help="Number of simulation steps (seconds)")
    parser.add_argument("--delay", type=int, default=50, help="Animation delay per step in ms (for GUI view)")
    parser.add_argument("--mode", choices=["sumo_default", "fixed", "max_pressure", "custom"],
                        default="max_pressure", help="Traffic light controller policy")
    parser.add_argument("--cfg", default="grid2x2.sumocfg", help="SUMO configuration file path")
    parser.add_argument("--out", default="simulation_metrics.csv", help="Output metrics CSV file")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(script_dir, args.cfg)

    env = MultiAgentEnvironment(cfg_path, use_gui=args.gui, delay_ms=args.delay)
    env.start()

    try:
        for s in range(args.steps):
            states = env.get_states()
            actions = {}

            if args.mode != "sumo_default":
                for tls_id, state in states.items():
                    if args.mode == "fixed":
                        actions[tls_id] = select_action_fixed(tls_id, s)
                    elif args.mode == "max_pressure":
                        actions[tls_id] = select_action_max_pressure(state)
                    elif args.mode == "custom":
                        actions[tls_id] = select_action_custom_rl(tls_id, state)
                
                env.apply_actions(actions)

            metrics = env.step()

            if (s + 1) % 50 == 0:
                print(f"[Step {s+1:4d}/{args.steps}] Active: {metrics['active_vehicles']:3d} veh | "
                      f"Avg Speed: {metrics['avg_speed_m_s']:4.1f} m/s | "
                      f"Waiting Time: {metrics['total_waiting_time_s']:6.1f} s")

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    finally:
        env.close(output_csv=args.out)

if __name__ == "__main__":
    main()
