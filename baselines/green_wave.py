"""
baselines/green_wave.py
Green Wave arterial progression controller (F2 reference baseline).

Coordinates consecutive traffic lights along major corridors by applying
progression offsets calculated from intersection spacing and design speed:
    offset = distance / design_speed
Allows vehicle platoons to traverse consecutive green signals without stopping.
"""

from typing import Dict, Any
from agents.base_agent import BaseTrafficAgent


class GreenWaveAgent(BaseTrafficAgent):
    """
    Coordinated progression signal controller.
    Uses calculated offsets to create continuous green waves along the main corridor.
    """

    def __init__(
        self,
        tls_id: str,
        cycle_length: int = 60,
        green_split: float = 0.55,
        grid_spacing_m: float = 200.0,
        progression_speed_m_s: float = 13.89,  # 50 km/h
        corridor: str = "EW",  # 'EW' for East-West wave, 'NS' for North-South wave
    ):
        """
        Args:
            tls_id: Junction ID (e.g., 'A0', 'B0', 'C0').
            cycle_length: Common cycle length across all coordinated signals.
            green_split: Fraction of cycle allocated to the coordinated corridor.
            grid_spacing_m: Distance between adjacent intersections (default 200m).
            progression_speed_m_s: Desired platoon progression speed (default 13.89 m/s).
            corridor: 'EW' (East-West progression) or 'NS' (North-South progression).
        """
        super().__init__(tls_id)
        self.cycle_length = max(20, cycle_length)
        self.green_split = green_split
        self.corridor = corridor.upper()

        travel_time = grid_spacing_m / progression_speed_m_s

        # Derive column or row index from tls_id (e.g., 'A0' -> col A, row 0)
        col_letter = tls_id[0].upper() if len(tls_id) > 0 else 'A'
        row_num = int(tls_id[1]) if len(tls_id) > 1 and tls_id[1].isdigit() else 0
        col_idx = ord(col_letter) - ord('A')  # A=0, B=1, C=2

        # Compute offset along progression axis
        if self.corridor == "EW":
            # East-West wave: offset progresses across columns (A -> B -> C)
            self.offset = int(col_idx * travel_time)
            # Action 1 = EW green
            self.coordinated_action = 1
        else:
            # North-South wave: offset progresses across rows (0 -> 1 -> 2)
            self.offset = int(row_num * travel_time)
            # Action 0 = NS green
            self.coordinated_action = 0

        self.coordinated_duration = int(self.cycle_length * self.green_split)

    def select_action(self, state: Dict[str, Any]) -> int:
        sim_step = state.get("sim_step", None)
        if sim_step is None:
            if not hasattr(self, "_local_step"):
                self._local_step = 0
            current_time = self._local_step + self.offset
            self._local_step += 1
        else:
            current_time = sim_step + self.offset

        cycle_pos = current_time % self.cycle_length

        if cycle_pos < self.coordinated_duration:
            return self.coordinated_action
        else:
            return 1 - self.coordinated_action
