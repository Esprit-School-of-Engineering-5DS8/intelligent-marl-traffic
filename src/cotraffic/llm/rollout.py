"""Situations saved from validation episodes, and short rollouts that score an advice.

A situation is a snapshot (llm.snapshot) plus its text and the episode it belongs to.
``score`` replays it for ``horizon_s`` seconds with one advice (or none) and measures, on
the controlled approaches, the vehicle-seconds of waiting, the seconds emergency vehicles
spend stopped and the person-seconds pedestrians wait. Two replays of the same snapshot
are identical, so an advice and the no-advice baseline are compared on the same start.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cotraffic.envs.episodes import evaluation_episode, split_scenarios
from cotraffic.envs.traffic_env import CoTrafficEnv
from cotraffic.llm.advice import Advice
from cotraffic.llm.advised import AdvisedPolicy, AdvisorConfig
from cotraffic.llm.situation import Junction, Situation
from cotraffic.llm.snapshot import SUMO_STATE_OPTIONS, Snapshot, restore, take
from cotraffic.llm.sources import AdviceSource, FixedSource


@dataclass
class EpisodeSpec:
    network: str
    demand: str
    scenarios: list[str]
    seed: int
    mode: str = "validation"

    def build(self):
        return evaluation_episode(
            self.network, self.demand, self.scenarios, self.seed, mode=self.mode
        )


@dataclass
class Stored:
    id: str
    spec: EpisodeSpec
    situation: Situation
    snapshot: Snapshot

    def save(self, folder: Path) -> None:
        data = {
            "id": self.id,
            "spec": asdict(self.spec),
            "situation": self.situation.to_dict(),
            "snapshot": {
                "time": self.snapshot.time,
                "sumo_state": str(self.snapshot.sumo_state),
                "python_state": str(self.snapshot.python_state),
            },
        }
        (folder / f"{self.id}.json").write_text(json.dumps(data), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> Stored:
        d = json.loads(path.read_text(encoding="utf-8"))
        sit = d["situation"]
        situation = Situation(
            time=sit["time"],
            trigger=sit["trigger"],
            junctions=[Junction(**j) for j in sit["junctions"]],
            events=sit["events"],
        )
        snap = d["snapshot"]
        return Stored(
            id=d["id"],
            spec=EpisodeSpec(**d["spec"]),
            situation=situation,
            snapshot=Snapshot(snap["time"], Path(snap["sumo_state"]), Path(snap["python_state"])),
        )


def make_env(spec: EpisodeSpec, agent_cfg: dict[str, Any]) -> CoTrafficEnv:
    episode = spec.build()
    _, runtime = split_scenarios(spec.scenarios)
    return CoTrafficEnv(
        spec.network,
        lambda rng: episode,
        agent_cfg,
        runtime_scenarios=runtime,
        sumo_options=SUMO_STATE_OPTIONS,
    )


class Recorder(AdvisedPolicy):
    """Runs the policy with no advice and saves every situation where a call would happen."""

    def __init__(
        self,
        base,
        spec: EpisodeSpec,
        folder: Path,
        cfg: AdvisorConfig,
        after_s: float,
        during_events_s: float = 60.0,
    ):
        super().__init__(base, AdviceSource(), cfg, name="recorder")
        self.spec = spec
        self.folder = folder
        self.after_s = after_s
        self.during_events_s = during_events_s
        self.stored: list[Stored] = []
        self._obs: dict[str, Any] | None = None
        self._last_event_point = -1e9

    def act(self, env, obs):
        self._obs = obs
        actions = super().act(env, obs)
        # extra situations while an emergency vehicle or an incident is active: rare
        # events would otherwise be a handful of points in the benchmark set
        from cotraffic.llm.situation import events

        active = [e for e in events(env) if e["kind"] in ("emergency", "incident")]
        if active and env.now - self._last_event_point >= self.during_events_s:
            self._last_event_point = env.now
            self._save(env, "event-active")
        return actions

    def _ask(self, env, trigger: str) -> None:
        super()._ask(env, trigger)
        self._save(env, trigger)

    def _save(self, env, trigger: str) -> None:
        if env.now < self.after_s or any(st.situation.time == env.now for st in self.stored):
            return
        from cotraffic.llm.situation import observe

        s = self.spec
        scen = "+".join(s.scenarios) or "normal"
        sid = f"{s.network}__{scen}__{s.demand}__s{s.seed}__t{int(env.now)}"
        snap = take(env, self.folder / "states", sid, self._obs)
        stored = Stored(sid, self.spec, observe(env, trigger), snap)
        stored.save(self.folder)
        self.stored.append(stored)


def record(
    base, spec: EpisodeSpec, folder: Path, cfg: AdvisorConfig, after_s: float
) -> list[Stored]:
    folder.mkdir(parents=True, exist_ok=True)
    env = make_env(spec, base.agent_cfg)
    rec = Recorder(base, spec, folder, cfg, after_s)
    try:
        obs, _ = env.reset(seed=spec.seed)
        rec.reset(env)
        while env.agents:
            obs, *_ = env.step(rec.act(env, obs))
    finally:
        env.close()
    return rec.stored


@dataclass
class Score:
    waiting_veh_s: float
    ev_stopped_s: float
    ped_wait_s: float
    biased: int
    changed: int


def score(  # [Exigence 8] rejeu apparié : même instantané, avec ou sans conseil
    env: CoTrafficEnv,
    base,
    stored: Stored,
    advice: Advice | None,
    horizon_s: float,
    beta: float,
    delay_s: float = 0.0,
) -> Score:
    """Replay ``stored`` with ``advice`` (activated after ``delay_s``) for ``horizon_s``."""
    env.reset(seed=stored.spec.seed)
    source = FixedSource(advice, delay_s) if advice is not None else AdviceSource()
    cfg = AdvisorConfig(beta=beta, period_s=1e9, min_gap_s=1e9, latency="measured")
    policy = AdvisedPolicy(base, source, cfg)
    policy.reset(env)
    obs = restore(env, stored.snapshot)  # [Exigence 8] repart du même instantané
    if advice is not None:
        policy._ask(env, "replay")  # the advice under test, issued at the snapshot time
    policy._last_call = env.now  # no other call during the rollout
    policy._next_periodic = 1e12
    policy._seen = {"*"}
    end = stored.snapshot.time + horizon_s
    halting0 = env.halting_sum
    ev_stopped = ped = 0.0
    while env.agents and env.now < end:
        obs, *_ = env.step(policy.act(env, obs))
        for ev in env.ev_ids:
            try:
                if env.conn.vehicle.getSpeed(ev) < 0.1:
                    ev_stopped += env.delta
            except Exception:
                pass
        ped += sum(env.ped_waiting.values()) * env.delta
    return Score(
        waiting_veh_s=(env.halting_sum - halting0) * env.delta,
        ev_stopped_s=ev_stopped,
        ped_wait_s=ped,
        biased=policy.biased_decisions,
        changed=policy.changed_decisions,
    )
