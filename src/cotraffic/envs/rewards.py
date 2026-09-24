"""Per-agent reward.

    r = r_wait - l_co2 * CO2 / n_co2 - l_ev * EVwait / n_ev - l_ped * PEDwait / n_ped
    r_wait = -(W_t - W_{t-1}) / n_wait

``W`` is the (optionally person-weighted) waiting time accumulated by the vehicles
currently on the intersection's incoming lanes, counting only the waiting done since
they entered those lanes, so an agent is not charged for delay caused upstream.
Over an episode the discounted sum of ``r_wait`` favours keeping ``W`` low at all
times, i.e. short waits. The ``n_*`` constants come from baseline runs
(``cotraffic calibrate``) so that each term is of order 1.
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


@dataclass(frozen=True)
class RewardConfig:
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
        self.norm = {k: max(1e-9, float(norm.get(k, 1.0))) for k in ("wait", "co2", "ev", "ped")}
        self.state: dict[str, _AgentState] = {}

    def reset(self) -> None:
        self.state = {}

    def _weight(self, veh_id: str) -> float:
        kind = vehicle_kind(veh_id)
        if kind == "incident":
            return 0.0
        return self.occupancy[kind] if self.cfg.person_weighted else 1.0

    def raw_terms(
        self, conn, inter: Intersection, co2_mg: float, ped_waiting_s: float
    ) -> dict[str, float]:
        """Unscaled reward components for one decision interval."""
        st = self.state.setdefault(inter.id, _AgentState())
        entry, new_entry, last, new_last = st.entry_wait, {}, st.last_wait, {}
        total, ev_wait = 0.0, 0.0
        for lane in inter.in_lanes:
            for veh in conn.lane.getLastStepVehicleIDs(lane):
                acc = conn.vehicle.getAccumulatedWaitingTime(veh)
                base = entry.get(veh, acc)
                new_entry[veh] = base
                total += self._weight(veh) * (acc - base)
                if veh.startswith("ev_"):
                    ev_wait += max(0.0, acc - last.get(veh, acc))
                    new_last[veh] = acc
        delta = total - st.total
        st.entry_wait, st.last_wait, st.total = new_entry, new_last, total
        return {"wait": -delta, "co2": co2_mg, "ev": ev_wait, "ped": ped_waiting_s}

    def combine(self, raw: Mapping[str, float]) -> float:
        c, n = self.cfg, self.norm
        r = raw["wait"] / n["wait"]
        if c.co2:
            r -= c.co2 * raw["co2"] / n["co2"]
        if c.ev:
            r -= c.ev * raw["ev"] / n["ev"]
        if c.ped:
            r -= c.ped * raw["ped"] / n["ped"]
        return float(np.clip(r, -c.clip, c.clip))
