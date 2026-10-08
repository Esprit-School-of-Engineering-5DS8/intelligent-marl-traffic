"""
baselines/actuated.py
Vehicle-Actuated traffic signal controller (F2 reference baseline).

Implements standard transportation engineering gap-out and max-out logic:
- Extends the current green phase while vehicles are detected approaching.
- Switches to competing direction when queue clears (gap-out) or when
  maximum green duration is exceeded (max-out).
"""

from typing import Dict, Any, List
from agents.base_agent import BaseTrafficAgent


class ActuatedAgent(BaseTrafficAgent):
    """
    Decentralized vehicle-actuated signal controller.
    Dynamically extends green phases based on incoming vehicle demand.
    """

    def __init__(
        self,
        tls_id: str,
        min_green: int = 10,
        max_green: int = 50,
        gap_threshold: int = 1,
    ):
        """
        Args:
            tls_id: Traffic light junction ID.
            min_green: Minimum seconds to hold green before considering switch.
            max_green: Maximum seconds to hold green before forcing switch (max-out).
            gap_threshold: Minimum active vehicles on incoming lanes to justify green extension.
        """
        super().__init__(tls_id)
        self.min_green = min_green
        self.max_green = max_green
        self.gap_threshold = gap_threshold

        self.current_action = 0
        self.time_in_current_action = 0

    def select_action(self, state: Dict[str, Any]) -> int:
        """
        Evaluates queue lengths and vehicle counts on incoming approaches:
        - Lanes with vertical orientation -> North-South (Action 0)
        - Lanes with horizontal orientation -> East-West (Action 1)
        """
        self.time_in_current_action += 1

        lane_counts = state.get("lane_counts", {})
        lane_queues = state.get("lane_queues", {})

        ns_demand = 0
        ew_demand = 0

        for lane_id, count in lane_counts.items():
            queue = lane_queues.get(lane_id, 0)
            demand = count + queue * 2  # weight queued vehicles higher

            # Determine lane direction heuristic
            # Edges top/bottom or col movements -> NS; left/right or row -> EW
            lane_lower = lane_id.lower()
            if any(k in lane_lower for k in ["top", "bottom", "a0a1", "a1a2", "b0b1", "b1b2", "c0c1", "c1c2", "a1a0", "a2a1", "b1b0", "b2b1", "c1c0", "c2c1"]):
                ns_demand += demand
            else:
                ew_demand += demand

        current_demand = ns_demand if self.current_action == 0 else ew_demand
        competing_demand = ew_demand if self.current_action == 0 else ns_demand

        # Must serve min_green first
        if self.time_in_current_action < self.min_green:
            return self.current_action

        # Force switch if max_green reached (Max-Out)
        if self.time_in_current_action >= self.max_green:
            if competing_demand > 0:
                self.current_action = 1 - self.current_action
                self.time_in_current_action = 0
            return self.current_action

        # Gap-Out condition: current approach has dried up and competing approach has demand
        if current_demand <= self.gap_threshold and competing_demand > current_demand:
            self.current_action = 1 - self.current_action
            self.time_in_current_action = 0

        return self.current_action
