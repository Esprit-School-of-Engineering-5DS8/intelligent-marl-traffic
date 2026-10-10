"""
agents/max_pressure.py
Max-Pressure / Queue-Greedy adaptive controller.
Gives green to the direction with the most queued vehicles.
"""
from agents.base_agent import BaseTrafficAgent
from typing import Dict, Any


class MaxPressureAgent(BaseTrafficAgent):
    """Decentralized adaptive pressure-based heuristic (no learning required)."""

    def select_action(self, state: Dict[str, Any]) -> int:
        # Lane groups come from the TLS program via environment.topology —
        # never from lane-ID string matching.
        ns_lanes = state["ns_lanes"]
        ew_lanes = state["ew_lanes"]
        lane_queues = state["lane_queues"]
        ns_queue = sum(queue for lane, queue in lane_queues.items() if lane in ns_lanes)
        ew_queue = sum(queue for lane, queue in lane_queues.items() if lane in ew_lanes)
        return 0 if ns_queue >= ew_queue else 1
