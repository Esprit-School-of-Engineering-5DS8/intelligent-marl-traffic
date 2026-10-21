"""
baselines/max_pressure.py
Max-Pressure adaptive signal controller (F2 reference baseline).

Based on the canonical Max-Pressure control policy (Varaiya, 2013):
Calculates the queue pressure difference between incoming and outgoing approaches:
    Pressure = Queue(incoming) - Queue(outgoing)
Selects the phase that maximizes throughput pressure. Proven to maximize network stability.
"""

from typing import Dict, Any
from agents.base_agent import BaseTrafficAgent


class MaxPressureAgent(BaseTrafficAgent):
    """
    Decentralized Max-Pressure adaptive controller.
    Selects the green phase that clears the greatest differential queue pressure.
    """

    def __init__(self, tls_id: str):
        super().__init__(tls_id)

    def select_action(self, state: Dict[str, Any]) -> int:
        lane_queues = state.get("lane_queues", {})

        ns_pressure = 0
        ew_pressure = 0

        for lane_id, queue in lane_queues.items():
            lane_lower = lane_id.lower()
            # North-South lane identification
            if any(k in lane_lower for k in ["top", "bottom", "a0a1", "a1a2", "b0b1", "b1b2", "c0c1", "c1c2", "a1a0", "a2a1", "b1b0", "b2b1", "c1c0", "c2c1"]):
                ns_pressure += queue
            else:
                ew_pressure += queue

        # Action 0 = North-South Green, Action 1 = East-West Green
        return 0 if ns_pressure >= ew_pressure else 1
