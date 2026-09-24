"""Multi-agent traffic signal control environment (PettingZoo parallel API).

One agent per signalised intersection. Every ``delta_time`` seconds each agent
proposes a green phase; the safety shield turns it into the executed phase, the
intersection model handles the yellow transition, and SUMO advances. The same
class runs the classical baselines: with ``controlled=False`` SUMO's own signal
programs stay in charge and the environment only steps and measures.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

from cotraffic import config
from cotraffic.envs.intersection import Intersection
from cotraffic.envs.observations import (
    Measurements,
    ObservationBuilder,
    ObservationConfig,
    Padding,
    phase_pressures,
)
from cotraffic.envs.rewards import RewardComputer, RewardConfig, vehicle_kind
from cotraffic.envs.shield import REASONS, ShieldConfig, ShieldState, apply_shield
from cotraffic.envs.simulation import Episode, Simulation, sumo_command
from cotraffic.networks.build import ensure_network
from cotraffic.networks.topology import load_net, pedestrian_edges, tls_geometry
from cotraffic.paths import CONFIG_DIR
from cotraffic.scenarios.runtime import runtime_perturbations

EpisodeFactory = Callable[[np.random.Generator], Episode]
StepHook = Callable[["CoTrafficEnv", float], None]


def reward_norm(network: str) -> dict[str, float]:
    """Normalisation constants written by ``cotraffic calibrate`` (1.0 if not calibrated)."""
    path = CONFIG_DIR / "reward_norm" / f"{network}.yaml"
    if path.is_file():
        return {k: float(v) for k, v in config.load_yaml(path)["norm"].items()}
    return {"wait": 1.0, "co2": 1.0, "ev": 1.0, "ped": 1.0}


class CoTrafficEnv(ParallelEnv):
    metadata = {"name": "cotraffic_v0", "render_modes": ["human"], "is_parallelizable": True}

    def __init__(
        self,
        network: str,
        episodes: EpisodeFactory,
        agent_cfg: Mapping[str, Any] | None = None,
        controlled: bool = True,
        gui: bool = False,
        runtime_scenarios: Sequence[str] = (),
        record_decisions: bool = False,
        protocol: Mapping[str, Any] | None = None,
        step_hooks: Sequence[StepHook] = (),
        compute_observations: bool = True,
    ):
        self.network = network
        self.episodes = episodes
        self.protocol = dict(protocol or config.load_protocol())
        self.net_cfg = config.load("networks", network)
        self.net_file = ensure_network(network)
        agent_cfg = dict(agent_cfg or {})
        self.obs_cfg = ObservationConfig.from_dict(agent_cfg.get("observation"))
        self.reward_cfg = RewardConfig.from_dict(agent_cfg.get("reward"))
        self.pad = Padding.from_dict(self.net_cfg["padding"])
        self.timing = self.protocol["timing"]
        self.delta = float(self.timing["delta_time"])
        self.step_length = float(self.protocol["sumo"]["step_length"])
        self.shield_cfg = ShieldConfig.from_timing(self.timing)
        self.builder = ObservationBuilder(
            self.obs_cfg, self.pad, self.timing, self.protocol["observation"]
        )
        self.rewards = RewardComputer(
            self.reward_cfg, self.protocol["occupancy"], reward_norm(network)
        )
        self.controlled = controlled
        self.gui = gui
        self.render_mode = "human" if gui else None
        self.record_decisions = record_decisions
        self.compute_observations = compute_observations
        self.step_hooks = list(step_hooks)
        self.runtime = runtime_perturbations(runtime_scenarios)
        self.forecaster = None

        self.geometry = tls_geometry(
            self.net_file, float(self.net_cfg["neighbours"]["max_distance_m"])
        )
        net = load_net(str(self.net_file))
        self.crossing_edges, self.walkingareas = pedestrian_edges(net)
        self.possible_agents = sorted(self.geometry)
        self.agents: list[str] = []
        obs_space = spaces.Box(-1.0, 1.0, shape=(self.builder.size,), dtype=np.float32)
        act_space = spaces.Discrete(self.pad.max_phases)
        self.observation_spaces = dict.fromkeys(self.possible_agents, obs_space)
        self.action_spaces = dict.fromkeys(self.possible_agents, act_space)

        self.sim = Simulation(gui)
        self.conn = None
        self._rng = np.random.default_rng()
        self.episode: Episode | None = None
        self.intersections: dict[str, Intersection] = {}
        self.decisions: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ PettingZoo API
    def observation_space(self, agent: str) -> spaces.Space:
        return self.observation_spaces[agent]

    def action_space(self, agent: str) -> spaces.Space:
        return self.action_spaces[agent]

    def seed_episodes(self, seed: int) -> None:
        """Seed the generator that draws the demand of every following episode."""
        self._rng = np.random.default_rng(seed)

    def reset(self, seed: int | None = None, options: dict[str, Any] | None = None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        options = options or {}
        self.episode = options.get("episode") or self.episodes(self._rng)
        self.conn = self.sim.start(sumo_command(self.episode, self.protocol, self.gui))
        conn = self.conn
        self.now = float(conn.simulation.getTime())
        lanes_per_side = self.pad.lanes_per_side
        yellow = float(self.timing["yellow_time"])
        self.intersections = {
            tid: Intersection(
                conn, tid, self.geometry[tid], self.crossing_edges, yellow, lanes_per_side
            )
            for tid in self.possible_agents
        }
        for inter in self.intersections.values():
            self.builder.check(inter)
        self._index_network()
        lanes = [
            ln for inter in self.intersections.values() for ln in inter.in_lanes + inter.out_lanes
        ]
        self.meas = Measurements(
            conn, lanes, float(self.protocol["observation"]["lane_capacity_gap_m"])
        )
        if self.controlled:
            for inter in self.intersections.values():
                inter.start(self.now, 0)

        self.rewards.reset()
        self.ev_ids: set[str] = set()
        self.bus_ids: set[str] = set()
        self.person_ids: set[str] = set()
        self.teleported: set[str] = set()
        self.teleports = 0
        self.stats: Counter[str] = Counter()
        self.decisions = []
        self.episode_reward = 0.0
        self.halting_sum = 0.0
        self.decision_steps = 0
        self.wall_start = time.perf_counter()
        noise = self.runtime.get("sensor_noise")
        if noise is not None:
            noise.reset(self.meas.lanes, self._rng)
        if "comm_dropout" in self.runtime:
            self.runtime["comm_dropout"].reset()

        self._sense()
        self.agents = list(self.possible_agents)
        obs = self._observe_all() if self.compute_observations else {}
        return obs, {a: {} for a in self.agents}

    def step(self, actions: Mapping[str, int] | None):
        conn = self.conn
        now = self.now
        if self.controlled:
            for aid, inter in self.intersections.items():
                if inter.in_yellow:
                    continue
                requested = (
                    int(actions[aid]) if actions is not None and aid in actions else inter.phase
                )
                decision = apply_shield(requested, self._shield_state(inter, now), self.shield_cfg)
                self.stats["decisions"] += 1
                if decision.reason is not None:
                    self.stats[decision.reason] += 1
                switched = inter.switch(decision.phase, now)
                self.stats["switches"] += int(switched)
                if self.record_decisions:
                    self.decisions.append(
                        {
                            "time": now,
                            "agent": aid,
                            "requested": requested,
                            "executed": decision.phase,
                            "reason": decision.reason or "",
                        }
                    )

        co2 = defaultdict(float)
        need_co2 = self.reward_cfg.co2 > 0
        n_steps = max(1, int(round(self.delta / self.step_length)))
        for _ in range(n_steps):
            conn.simulationStep()
            self.now = float(conn.simulation.getTime())
            for inter in self.intersections.values():
                inter.tick(self.now, self.step_length)
            self._track_step()
            if need_co2:
                for aid, inter in self.intersections.items():
                    co2[aid] += (
                        sum(conn.lane.getCO2Emission(ln) for ln in inter.in_lanes)
                        * self.step_length
                    )
            for hook in self.step_hooks:
                hook(self, self.now)

        self._sense()
        self.decision_steps += 1
        self.halting_sum += sum(
            self.meas.halting[ln] for i in self.intersections.values() for ln in i.in_lanes
        )
        done = self.now >= self.episode.end_time - 1e-6
        obs = self._observe_all() if self.compute_observations else {}
        rewards, infos = {}, {}
        for aid, inter in self.intersections.items():
            if self.compute_observations:
                ped_s = sum(self.ped_waiting.get(c, 0.0) for c in inter.crossings) * self.delta
                raw = self.rewards.raw_terms(conn, inter, co2[aid], ped_s)
                rewards[aid] = self.rewards.combine(raw)
                infos[aid] = {"raw": raw}
            else:
                rewards[aid] = 0.0
                infos[aid] = {}
        self.episode_reward += float(np.mean(list(rewards.values()))) if rewards else 0.0
        terminations = dict.fromkeys(self.agents, False)
        truncations = dict.fromkeys(self.agents, done)
        if done:
            summary = self.episode_summary()
            for aid in self.agents:
                infos[aid]["episode_summary"] = summary
                # episodes end on a time limit: learners must bootstrap, not treat it as terminal
                infos[aid]["TimeLimit.truncated"] = True
            self.agents = []
        return obs, rewards, terminations, truncations, infos

    def close(self) -> None:
        self.sim.close()

    def render(self) -> None:
        return None

    # ------------------------------------------------------------------ internals
    def _index_network(self) -> None:
        """Lookup tables linking lanes, crossings and walking areas to intersections."""
        self.lane_owner: dict[str, tuple[str, str]] = {}
        self.crossing_owner: dict[str, str] = {}
        for tid, inter in self.intersections.items():
            for lane in inter.in_lanes:
                self.lane_owner[lane] = (tid, inter.lane_side[lane])
            for crossing in inter.crossings:
                self.crossing_owner[crossing] = tid
        # neighbour links: which lanes/links of the upstream neighbour feed this intersection
        self.neighbour_links: dict[str, dict[str, tuple[str, list[str], frozenset[int]]]] = {}
        for tid, geo in self.geometry.items():
            links = {}
            for side, nb in geo.neighbours.items():
                upstream = self.intersections[nb.tls_id]
                first_edge = nb.path_edges[0]
                feeding = [
                    lk
                    for lk in upstream.links
                    if not lk.crossing and lk.out_lane.rsplit("_", 1)[0] == first_edge
                ]
                in_lanes = sorted({lk.in_lane for lk in feeding})
                links[side] = (nb.tls_id, in_lanes, frozenset(lk.index for lk in feeding))
            self.neighbour_links[tid] = links

    def _track_step(self) -> None:
        sim = self.conn.simulation
        for veh in sim.getDepartedIDList():
            kind = vehicle_kind(veh)
            if kind == "emergency":
                self.ev_ids.add(veh)
            elif kind == "bus":
                self.bus_ids.add(veh)
        for veh in sim.getArrivedIDList():
            self.ev_ids.discard(veh)
            self.bus_ids.discard(veh)
        self.person_ids.update(sim.getDepartedPersonIDList())
        self.person_ids.difference_update(sim.getArrivedPersonIDList())
        teleporting = sim.getStartingTeleportIDList()
        if teleporting:
            self.teleports += len(teleporting)
            self.teleported.update(teleporting)

    def _sense(self) -> None:
        """Sample every measurement used by observations, rewards and the shield."""
        conn = self.conn
        self.meas.refresh(conn)
        noise = self.runtime.get("sensor_noise")
        if noise is not None:
            noise.apply(self.meas, self._rng)

        self.ped_waiting: dict[str, float] = defaultdict(float)
        for person in self.person_ids:
            if (
                conn.person.getRoadID(person) in self.walkingareas
                and conn.person.getWaitingTime(person) > 0
            ):
                nxt = conn.person.getNextEdge(person)
                if nxt in self.crossing_owner:
                    self.ped_waiting[nxt] += 1.0

        rng_ev = float(self.protocol["observation"]["ev_detection_range_m"])
        self.ev_info: dict[str, dict[str, Any]] = {}
        for ev in self.ev_ids:
            upcoming = conn.vehicle.getNextTLS(ev)
            if not upcoming:
                continue
            tls, link_index, dist, _state = upcoming[0]
            inter = self.intersections.get(tls)
            if inter is None or dist > rng_ev or link_index not in inter.link_by_index:
                continue
            prox = 1.0 - dist / rng_ev
            info = self.ev_info.setdefault(
                tls, {"side": {}, "phase": [0.0] * inter.n_phases, "links": {}}
            )
            side = inter.lane_side.get(inter.link_by_index[link_index].in_lane, "north")
            info["side"][side] = max(info["side"].get(side, 0.0), prox)
            info["links"][link_index] = max(info["links"].get(link_index, 0.0), prox)
            for k, links in enumerate(inter.phase_links):
                if link_index in links:
                    info["phase"][k] = max(info["phase"][k], prox)

        self.bus_load: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        if self.bus_ids:
            occupancy = float(self.protocol["occupancy"]["bus"])
            for bus in self.bus_ids:
                owner = self.lane_owner.get(conn.vehicle.getLaneID(bus))
                if owner is not None:
                    self.bus_load[owner[0]][owner[1]] += occupancy

    def _messages(self) -> dict[str, dict[str, np.ndarray]]:
        """Messages each agent receives from its upstream neighbours (COOP)."""
        pressure = {
            tid: max(phase_pressures(inter, self.meas)) for tid, inter in self.intersections.items()
        }
        dropout = self.runtime.get("comm_dropout")
        out: dict[str, dict[str, np.ndarray]] = {}
        for tid, links in self.neighbour_links.items():
            received = {}
            for side, (nb_id, in_lanes, link_idx) in links.items():
                nb = self.intersections[nb_id]
                releasing = float(not nb.in_yellow and bool(nb.phase_links[nb.phase] & link_idx))
                msg = np.array(
                    [self.meas.queue(in_lanes), releasing, pressure[nb_id]], dtype=np.float32
                )
                if dropout is not None:
                    msg = dropout.transmit((nb_id, tid), msg, self._rng)
                received[side] = msg
            out[tid] = received
        return out

    def _observe_all(self) -> dict[str, np.ndarray]:
        messages = self._messages() if self.obs_cfg.neighbours else {}
        forecasts = (
            self.forecaster.predict(self) if (self.obs_cfg.forecast and self.forecaster) else {}
        )
        obs = {}
        for tid, inter in self.intersections.items():
            obs[tid] = self.builder.observe(
                inter,
                self.meas,
                self.now,
                messages=messages.get(tid),
                ev=self.ev_info.get(tid),
                ped_waiting=self.ped_waiting,
                bus_load=self.bus_load.get(tid),
                forecast=forecasts.get(tid),
            )
        return obs

    def _shield_state(self, inter: Intersection, now: float) -> ShieldState:
        halting = self.meas.halting
        demand = set()
        for link in inter.links:
            if link.crossing:
                if self.ped_waiting.get(link.crossing, 0.0) > 0:
                    demand.add(link.index)
            elif halting.get(link.in_lane, 0.0) > 0:
                demand.add(link.index)
        served = inter.phase_lanes[inter.phase]
        phase_demand = [
            sum(halting[ln] for ln in lanes if ln not in served) for lanes in inter.phase_lanes
        ]
        return ShieldState(
            inter.phase,
            inter.green_elapsed(now),
            inter.phase_links,
            inter.link_red_time(now),
            frozenset(demand),
            phase_demand,
        )

    # ------------------------------------------------------------------ reporting
    def episode_summary(self) -> dict[str, Any]:
        s = {
            "sim_time": self.now,
            "wall_time_s": time.perf_counter() - self.wall_start,
            "episode_reward": self.episode_reward,
            "mean_halting": self.halting_sum / max(1, self.decision_steps),
            "teleports": self.teleports,
            "decisions": self.stats["decisions"],
            "switches": self.stats["switches"],
        }
        for reason in REASONS:
            s[f"shield_{reason}"] = self.stats[reason]
        if "comm_dropout" in self.runtime:
            d = self.runtime["comm_dropout"]
            s["messages_sent"], s["messages_lost"] = d.sent, d.lost
        if self.episode is not None:
            s.update(
                {f"episode_{k}": v for k, v in self.episode.info.items() if not isinstance(v, list)}
            )
        return s
