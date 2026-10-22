"""Per-agent reward.

    r = r_base - l_co2 * CO2 / n_co2 - l_ev * EVwait / n_ev - l_ped * PEDwait / n_ped

The base term is chosen by ``base``:

* ``wait`` (default): r_base = -(W_t - W_{t-1}) / n_wait, where ``W`` is the (optionally
  person-weighted) waiting time accumulated by the vehicles currently on the
  intersection's incoming lanes, counting only the waiting done since they entered those
  lanes, so an agent is not charged for delay caused upstream;
* ``queue``: r_base = -(halting vehicles on the incoming lanes) / n_queue, the integral of
  which is the total waiting time;
* ``pressure``: r_base = -|sum over movements of (vehicles upstream - downstream)| /
  n_pressure, the reward of PressLight (Wei et al. 2019).

The ``n_*`` constants come from baseline runs (``cotraffic calibrate``) so that each term
is of order 1.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cotraffic.envs.intersection import Intersection


def vehicle_kind(veh_id: str) -> str:
    """Vehicle class from the id prefixes used by the demand generator."""
    if veh_id.startswith("bus_"):
        return "bus"
    if veh_id.startswith("ev_"):
        return "emergency"
    if veh_id.startswith("incident_"):
        return "incident"
    return "passenger"


BASE_TERMS = ("wait", "queue", "pressure")
TERMS = ("wait", "queue", "pressure", "co2", "ev", "ped")


@dataclass(frozen=True)
class RewardConfig:
    base: str = "wait"
    person_weighted: bool = False
    co2: float = 0.0
    ev: float = 0.0
    ped: float = 0.0
    clip: float = 5.0

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> RewardConfig:
        d = dict(d or {})
        unknown = set(d) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown reward options: {sorted(unknown)}")
        if d.get("base", "wait") not in BASE_TERMS:
            raise ValueError(f"reward base must be one of {BASE_TERMS}")
        return cls(**d)


@dataclass
class _AgentState:
    entry_wait: dict[str, float] = field(default_factory=dict)
    last_wait: dict[str, float] = field(default_factory=dict)
    total: float = 0.0


class RewardComputer:
    def __init__(
        self, cfg: RewardConfig, occupancy: Mapping[str, float], norm: Mapping[str, float]
    ):
        self.cfg = cfg
        self.occupancy = {k: float(v) for k, v in occupancy.items()}
        self.occupancy["incident"] = 0.0
        self.norm = {k: max(1e-9, float(norm.get(k, 1.0))) for k in TERMS}
        self.state: dict[str, _AgentState] = {}

    def reset(self) -> None:
        self.state = {}

    def _weight(self, veh_id: str) -> float:
        kind = vehicle_kind(veh_id)
        if kind == "incident":
            return 0.0
        return self.occupancy[kind] if self.cfg.person_weighted else 1.0

    def raw_terms(
        self,
        conn,
        inter: Intersection,
        co2_mg: float,
        ped_waiting_s: float,
        counts: Mapping[str, float],
    ) -> dict[str, float]:
        """Unscaled reward components for one decision interval (all base terms)."""
        st = self.state.setdefault(inter.id, _AgentState())
        entry, new_entry, last, new_last = st.entry_wait, {}, st.last_wait, {}
        total, ev_wait, queue = 0.0, 0.0, 0.0
        for lane in inter.in_lanes:
            vehicles = conn.lane.getLastStepVehicleIDs(lane)
            if not self.cfg.person_weighted:
                queue += conn.lane.getLastStepHaltingNumber(lane)
            for veh in vehicles:
                acc = conn.vehicle.getAccumulatedWaitingTime(veh)
                base = entry.get(veh, acc)
                new_entry[veh] = base
                weight = self._weight(veh)
                total += weight * (acc - base)
                if self.cfg.person_weighted and conn.vehicle.getSpeed(veh) < 0.1:
                    queue += weight
                if veh.startswith("ev_"):
                    ev_wait += max(0.0, acc - last.get(veh, acc))
                    new_last[veh] = acc
        delta = total - st.total
        st.entry_wait, st.last_wait, st.total = new_entry, new_last, total
        pressure = abs(
            sum(
                counts.get(lk.in_lane, 0.0) - counts.get(lk.out_lane, 0.0)
                for lk in inter.links
                if not lk.crossing
            )
        )
        return {
            "wait": -delta,
            "queue": queue,
            "pressure": pressure,
            "co2": co2_mg,
            "ev": ev_wait,
            "ped": ped_waiting_s,
        }

    def combine(self, raw: Mapping[str, float]) -> float:
        c, n = self.cfg, self.norm
        # the waiting term is already signed (less waiting = positive); the others are costs
        r = raw["wait"] / n["wait"] if c.base == "wait" else -raw[c.base] / n[c.base]
        if c.co2:
            r -= c.co2 * raw["co2"] / n["co2"]
        if c.ev:
            r -= c.ev * raw["ev"] / n["ev"]
        if c.ped:
            r -= c.ped * raw["ped"] / n["ped"]
        return float(np.clip(r, -c.clip, c.clip))
