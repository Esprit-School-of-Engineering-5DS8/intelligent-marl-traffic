"""
environment/multi_agent_env.py
Standardized Multi-Agent Reinforcement Learning (MARL) Environment for SUMO.
Complies with PettingZoo ParallelEnv and Gymnasium APIs.

Author: Hazem Mrad (Simulation & Environment Lead)
Course: Advanced Data Science Project - Esprit (5DS8)
Repository: intelligent-marl-traffic
"""

import os
import sys
import csv
import numpy as np
from typing import Dict, List, Any, Optional, Tuple

# SUMO_HOME resolution
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
    import sumolib
except ImportError as err:
    raise ImportError(f"TraCI/sumolib not found. Ensure SUMO_HOME is set: {err}")

import gymnasium
from gymnasium import spaces
from pettingzoo import ParallelEnv


class SumoTLSController:
    """
    Internal controller tracking signal state, minimum green enforcement,
    and yellow clearance transitions for a single traffic light junction.
    """

    def __init__(
        self,
        tls_id: str,
        incoming_lanes: List[str],
        green_phases: Optional[List[int]] = None,
        yellow_phases: Optional[Dict[int, int]] = None,
        min_green: int = 10,
        yellow_time: int = 3,
    ):
        self.tls_id = tls_id
        self.incoming_lanes = incoming_lanes
        self.min_green = min_green
        self.yellow_time = yellow_time

        # Green and yellow phase setup
        self.green_phases = green_phases if green_phases is not None else [0, 2]
        self.yellow_phases = yellow_phases if yellow_phases is not None else {0: 1, 2: 3}

        self.current_phase = self.green_phases[0]
        self.target_phase = self.green_phases[0]
        self.time_in_phase = 0
        self.is_yellow = False

    def reset(self):
        self.current_phase = self.green_phases[0]
        self.target_phase = self.green_phases[0]
        self.time_in_phase = 0
        self.is_yellow = False
        try:
            traci.trafficlight.setPhase(self.tls_id, self.current_phase)
        except Exception:
            pass

    def apply_action(self, action: int):
        """
        Processes discrete action (index into green_phases).
        Guarantees safety clearance via yellow transitions and minimum green times.
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


class SumoMARLEnv(ParallelEnv):
    """
    PettingZoo-compliant Parallel Environment for multi-intersection SUMO control.

    Key Features:
    - ParallelEnv API: step(actions_dict) -> (obs, rewards, terminations, truncations, infos)
    - Vectorized observation spaces for RL policies (DQN, PPO, MAPPO).
    - Multi-objective reward structure (delay, queue, emissions, pedestrian wait).
    - Automatic yellow clearance & minimum green safety enforcement.
    - Global system KPI logging for evaluation benchmarks.
    """

    metadata = {"render_modes": ["human", "none"], "name": "sumo_marl_v1"}

    def __init__(
        self,
        sumocfg_path: str,
        use_gui: bool = False,
        step_length: float = 1.0,
        max_steps: int = 1000,
        min_green: int = 10,
        yellow_time: int = 3,
        reward_weights: Optional[Dict[str, float]] = None,
        delay_ms: int = 0,
    ):
        super().__init__()
        self.sumocfg_path = os.path.abspath(sumocfg_path)
        self.use_gui = use_gui
        self.step_length = step_length
        self.max_steps = max_steps
        self.min_green = min_green
        self.yellow_time = yellow_time
        self.delay_ms = delay_ms

        # Reward weights (Configurable for multi-objective optimization)
        # Default: penalties on waiting time and queue length
        self.reward_weights = {
            "waiting_time": -0.01,
            "queue": -0.2,
            "co2": 0.0,
            "pedestrian": 0.0,
            "emergency": 0.0,
        }
        if reward_weights:
            self.reward_weights.update(reward_weights)

        # Simulation state
        self.step_count = 0
        self.is_running = False
        self.history: List[Dict[str, Any]] = []

        # Interrogate network to configure agents and spaces
        self.controllers: Dict[str, SumoTLSController] = {}
        self.incoming_lanes_map: Dict[str, List[str]] = {}
        self._discover_network_layout()

        # PettingZoo agent lists
        self.possible_agents: List[str] = sorted(list(self.incoming_lanes_map.keys()))
        self.agents: List[str] = list(self.possible_agents)

        # Define Gym spaces per agent
        self.observation_spaces: Dict[str, spaces.Box] = {}
        self.action_spaces: Dict[str, spaces.Discrete] = {}
        self._build_spaces()

    def _discover_network_layout(self):
        """Temporarily boots SUMO to discover TLS IDs and incoming lanes."""
        sumo_bin = sumolib.checkBinary("sumo")
        cmd = [sumo_bin, "-c", self.sumocfg_path, "--no-warnings", "true"]
        traci.start(cmd)
        tls_ids = sorted(list(traci.trafficlight.getIDList()))

        for tls_id in tls_ids:
            lanes = traci.trafficlight.getControlledLanes(tls_id)
            # Filter internal junction lanes (starting with ':')
            incoming = sorted(list(set(l for l in lanes if not l.startswith(":"))))
            self.incoming_lanes_map[tls_id] = incoming

            # Read phase definitions
            logics = traci.trafficlight.getAllProgramLogics(tls_id)
            green_phases = [0, 2]
            yellow_phases = {0: 1, 2: 3}
            if logics and len(logics[0].phases) >= 4:
                phases = logics[0].phases
                greens = [i for i, p in enumerate(phases) if "G" in p.state or "g" in p.state]
                if len(greens) >= 2:
                    green_phases = greens[:2]
                    yellow_phases = {
                        green_phases[0]: min(green_phases[0] + 1, len(phases) - 1),
                        green_phases[1]: min(green_phases[1] + 1, len(phases) - 1),
                    }

            self.controllers[tls_id] = SumoTLSController(
                tls_id=tls_id,
                incoming_lanes=incoming,
                green_phases=green_phases,
                yellow_phases=yellow_phases,
                min_green=self.min_green,
                yellow_time=self.yellow_time,
            )

        traci.close()

    def _build_spaces(self):
        """Constructs observation and discrete action spaces for every agent."""
        for agent_id, lanes in self.incoming_lanes_map.items():
            ctrl = self.controllers[agent_id]
            # Observation vector:
            # For each lane (4 metrics): [queue, wait_time, veh_count, mean_speed]
            # Plus TLS status (3 metrics): [current_phase_idx, time_in_phase, is_yellow]
            obs_dim = (len(lanes) * 4) + 3
            self.observation_spaces[agent_id] = spaces.Box(
                low=0.0, high=np.inf, shape=(obs_dim,), dtype=np.float32
            )
            # Discrete actions: choose which green phase to serve
            self.action_spaces[agent_id] = spaces.Discrete(len(ctrl.green_phases))

    def observation_space(self, agent: str) -> spaces.Box:
        return self.observation_spaces[agent]

    def action_space(self, agent: str) -> spaces.Discrete:
        return self.action_spaces[agent]

    def _start_sumo(self):
        """Starts TraCI connection with GUI or headless mode."""
        if self.is_running:
            try:
                traci.close()
            except Exception:
                pass
            self.is_running = False

        binary_name = "sumo-gui" if self.use_gui else "sumo"
        sumo_bin = sumolib.checkBinary(binary_name)
        cmd = [
            sumo_bin,
            "-c", self.sumocfg_path,
            "--step-length", str(self.step_length),
            "--no-warnings", "true",
            "--quit-on-end", "true",
        ]
        if self.use_gui:
            cmd.extend(["--start", "true", "--delay", str(self.delay_ms)])

        traci.start(cmd)
        self.is_running = True

    def reset(
        self, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, Dict[str, Any]]]:
        """
        Resets simulation and controllers to step 0.
        Returns: (observations_dict, infos_dict)
        """
        self._start_sumo()
        self.step_count = 0
        self.history.clear()
        self.agents = list(self.possible_agents)

        for ctrl in self.controllers.values():
            ctrl.reset()

        obs = self._get_observations()
        infos = self._get_infos()
        return obs, infos

    def step(
        self, actions: Dict[str, int]
    ) -> Tuple[
        Dict[str, np.ndarray],
        Dict[str, float],
        Dict[str, bool],
        Dict[str, bool],
        Dict[str, Dict[str, Any]],
    ]:
        """
        Executes one joint action step across all agents.
        Returns: (observations, rewards, terminations, truncations, infos)
        """
        # 1. Dispatch actions to individual junction controllers
        for agent_id, action in actions.items():
            if agent_id in self.controllers:
                self.controllers[agent_id].apply_action(action)

        # 2. Advance SUMO simulation by one step
        traci.simulationStep()
        self.step_count += 1

        # 3. System-wide metric aggregation
        veh_ids = traci.vehicle.getIDList()
        n_vehs = len(veh_ids)
        total_wait = sum(traci.vehicle.getWaitingTime(v) for v in veh_ids)
        total_speed = sum(traci.vehicle.getSpeed(v) for v in veh_ids)
        total_co2 = sum(traci.vehicle.getCO2Emission(v) for v in veh_ids)
        total_fuel = sum(traci.vehicle.getFuelConsumption(v) for v in veh_ids)
        arrived = traci.simulation.getArrivedNumber()

        system_record = {
            "step": self.step_count,
            "active_vehicles": n_vehs,
            "arrived_vehicles": arrived,
            "avg_speed_m_s": round(total_speed / n_vehs, 2) if n_vehs > 0 else 0.0,
            "total_waiting_time_s": round(total_wait, 2),
            "co2_mg_s": round(total_co2, 2),
            "fuel_ml_s": round(total_fuel, 2),
        }
        self.history.append(system_record)

        # 4. Agent observations, rewards, and status
        obs = self._get_observations()
        rewards = self._compute_rewards()
        infos = self._get_infos(system_record=system_record)

        # Check termination & truncation
        is_truncated = self.step_count >= self.max_steps
        is_terminated = False  # SUMO runs until max_steps unless network crashes

        terminations = {agent: is_terminated for agent in self.agents}
        truncations = {agent: is_truncated for agent in self.agents}

        if is_truncated or is_terminated:
            self.agents = []

        return obs, rewards, terminations, truncations, infos

    def _get_observations(self) -> Dict[str, np.ndarray]:
        """Extracts numerical state vectors for all agents."""
        obs = {}
        for agent_id in self.possible_agents:
            lanes = self.incoming_lanes_map[agent_id]
            ctrl = self.controllers[agent_id]

            features = []
            for lane_id in lanes:
                halting = float(traci.lane.getLastStepHaltingNumber(lane_id))
                wait = float(traci.lane.getWaitingTime(lane_id))
                veh_count = float(traci.lane.getLastStepVehicleNumber(lane_id))
                speed = float(traci.lane.getLastStepMeanSpeed(lane_id))
                features.extend([halting, wait, veh_count, speed])

            phase_idx = float(ctrl.green_phases.index(ctrl.current_phase) if ctrl.current_phase in ctrl.green_phases else 0)
            time_in_phase = float(ctrl.time_in_phase)
            is_yellow = 1.0 if ctrl.is_yellow else 0.0
            features.extend([phase_idx, time_in_phase, is_yellow])

            obs[agent_id] = np.array(features, dtype=np.float32)
        return obs

    def _compute_rewards(self) -> Dict[str, float]:
        """Calculates multi-objective rewards per agent."""
        rewards = {}
        for agent_id in self.possible_agents:
            lanes = self.incoming_lanes_map[agent_id]
            total_queue = sum(traci.lane.getLastStepHaltingNumber(l) for l in lanes)
            total_wait = sum(traci.lane.getWaitingTime(l) for l in lanes)
            total_co2 = sum(traci.lane.getCO2Emission(l) for l in lanes)

            # Linear scalarization of reward objectives
            reward = (
                self.reward_weights["waiting_time"] * total_wait
                + self.reward_weights["queue"] * total_queue
                + self.reward_weights["co2"] * total_co2
            )
            rewards[agent_id] = float(reward)
        return rewards

    def _get_infos(self, system_record: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        """Provides rich metadata (raw lane statistics and system KPIs)."""
        infos = {}
        for agent_id in self.possible_agents:
            lanes = self.incoming_lanes_map[agent_id]
            ctrl = self.controllers[agent_id]
            lane_queues = {l: traci.lane.getLastStepHaltingNumber(l) for l in lanes}
            lane_waiting = {l: traci.lane.getWaitingTime(l) for l in lanes}
            lane_counts = {l: traci.lane.getLastStepVehicleNumber(l) for l in lanes}

            infos[agent_id] = {
                "tls_id": agent_id,
                "current_phase": ctrl.current_phase,
                "time_in_phase": ctrl.time_in_phase,
                "is_yellow": ctrl.is_yellow,
                "total_queue": sum(lane_queues.values()),
                "total_waiting_time": sum(lane_waiting.values()),
                "lane_queues": lane_queues,
                "lane_waiting": lane_waiting,
                "lane_counts": lane_counts,
            }

        if system_record:
            infos["__system__"] = system_record
        return infos

    def save_metrics(self, output_csv: str = "simulation_metrics.csv"):
        """Saves recorded simulation step metrics to CSV."""
        if self.history:
            with open(output_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(self.history[0].keys()))
                writer.writeheader()
                writer.writerows(self.history)
            print(f"[SumoMARLEnv] Performance log saved to: {output_csv}")

    def close(self, output_csv: Optional[str] = None):
        """Closes TraCI and optionally exports metrics."""
        if self.is_running:
            try:
                traci.close()
            except Exception:
                pass
            self.is_running = False
        if output_csv:
            self.save_metrics(output_csv)


# Backwards compatibility alias
MultiAgentEnv = SumoMARLEnv
