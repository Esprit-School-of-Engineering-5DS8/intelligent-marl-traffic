"""Measurements beyond the report's metrics, for the dashboard (``results/extra/``).

A probe attached to the simulation (a step hook, called every simulated second) collects
them during an evaluation episode, together with SUMO's trip output; it only reads the
simulation and never changes it. Extra runs are written to ``results/extra/`` so that the
report's results in ``results/raw/`` are never touched; their common metrics must equal
the original runs (same seeds), which ``compare_with_raw`` checks.

Definitions (measured window and populations as in :mod:`cotraffic.evaluation.metrics`):

* **Pedestrian waiting, 95th percentile** - of the pedestrians departing in the measured
  window (personinfo, as ``ped_mean_waiting_time``).
* **Crossings completed in green** - share of the traversals of a signalised crossing
  during which its signal stayed green from the pedestrian's entry to exit. A pedestrian
  still on the crossing when it turns red finishes in red.
* **Pedestrian green and crowd size** - every green interval of a signalised crossing: its
  duration and the pedestrians waiting for that crossing when it turned green (log
  ``pedestrian_greens``); per run, the least-squares slope of duration on crowd size.
* **Emergency vehicles** - per vehicle departing in the measured window (log
  ``emergency``): trip time, delay (time loss, departure delay included), stops (SUMO
  ``waitingCount``), stops at a signal that is not green for its link (halted within 30 m
  of it), and the error of an arrival-time estimate made at departure: the sum of the
  current travel times of the edges of its route, which a dispatcher with live link travel
  times would predict.
* **Reward terms** - the cost components of the agents' reward computed the same way for
  every controller, each divided by the network's reward constant (``configs/reward_norm``)
  and counted negative: delay (vehicles halted on the incoming lanes, whose sum over time is
  their waiting time; the reward itself uses the change of waiting, which averages to about
  zero over an episode), CO2, emergency-vehicle waiting and pedestrian waiting; mean per
  decision and intersection over the measured window.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cotraffic.envs.rewards import RewardComputer, RewardConfig
from cotraffic.evaluation.metrics import parse_tripinfo, planned_vehicles

GREEN = frozenset("gG")
STOP_DISTANCE_M = 30.0


class ExtraProbe:
    """Step hook collecting the extra measurements of one episode."""

    def __init__(self, window: tuple[float, float]) -> None:
        self.begin, self.end = window
        self.ready = False
        self.calls = 0
        # pedestrians
        self.crossing_links: dict[str, tuple[str, list[int]]] = {}
        self.on_crossing: dict[str, list[Any]] = {}  # person -> [crossing, entry time, ok]
        self.traversals: list[bool] = []
        self.green_open: dict[str, dict[str, Any]] = {}
        self.greens: list[dict[str, Any]] = []
        # emergency vehicles
        self.ev: dict[str, dict[str, Any]] = {}
        # reward terms
        self.co2: dict[str, float] = defaultdict(float)
        self.terms: dict[str, float] = defaultdict(float)
        self.term_count = 0

    def _setup(self, env) -> None:
        from cotraffic.envs.traffic_env import reward_norm

        for tid, inter in env.intersections.items():
            for link in inter.crossing_links:
                _, indices = self.crossing_links.setdefault(link.crossing, (tid, []))
                indices.append(link.index)
        self.rewards = RewardComputer(
            RewardConfig(), env.protocol["occupancy"], reward_norm(env.network)
        )
        self.substeps = max(1, round(env.delta / env.step_length))
        self.ready = True

    def __call__(self, env, now: float) -> None:
        if not self.ready:
            self._setup(env)
        conn = env.conn
        states = {tid: conn.trafficlight.getRedYellowGreenState(tid) for tid in env.intersections}
        self._pedestrians(env, conn, now, states)
        self._emergency(env, conn, now)
        self._reward_terms(env, conn, now)

    # ------------------------------------------------------------------ pedestrians
    def _waiting(self, env, conn) -> dict[str, float]:
        """Pedestrians waiting for each crossing (as the environment counts them)."""
        out: dict[str, float] = defaultdict(float)
        for person in env.person_ids:
            if conn.person.getRoadID(person) in env.walkingareas and (
                conn.person.getWaitingTime(person) > 0
            ):
                nxt = conn.person.getNextEdge(person)
                if nxt in self.crossing_links:
                    out[nxt] += 1.0
        return out

    def _pedestrians(self, env, conn, now: float, states: dict[str, str]) -> None:
        if not self.crossing_links:
            return
        green = {
            c: all(states[tls][i] in GREEN for i in idx)
            for c, (tls, idx) in self.crossing_links.items()
        }
        seen = set()
        for person in env.person_ids:
            road = conn.person.getRoadID(person)
            if road not in self.crossing_links:
                continue
            seen.add(person)
            if person not in self.on_crossing:
                self.on_crossing[person] = [road, now, green[road]]
                if road in self.green_open:
                    self.green_open[road]["crossed"] += 1
            elif not green[road]:
                self.on_crossing[person][2] = False
        for person in [p for p in self.on_crossing if p not in seen]:
            _, entry, ok = self.on_crossing.pop(person)
            if self.begin <= entry < self.end:
                self.traversals.append(bool(ok))
        opening = [c for c, g in green.items() if g and c not in self.green_open]
        waiting = self._waiting(env, conn) if opening else {}
        for crossing in opening:
            self.green_open[crossing] = {
                "tls": self.crossing_links[crossing][0],
                "crossing": crossing,
                "start": now,
                "waiting_at_start": waiting.get(crossing, 0.0),
                "crossed": 0,
            }
        for crossing in [c for c in self.green_open if not green[c]]:
            event = self.green_open.pop(crossing)
            event["duration_s"] = now - event["start"]
            if self.begin <= event["start"] < self.end:
                self.greens.append(event)

    # ------------------------------------------------------------------ emergency vehicles
    def _emergency(self, env, conn, now: float) -> None:
        for vid in env.ev_ids:
            rec = self.ev.get(vid)
            if rec is None:
                route = conn.vehicle.getRoute(vid)
                rec = self.ev[vid] = {
                    "id": vid,
                    "eta_s": float(sum(conn.edge.getTraveltime(e) for e in route)),
                    "stops_at_red": 0,
                    "halted": False,
                }
            if conn.vehicle.getSpeed(vid) < 0.1:
                if not rec["halted"]:
                    rec["halted"] = True
                    upcoming = conn.vehicle.getNextTLS(vid)
                    if (
                        upcoming
                        and upcoming[0][2] <= STOP_DISTANCE_M
                        and (upcoming[0][3] not in GREEN)
                    ):
                        rec["stops_at_red"] += 1
            else:
                rec["halted"] = False

    # ------------------------------------------------------------------ reward terms
    def _reward_terms(self, env, conn, now: float) -> None:
        for aid, inter in env.intersections.items():
            self.co2[aid] += (
                sum(conn.lane.getCO2Emission(ln) for ln in inter.in_lanes) * env.step_length
            )
        self.calls += 1
        if self.calls % self.substeps:
            return  # not the end of a decision interval
        waiting = self._waiting(env, conn) if self.crossing_links else {}
        norm = self.rewards.norm
        for aid, inter in env.intersections.items():
            ped_s = sum(waiting.get(c, 0.0) for c in inter.crossings) * env.delta
            raw = self.rewards.raw_terms(conn, inter, self.co2[aid], ped_s, env.meas.count)
            if self.begin <= now < self.end:
                self.terms["delay"] -= raw["queue"] / norm["queue"]
                self.terms["co2"] -= raw["co2"] / norm["co2"]
                self.terms["ev"] -= raw["ev"] / norm["ev"]
                self.terms["ped"] -= raw["ped"] / norm["ped"]
                self.term_count += 1
        self.co2.clear()

    # ------------------------------------------------------------------ results
    def finish(
        self, output_dir: Path, route_files: list[Path]
    ) -> tuple[dict[str, float], pd.DataFrame, pd.DataFrame]:
        """(extra metrics, emergency-vehicle log, pedestrian-green log)."""
        vehicles, persons = parse_tripinfo(output_dir / "tripinfo.xml")
        m: dict[str, float] = {}
        if not persons.empty:
            ped = persons[(persons["depart"] >= self.begin) & (persons["depart"] < self.end)]
            if not ped.empty:
                m["ped_p95_waiting_time"] = float(np.percentile(ped["waiting_time"], 95))
        if self.traversals:
            m["ped_crossings"] = float(len(self.traversals))
            m["ped_crossings_in_green_pct"] = 100.0 * float(np.mean(self.traversals))
        greens = pd.DataFrame(self.greens)
        if self.traversals and len(greens) >= 2:  # crowd sizes only mean something with pedestrians
            m["ped_green_mean_s"] = float(greens["duration_s"].mean())
            m["ped_green_mean_waiting"] = float(greens["waiting_at_start"].mean())
            if greens["waiting_at_start"].std() > 0:
                slope, _ = np.polyfit(greens["waiting_at_start"], greens["duration_s"], 1)
                m["ped_green_slope_s_per_person"] = float(slope)

        planned = planned_vehicles(route_files).set_index("id")["planned_depart"]
        trips = vehicles.set_index("id")
        rows = []
        for vid, rec in self.ev.items():
            depart = float(planned.get(vid, np.nan))
            if not (self.begin <= depart < self.end):
                continue
            row = {
                "id": vid,
                "planned_depart": depart,
                "eta_s": rec["eta_s"],
                "stops_at_red": rec["stops_at_red"],
            }
            if vid in trips.index and trips.at[vid, "arrival"] >= 0:
                t = trips.loc[vid]
                row.update(
                    trip_time_s=float(t["duration"]),
                    delay_s=float(t["time_loss"] + t["depart_delay"]),
                    stops=float(t["waiting_count"]),
                    eta_error_s=float(t["duration"] - rec["eta_s"]),
                    eta_error_pct=100.0 * float(t["duration"] - rec["eta_s"]) / rec["eta_s"]
                    if rec["eta_s"] > 0
                    else np.nan,
                )
            rows.append(row)
        ev = pd.DataFrame(rows)
        if not ev.empty:
            m["ev_logged"] = float(len(ev))
            m["ev_stops_at_red_mean"] = float(ev["stops_at_red"].mean())
            if "eta_error_s" in ev:
                done = ev.dropna(subset=["eta_error_s"])
                if not done.empty:
                    m["ev_stops_mean"] = float(done["stops"].mean())
                    m["ev_eta_error_mean_s"] = float(done["eta_error_s"].mean())
                    m["ev_eta_abs_error_mean_s"] = float(done["eta_error_s"].abs().mean())
                    m["ev_eta_error_pct_mean"] = float(done["eta_error_pct"].mean())
        if self.term_count:
            for name in ("delay", "co2", "ev", "ped"):
                m[f"reward_{name}"] = self.terms[name] / self.term_count
        return m, ev, greens


def compare_with_raw(extra_raw: Path, raw: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    """Runs present in both folders whose common metrics differ (determinism check)."""
    rows = []
    for path in sorted(Path(extra_raw).glob("*.csv")):
        original = Path(raw) / path.name
        if not original.is_file():
            continue
        a, b = pd.read_csv(path).iloc[0], pd.read_csv(original).iloc[0]
        for col in columns:
            if (
                col in a
                and col in b
                and not np.isclose(float(a[col]), float(b[col]), equal_nan=True)
            ):
                rows.append({"run_id": path.stem, "metric": col, "extra": a[col], "raw": b[col]})
    return pd.DataFrame(rows, columns=["run_id", "metric", "extra", "raw"])
