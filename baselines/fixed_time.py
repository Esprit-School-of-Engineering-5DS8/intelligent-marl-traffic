"""
baselines/fixed_time.py
Fixed-time cycle baseline controller (F2).
Cycles between NS and EW green every `cycle_length / 2` steps.
"""
from agents.base_agent import BaseTrafficAgent
from typing import Dict, Any


class FixedTimeAgent(BaseTrafficAgent):
    """Simple fixed-time signal controller — reference baseline."""

    def __init__(self, tls_id: str, cycle_length: int = 60):
        super().__init__(tls_id)
        self.cycle_length = cycle_length
        self._step = 0

    def select_action(self, state: Dict[str, Any]) -> int:
        action = 0 if (self._step % self.cycle_length) < (self.cycle_length // 2) else 1
        self._step += 1
        return action
