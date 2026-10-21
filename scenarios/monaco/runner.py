#!/usr/bin/env python3
"""
runner.py
Multi-Agent Traffic Light Control Runner for Monaco MoST Scenario (Phase 3).
Real-world OSM network — Principality of Monaco.

Compatible with both WSL Ubuntu and native Windows environments.

Features:
- Connects to SUMO via TraCI (GUI or headless).
- Multi-Agent structure: 12 real signalized junctions from the MoST dataset.
- Pre-built controllers:
  * 'sumo_default' : SUMO default actuated/pre-timed logic (no Python override)
  * 'fixed'        : Fixed-time cycling (30s NS / 30s EW per phase)
  * 'max_pressure' : Decentralized adaptive pressure-based heuristic
  * 'custom'       : Modular placeholder ready for RL agents
- Real-time KPI tracking: waiting time, queue lengths, average speed,
  throughput, CO2 emissions, fuel consumption.
- Exports metrics to CSV for analysis and visualization.

Network: Monaco SUMO Traffic (MoST) Scenario
Citation: L. Codeca, J. Härri, VNC 2017.
Author (runner): Hazem Mrad — Simulation & Environment Lead (5DS8)
"""

import os
import sys
import csv
import argparse
from typing import Dict, List, Any

# ── SUMO_HOME resolution ────────────────────────────────────────────────────
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
    from traci.exceptions import FatalTraCIError
except ImportError:
    print(f"Error: Unable to import TraCI. SUMO_HOME='{sumo_home}'", file=sys.stderr)
    print("Please ensure SUMO is installed and SUMO_HOME/tools is accessible.", file=sys.stderr)
    sys.exit(1)

# ── Known controlled TLS IDs in the MoST Monaco network ────────────────────
# These are the 12 real signalized junctions. Discovered at runtime via TraCI,
# but listed here for reference.
MONACO_TLS_IDS = [
    "134872",
    "cluster_135794_135910",
    "cluster_21728904_21728905",
    "cluster_21728907_21728908",
    "cluster_21728924_21728925",
    "cluster_21728930_21728931",
    "cluster_21729183_21729184",
    "cluster_21729185_21729186",
    "cluster_21729189_21729190",
    "cluster_21729193_21729194",
    "cluster_21729196_21729197",
    "cluster_21729200_21729201",
]


class TrafficLightAgent:
    """
    Autonomous agent controlling one real-world signalized junction in Monaco.
    Handles phase transitions, yellow clearance, and minimum green enforcement.

    Unlike the grid scenarios, Monaco TLS have variable numbers of phases
    (not a simple 2-phase NS/EW), so we work with phase indices generically.
    """

    def __init__(self, tls_id: str, min_green: int = 10, yellow_time: int = 3):
        self.tls_id = tls_id
        self.min_green = min_green
        self.yellow_time = yellow_time

        # Query the full phase definition from the network
        logic = traci.trafficlight.getAllProgramLogics(tls_id)
        if logic:
            phases = logic[0].phases
            # Separate green phases (contain 'G' or 'g') from yellow/red
            self.green_phases = [
                i for i, p in enumerate(phases)
                if "G" in p.state or "g" in p.state
                and "y" not in p.state.lower()
            ]
            self.yellow_phase_map = {
                i: i + 1 for i in self.green_phases
                if (i + 1) < len(phases) and "y" in phases[i + 1].state.lower()
            }
        else:
            # Fallback: assume 4-phase standard
            self.green_phases = [0, 2]
            self.yellow_phase_map = {0: 1, 2: 3}

        self.current_phase = self.green_phases[0] if self.green_phases else 0
        self.target_phase = self.current_phase
        self.time_in_phase = 0
        self.is_yellow = False

        # Query incoming lanes
        self.incoming_lanes = list(set(traci.trafficlight.getControlledLanes(tls_id)))

    def get_state(self) -> Dict[str, Any]:
        """
        Extracts per-agent observations:
        - Queue length (halting vehicles, speed < 0.1 m/s)
        - Vehicle counts and waiting times per incoming lane
        - Active phase & time in phase
        """
        lane_queues = {}
        lane_waiting = {}
        lane_counts = {}
        total_queue = 0
        total_waiting = 0.0

        for lane_id in self.incoming_lanes:
            halting = traci.lane.getLastStepHaltingNumber(lane_id)
            waiting = traci.lane.getWaitingTime(lane_id)
            count = traci.lane.getLastStepVehicleNumber(lane_id)

            lane_queues[lane_id] = halting
            lane_waiting[lane_id] = waiting
            lane_counts[lane_id] = count

            total_queue += halting
            total_waiting += waiting

        return {
            "tls_id": self.tls_id,
            "current_phase": self.current_phase,
            "time_in_phase": self.time_in_phase,
            "is_yellow": self.is_yellow,
            "total_queue": total_queue,
            "total_waiting_time": total_waiting,
            "lane_queues": lane_queues,
            "lane_waiting": lane_waiting,
            "lane_counts": lane_counts,
        }

    def compute_reward(self, state: Dict[str, Any]) -> float:
        """Standard MARL reward: penalise waiting time and queue buildup."""
        return -(state["total_waiting_time"] * 0.1 + state["total_queue"] * 1.0)

    def step_control(self, action: int):
        """
        Applies action (index into self.green_phases) with safe yellow transitions.
        action=0 → first green phase, action=1 → second green phase, etc.
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
                yellow = self.yellow_phase_map.get(self.current_phase)
                self.is_yellow = True
                self.target_phase = desired_green
                self.time_in_phase = 0
                if yellow is not None:
                    traci.trafficlight.setPhase(self.tls_id, yellow)
                else:
                    # No yellow phase defined — switch directly
                    self.is_yellow = False
                    self.current_phase = desired_green
                    traci.trafficlight.setPhase(self.tls_id, desired_green)


class MonacoMultiAgentEnvironment:
    """
    Manages the Monaco MoST multi-agent environment.
    Handles SUMO launch, agent discovery, step loop, and KPI logging.
    """

    def __init__(
        self,
        sumocfg_path: str,
        use_gui: bool = False,
        step_length: float = 0.25,
        delay_ms: int = 50,
        begin_time: int = 28800,   # 08:00 AM — morning peak hour
    ):
        self.sumocfg_path = sumocfg_path
        self.use_gui = use_gui
        self.step_length = step_length
        self.delay_ms = delay_ms
        self.begin_time = begin_time
        self.agents: Dict[str, TrafficLightAgent] = {}
        self.step_count = 0
        self.history: List[Dict[str, Any]] = []

    def start(self):
        """Launches SUMO and initializes agents for all discovered TLS."""
        binary_name = "sumo-gui" if self.use_gui else "sumo"
        try:
            import sumolib
            binary = sumolib.checkBinary(binary_name)
        except Exception:
            binary = f"{binary_name}.exe" if sys.platform == "win32" else binary_name

        sumo_cmd = [
            binary,
            "-c", self.sumocfg_path,
            "--step-length", str(self.step_length),
            "--no-warnings", "true",
            "--quit-on-end", "true",
            "--ignore-route-errors", "true",
        ]

        if self.use_gui:
            sumo_cmd.extend(["--start", "true", "--delay", str(self.delay_ms)])

        print(f"[Monaco] Starting simulation → {binary}")
        print(f"[Monaco] Config: {self.sumocfg_path}")
        traci.start(sumo_cmd)

        tls_ids = traci.trafficlight.getIDList()
        print(f"[Monaco] Discovered {len(tls_ids)} traffic lights: {list(tls_ids)}")

        for tls_id in sorted(tls_ids):
            try:
                self.agents[tls_id] = TrafficLightAgent(tls_id)
            except Exception as e:
                print(f"[Monaco] Warning: Could not init agent for {tls_id}: {e}")

        print(f"[Monaco] {len(self.agents)} agents initialized.\n")

    def get_states(self) -> Dict[str, Dict[str, Any]]:
        """Collects observations from all agents."""
        return {tls_id: agent.get_state() for tls_id, agent in self.agents.items()}

    def apply_actions(self, actions: Dict[str, int]):
        """Dispatches actions to all agents."""
        for tls_id, action in actions.items():
            if tls_id in self.agents:
                self.agents[tls_id].step_control(action)

    def step(self) -> Dict[str, Any]:
        """Advances simulation by one step and records system-wide KPIs."""
        traci.simulationStep()
        self.step_count += 1

        veh_ids = traci.vehicle.getIDList()
        num_vehicles = len(veh_ids)

        total_waiting = 0.0
        total_speed = 0.0
        total_co2 = 0.0
        total_fuel = 0.0
        ev_waiting = 0.0
        ped_waiting = 0.0

        for v in veh_ids:
            w = traci.vehicle.getWaitingTime(v)
            total_waiting += w
            total_speed += traci.vehicle.getSpeed(v)
            total_co2 += traci.vehicle.getCO2Emission(v)
            total_fuel += traci.vehicle.getFuelConsumption(v)
            # Emergency vehicle detection by type prefix
            vtype = traci.vehicle.getTypeID(v)
            if "emergency" in vtype.lower() or "rescue" in vtype.lower():
                ev_waiting += w

        # Pedestrian waiting time (persons)
        try:
            for person_id in traci.person.getIDList():
                ped_waiting += traci.person.getWaitingTime(person_id)
        except Exception:
            pass

        avg_speed = (total_speed / num_vehicles) if num_vehicles > 0 else 0.0
        arrived = traci.simulation.getArrivedNumber()

        record = {
            "step": self.step_count,
            "sim_time_s": round(self.begin_time + self.step_count * self.step_length, 2),
            "active_vehicles": num_vehicles,
            "arrived_vehicles": arrived,
            "avg_speed_m_s": round(avg_speed, 3),
            "total_waiting_time_s": round(total_waiting, 2),
            "ev_waiting_time_s": round(ev_waiting, 2),
            "pedestrian_waiting_time_s": round(ped_waiting, 2),
            "co2_mg_s": round(total_co2, 2),
            "fuel_ml_s": round(total_fuel, 2),
        }
        self.history.append(record)
        return record

    def close(self, output_csv: str = "monaco_metrics.csv"):
        """Closes TraCI and saves KPI history to CSV."""
        try:
            traci.close()
        except Exception:
            pass

        print(f"\n[Monaco] Simulation complete — {self.step_count} steps.")

        if self.history:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            csv_path = os.path.join(script_dir, output_csv)
            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(self.history[0].keys()))
                writer.writeheader()
                writer.writerows(self.history)
            print(f"[Monaco] Metrics saved → {csv_path}")

            active_steps = [r for r in self.history if r["active_vehicles"] > 0]
            avg_speeds = [r["avg_speed_m_s"] for r in active_steps]
            total_arrived = sum(r["arrived_vehicles"] for r in self.history)
            mean_wait = sum(r["total_waiting_time_s"] for r in self.history) / len(self.history)
            mean_co2 = sum(r["co2_mg_s"] for r in self.history) / len(self.history)

            print("=" * 62)
            print("       MONACO SIMULATION SUMMARY (Phase 3 — MoST)")
            print("=" * 62)
            print(f"  Total Steps Simulated  : {self.step_count}")
            print(f"  Total Vehicles Arrived : {total_arrived}")
            if avg_speeds:
                print(f"  Network Mean Speed     : {sum(avg_speeds)/len(avg_speeds):.3f} m/s")
            print(f"  Mean Step Waiting Time : {mean_wait:.2f} s")
            print(f"  Mean CO2 Emission      : {mean_co2:.2f} mg/s")
            print("=" * 62)


# ── Controllers ─────────────────────────────────────────────────────────────

def select_action_fixed(step: int, num_phases: int = 2) -> int:
    """Fixed-time: cycle through phases every 30 steps."""
    cycle_length = 30 * num_phases
    phase_duration = 30
    return (step % cycle_length) // phase_duration


def select_action_max_pressure(state: Dict[str, Any]) -> int:
    """
    Generic Max-Pressure for real-world network.
    Sums all lane queues and selects the phase index with most pressure.
    Since Monaco has variable phase counts, we split lanes into two groups
    (first half vs second half of incoming lanes) as a proxy for the two
    dominant movement directions.
    """
    lanes = list(state["lane_queues"].items())
    if not lanes:
        return 0
    mid = len(lanes) // 2
    group_a = sum(q for _, q in lanes[:mid])
    group_b = sum(q for _, q in lanes[mid:])
    return 0 if group_a >= group_b else 1


def select_action_custom_rl(tls_id: str, state: Dict[str, Any]) -> int:
    """Placeholder — plug your DQN / PPO policy here."""
    return select_action_max_pressure(state)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Monaco MoST Multi-Agent Traffic Simulation (Phase 3)"
    )
    parser.add_argument("--gui", action="store_true",
                        help="Launch SUMO graphical interface (sumo-gui)")
    parser.add_argument("--steps", type=int, default=2000,
                        help="Number of simulation steps (default: 2000 × 0.25s = 500s)")
    parser.add_argument("--delay", type=int, default=50,
                        help="GUI animation delay per step in ms")
    parser.add_argument("--mode",
                        choices=["sumo_default", "fixed", "max_pressure", "custom"],
                        default="max_pressure",
                        help="Traffic light controller policy")
    parser.add_argument("--cfg", default="most.traci.sumocfg",
                        help="SUMO configuration file (default: most.traci.sumocfg)")
    parser.add_argument("--out", default="monaco_metrics.csv",
                        help="Output metrics CSV filename")
    parser.add_argument("--begin", type=int, default=28800,
                        help="Simulation begin time in seconds (default: 28800 = 08:00 AM peak). "
                             "Other useful values: 25200=07:00, 57600=16:00 (evening peak)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(script_dir, args.cfg)

    if not os.path.exists(cfg_path):
        print(f"[Monaco] ERROR: Config file not found: {cfg_path}", file=sys.stderr)
        sys.exit(1)

    env = MonacoMultiAgentEnvironment(
        cfg_path,
        use_gui=args.gui,
        delay_ms=args.delay,
        begin_time=args.begin,
    )
    env.start()

    print_every = max(1, args.steps // 20)   # ~20 progress lines

    try:
        for s in range(args.steps):
            states = env.get_states()
            actions: Dict[str, int] = {}

            if args.mode != "sumo_default":
                for tls_id, state in states.items():
                    agent = env.agents[tls_id]
                    n_phases = len(agent.green_phases)

                    if args.mode == "fixed":
                        actions[tls_id] = select_action_fixed(s, n_phases)
                    elif args.mode == "max_pressure":
                        actions[tls_id] = select_action_max_pressure(state)
                    elif args.mode == "custom":
                        actions[tls_id] = select_action_custom_rl(tls_id, state)

                env.apply_actions(actions)

            metrics = env.step()

            if (s + 1) % print_every == 0:
                print(
                    f"[Step {s+1:5d}/{args.steps}] "
                    f"Vehicles: {metrics['active_vehicles']:4d} | "
                    f"Speed: {metrics['avg_speed_m_s']:5.2f} m/s | "
                    f"Wait: {metrics['total_waiting_time_s']:8.1f} s | "
                    f"Arrived: {metrics['arrived_vehicles']:4d}"
                )

    except KeyboardInterrupt:
        print("\n[Monaco] Simulation interrupted by user (Ctrl+C).")
    except FatalTraCIError:
        print("\n[Monaco] SUMO GUI was closed — ending simulation gracefully.")
    finally:
        env.close(output_csv=args.out)


if __name__ == "__main__":
    main()
