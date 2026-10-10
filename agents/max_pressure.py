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
        ns_queue, ew_queue = 0, 0
        for lane_id, queue in state.get("lane_queues", {}).items():
            # Heuristic: lanes with vertical IDs → NS, horizontal → EW
            if any(v in lane_id for v in ["A1", "A2", "B1", "B2", "C1", "C2"]):
                ns_queue += queue
            else:
                ew_queue += queue
        return 0 if ns_queue >= ew_queue else 1
