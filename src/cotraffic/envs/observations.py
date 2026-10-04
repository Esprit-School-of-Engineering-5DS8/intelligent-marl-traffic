"""Observations of the traffic-signal agents.

An observation is a fixed-size vector made of named blocks, all scaled to about
[0, 1] (pressures to [-1, 1]):

``lanes``        per incoming lane slot (``lanes_per_side`` slots on each of the
                 N/E/S/W sides): queue, density and speed ratio
``phase``        current phase one-hot, queue and pressure served by each phase,
                 time in phase and a min-green-satisfied flag
``neighbours``   COOP only - message received from the upstream neighbour on each
                 side: its queue heading to us, whether it currently releases
                 traffic toward us, its largest phase pressure
``emergency``    per side: emergency vehicle approaching, proximity; per phase:
                 proximity of an emergency vehicle that the phase would serve
``pedestrians``  waiting pedestrians per crossing slot
``buses``        occupancy-weighted buses per side
``forecast``     predicted inflow for the next 5 min per side

Slots are fixed by geometry (side, lane index) and padded with zeros, so the same
policy can be shared by intersections of different shapes. Per-phase features give
the meaning of every action explicitly, which matters when phase sets differ.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from cotraffic.envs.intersection import Intersection
from cotraffic.networks.topology import SIDES

BLOCKS = ("lanes", "phase", "neighbours", "emergency", "pedestrians", "buses", "forecast")
MESSAGE_SIZE = 3


@dataclass(frozen=True)
class ObservationConfig:
    neighbours: bool = False
    emergency: bool = False
    pedestrians: bool = False
    buses: bool = False
    forecast: bool = False

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> ObservationConfig:
        d = dict(d or {})
        unknown = set(d) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown observation options: {sorted(unknown)}")
        return cls(**{k: bool(v) for k, v in d.items()})


@dataclass(frozen=True)
class Padding:
    lanes_per_side: int
    max_phases: int
    max_crossings: int
    # a junction with more crossings than max_crossings is refused, unless the network
    # accepts that the extra ones are signalled but not observed (demonstration variant)
    extra_crossings_unobserved: bool = False

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Padding:
        return cls(
            int(d["lanes_per_side"]),
            int(d["max_phases"]),
            int(d["max_crossings"]),
            bool(d.get("extra_crossings_unobserved", False)),
        )


def block_sizes(cfg: ObservationConfig, pad: Padding) -> dict[str, int]:
    sizes = {
        "lanes": 4 * pad.lanes_per_side * 3,
        "phase": 3 * pad.max_phases + 2,
    }
    if cfg.neighbours:
        sizes["neighbours"] = 4 * MESSAGE_SIZE
    if cfg.emergency:
        sizes["emergency"] = 4 * 2 + pad.max_phases
    if cfg.pedestrians:
        sizes["pedestrians"] = pad.max_crossings
    if cfg.buses:
        sizes["buses"] = 4
    if cfg.forecast:
        sizes["forecast"] = 4
    return sizes


def block_slices(cfg: ObservationConfig, pad: Padding) -> dict[str, slice]:
    out, start = {}, 0
    for name, size in block_sizes(cfg, pad).items():
        out[name] = slice(start, start + size)
        start += size
    return out


class Measurements:
    """Detector-like lane data sampled once per decision and shared by all agents."""

    def __init__(self, conn, lanes: Iterable[str], capacity_gap_m: float):
        self.lanes = sorted(set(lanes))
        self.capacity = {
            ln: max(1.0, conn.lane.getLength(ln) / capacity_gap_m) for ln in self.lanes
        }
        self.speed_limit = {ln: max(0.1, conn.lane.getMaxSpeed(ln)) for ln in self.lanes}
        self.halting = dict.fromkeys(self.lanes, 0.0)
        self.count = dict.fromkeys(self.lanes, 0.0)
        self.speed = dict(self.speed_limit)

    def refresh(self, conn) -> None:
        lane = conn.lane
        for ln in self.lanes:
            self.halting[ln] = float(lane.getLastStepHaltingNumber(ln))
            self.count[ln] = float(lane.getLastStepVehicleNumber(ln))
            self.speed[ln] = float(lane.getLastStepMeanSpeed(ln))

    def queue(self, lanes: Iterable[str]) -> float:
        lanes = list(lanes)
        if not lanes:
            return 0.0
        return min(
            1.0, sum(self.halting[ln] for ln in lanes) / sum(self.capacity[ln] for ln in lanes)
        )

    def link_pressure(self, in_lane: str, out_lane: str) -> float:
        density_in = self.count[in_lane] / self.capacity[in_lane]
        density_out = (
            self.count[out_lane] / self.capacity[out_lane] if out_lane in self.capacity else 0.0
        )
        return density_in - density_out


def phase_pressures(inter: Intersection, meas: Measurements) -> list[float]:
    """Mean link pressure (density difference, in [-1, 1]) of every green phase."""
    out = []
    for links in inter.phase_links:
        values = [
            meas.link_pressure(lk.in_lane, lk.out_lane)
            for lk in inter.links
            if lk.index in links and not lk.crossing
        ]
        out.append(float(np.clip(np.mean(values), -1.0, 1.0)) if values else 0.0)
    return out


class ObservationBuilder:
    def __init__(
        self,
        cfg: ObservationConfig,
        pad: Padding,
        timing: Mapping[str, float],
        protocol_obs: Mapping[str, float],
    ):
        self.cfg = cfg
        self.pad = pad
        self.max_green = float(timing["max_green"])
        self.min_green = float(timing["min_green"])
        self.ped_norm = float(protocol_obs["ped_norm"])
        self.bus_norm = float(protocol_obs["bus_norm"])
        self.forecast_norm = float(protocol_obs["forecast_norm"])
        self.slices = block_slices(cfg, pad)
        self.size = sum(s.stop - s.start for s in self.slices.values())

    def check(self, inter: Intersection) -> None:
        if inter.n_phases > self.pad.max_phases:
            raise ValueError(
                f"{inter.id} has {inter.n_phases} phases, padding allows {self.pad.max_phases}"
            )
        too_many = len(inter.crossings) > self.pad.max_crossings
        if too_many and self.cfg.pedestrians and not self.pad.extra_crossings_unobserved:
            raise ValueError(
                f"{inter.id} has {len(inter.crossings)} crossings, padding allows "
                f"{self.pad.max_crossings}"
            )

    def observe(
        self,
        inter: Intersection,
        meas: Measurements,
        now: float,
        messages: Mapping[str, np.ndarray] | None = None,
        ev: Mapping[str, Any] | None = None,
        ped_waiting: Mapping[str, float] | None = None,
        bus_load: Mapping[str, float] | None = None,
        forecast: Mapping[str, float] | None = None,
    ) -> np.ndarray:
        obs = np.zeros(self.size, dtype=np.float32)
        pad = self.pad

        # lanes: fixed slots per side; extra lanes on a side are averaged into the last slot
        values = []
        for side in SIDES:
            lanes = inter.side_lanes[side]
            slots = [[] for _ in range(pad.lanes_per_side)]
            for i, lane in enumerate(lanes):
                slots[min(i, pad.lanes_per_side - 1)].append(lane)
            for slot in slots:
                if not slot:
                    values.extend((0.0, 0.0, 0.0))
                    continue
                cap = sum(meas.capacity[ln] for ln in slot)
                values.append(min(1.0, sum(meas.halting[ln] for ln in slot) / cap))
                values.append(min(1.0, sum(meas.count[ln] for ln in slot) / cap))
                values.append(
                    float(np.mean([min(1.0, meas.speed[ln] / meas.speed_limit[ln]) for ln in slot]))
                )
        obs[self.slices["lanes"]] = values

        # phase block
        p = pad.max_phases
        block = np.zeros(3 * p + 2, dtype=np.float32)
        if not inter.in_yellow:
            block[inter.phase] = 1.0
        for k, lanes in enumerate(inter.phase_lanes):
            block[p + k] = meas.queue(lanes)
        block[2 * p : 2 * p + inter.n_phases] = phase_pressures(inter, meas)
        elapsed = inter.green_elapsed(now)
        block[3 * p] = min(1.0, elapsed / self.max_green)
        block[3 * p + 1] = float(elapsed >= self.min_green)
        obs[self.slices["phase"]] = block

        if self.cfg.neighbours:
            msg = np.zeros(4 * MESSAGE_SIZE, dtype=np.float32)
            for i, side in enumerate(SIDES):
                if messages and side in messages:
                    msg[i * MESSAGE_SIZE : (i + 1) * MESSAGE_SIZE] = messages[side]
            obs[self.slices["neighbours"]] = msg

        if self.cfg.emergency:
            block = np.zeros(8 + p, dtype=np.float32)
            if ev:
                for i, side in enumerate(SIDES):
                    prox = ev["side"].get(side, 0.0)
                    block[2 * i] = float(prox > 0.0)
                    block[2 * i + 1] = prox
                for k in range(inter.n_phases):
                    block[8 + k] = ev["phase"][k]
            obs[self.slices["emergency"]] = block

        if self.cfg.pedestrians:
            block = np.zeros(pad.max_crossings, dtype=np.float32)
            if ped_waiting:
                for k, crossing in enumerate(inter.crossings[: pad.max_crossings]):
                    block[k] = min(1.0, ped_waiting.get(crossing, 0.0) / self.ped_norm)
            obs[self.slices["pedestrians"]] = block

        if self.cfg.buses:
            obs[self.slices["buses"]] = [
                min(1.0, (bus_load or {}).get(side, 0.0) / self.bus_norm) for side in SIDES
            ]

        if self.cfg.forecast:
            obs[self.slices["forecast"]] = [
                min(1.0, (forecast or {}).get(side, 0.0) / self.forecast_norm) for side in SIDES
            ]
        return obs
