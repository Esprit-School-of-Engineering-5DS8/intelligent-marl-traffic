"""
baselines/fixed_time.py
Fixed-time traffic signal controller (F2 reference baseline).

Cycles deterministically between North-South and East-West green phases
according to a preset cycle length and green-split ratio.
Supports phase offset for arterial coordination.
"""

from typing import Dict, Any
from agents.base_agent import BaseTrafficAgent


class FixedTimeAgent(BaseTrafficAgent):
    """
    Fixed-time signal controller.
    Runs a rigid, pre-timed schedule independent of real-time queue states.
    """

    def __init__(
        self,
        tls_id: str,
        cycle_length: int = 60,
        green_split: float = 0.5,
        offset: int = 0,
    ):
        """
        Args:
            tls_id: Traffic light junction ID.
            cycle_length: Total cycle length in simulation seconds (default 60s).
            green_split: Fraction of cycle allocated to phase 0 (NS). Default 0.5 (50/50).
            offset: Time shift in seconds relative to master clock (for Green Wave coordination).
        """
        super().__init__(tls_id)
        self.cycle_length = max(10, cycle_length)
        self.green_split = min(0.9, max(0.1, green_split))
        self.offset = offset
        self.phase0_duration = int(self.cycle_length * self.green_split)

    def select_action(self, state: Dict[str, Any]) -> int:
        """
        Returns:
            0: North-South Green
            1: East-West Green
        """
        time_step = state.get("time_in_phase", 0)
        # Global simulation step from state if available, or track locally
        sim_step = state.get("sim_step", None)
        if sim_step is None:
            # Fallback to local step tracking
            if not hasattr(self, "_local_step"):
                self._local_step = 0
            current_time = self._local_step + self.offset
            self._local_step += 1
        else:
            current_time = sim_step + self.offset

        cycle_pos = current_time % self.cycle_length
        return 0 if cycle_pos < self.phase0_duration else 1
