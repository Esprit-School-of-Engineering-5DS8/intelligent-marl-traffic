"""
agents/max_pressure.py
Max-Pressure / Queue-Greedy adaptive controller.
Gives green to the green phase group with the most queued vehicles.

Groups come from the TLS program via `environment.topology` (never from
lane-ID string matching). Grids have one group per axis (identical to the
binary NS/EW policy); N-phase real networks (e.g. MoST Monaco) expose up to
three groups so protected-turn / one-way phases are served too.
"""
from agents.base_agent import BaseTrafficAgent
from typing import Dict, Sequence, Any


class MaxPressureAgent(BaseTrafficAgent):
    """Decentralized adaptive pressure-based heuristic (no learning required)."""

    def select_action(self, state: Dict[str, Any]) -> int:
        groups: Sequence[frozenset] = state.get("group_lanes")
        if not groups:
            # Legacy/unit-test states carry only the binary NS/EW lane sets.
            groups = (state["ns_lanes"], state["ew_lanes"])
        lane_queues = state["lane_queues"]

        best_action = 0
        best_queue = -1
        for action, lanes in enumerate(groups):
            queue = sum(lane_queues.get(lane, 0) or 0 for lane in lanes)
            if queue > best_queue:
                best_action, best_queue = action, queue
        return best_action
