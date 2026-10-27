"""CoTraffic adapter for the LLM team of the teammate's branch (see PROVENANCE.md).

Two controllers, both Max-Pressure plus the team's typed directives, and both behind our
safety shield (the environment applies it to every requested phase):

* ``team_rules``: the mock backend. No LLM: the roles answer "no directive" and the
  team's code rules act alone (emergency pre-emption plan, pedestrian windows).
* ``team_qwen``: the same team with our local model (qwen2.5:3b through Ollama). The
  answer of a call acts only once its measured latency has passed in simulated time, as
  for our advisor (llm/advised.py); the source applies it at once, with the simulation
  paused during the call.

Three adaptations, all in this file:

* ``TeamEnvView``: the readings the team's snapshot expects and our environment does not
  compute (EV routes, per-lane and per-crossing waiting times), read from SUMO at
  decision time, the moment the source's environment computed them.
* ``LocalTeamClient``: the team's client over our Ollama client, in JSON mode like the
  source's hosted provider (schema sent as a system message, checked after the reply).
* ``LatentSupervisor``: the source's supervisor with answers held back for their latency.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import partial
from typing import Any

import numpy as np

from cotraffic.assistant.llm import validate
from cotraffic.controllers.llm_team.agent import PROMPTS_DIR, AgentCall, LLMAgent
from cotraffic.controllers.llm_team.client import MockClient, TeamResponse
from cotraffic.controllers.llm_team.controller import LLMTeamController
from cotraffic.controllers.llm_team.schemas import SchemaError
from cotraffic.controllers.llm_team.supervisor import ROLE_ORDER, Supervisor
from cotraffic.envs.ev import read_ev_states
from cotraffic.llm.client import Ollama, Options
from cotraffic.llm.settings import load_settings

TEAM_METHODS = ("team_rules", "team_qwen")
# the team's prompts and snapshots are longer than our advisor's: about 3k tokens on grid4x4
TEAM_NUM_CTX = 8192
SCHEMA_NOTE = "Reply with a JSON object that validates against this JSON Schema:\n"


def prompt_version() -> str:
    """Hash of the three role prompts, stored with every result row."""
    text = "".join((PROMPTS_DIR / f"{role}.md").read_text(encoding="utf-8") for role in ROLE_ORDER)
    return "team-v2/" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def delay_for(mode: str, latency_s: float) -> float:
    """Simulated delay before an answer acts (same modes as AdvisorConfig.latency)."""
    if mode == "measured":
        return latency_s
    if mode == "zero":
        return 0.0
    if mode == "double":
        return 2.0 * latency_s
    if mode.startswith("fixed:"):
        return float(mode.split(":", 1)[1])
    raise ValueError(f"unknown latency mode {mode!r}")


# ---------------------------------------------------------------- environment view
class _MeasView:
    def __init__(self, meas, waiting: dict[str, float]):
        self._meas = meas
        self.waiting = waiting

    def __getattr__(self, name: str) -> Any:
        return getattr(self._meas, name)


def ped_wait_sums(env) -> dict[str, float]:
    """Waiting time of the pedestrians in front of each crossing (source: traffic_env.py)."""
    sums: dict[str, float] = defaultdict(float)
    person = env.conn.person
    for pid in env.person_ids:
        waiting = person.getWaitingTime(pid)
        if waiting > 0 and person.getRoadID(pid) in env.walkingareas:
            nxt = person.getNextEdge(pid)
            if nxt in env.crossing_owner:
                sums[nxt] += waiting
    return sums


class TeamEnvView:
    """Our environment, plus ``ev_states``, ``ped_wait_sum`` and ``meas.waiting``."""

    def __init__(self, env):
        self._env = env
        conn = env.conn
        lanes = sorted({ln for inter in env.intersections.values() for ln in inter.in_lanes})
        self.meas = _MeasView(env.meas, {ln: float(conn.lane.getWaitingTime(ln)) for ln in lanes})
        self.ev_states = read_ev_states(conn, env.ev_ids)
        self.ped_wait_sum = ped_wait_sums(env)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._env, name)


# ---------------------------------------------------------------- local model
class LocalTeamClient:
    """The team's client protocol (complete -> TeamResponse) over our local Ollama model."""

    name = "ollama"

    def __init__(self, model: str, options: Options):
        self.model = model
        self.options = options

    def complete(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        effort: str | None = None,
        max_tokens: int = 700,
    ) -> TeamResponse:
        messages = [
            {"role": "system", "content": system},
            {"role": "system", "content": SCHEMA_NOTE + json.dumps(schema, separators=(",", ":"))},
            {"role": "user", "content": user},
        ]
        client = Ollama(self.model, replace(self.options, num_predict=int(max_tokens)))
        reply = client.chat(messages, "json")  # JSON mode, as the source's json_object
        try:
            value = json.loads(reply.text)
        except ValueError as err:
            raise SchemaError(f"not JSON: {reply.text[:80]!r}") from err
        problems = validate(value, schema)
        if problems:
            raise SchemaError("; ".join(problems[:3]))
        return TeamResponse(
            parsed=value,
            raw=reply.text,
            latency_s=reply.latency_s,
            tokens_in=reply.prompt_tokens,
            tokens_out=reply.output_tokens,
            model=self.model,
        )


# ---------------------------------------------------------------- latency
@dataclass
class _Pending:
    role: str
    call: AgentCall
    asked_at: float
    latency_s: float
    ready_at: float


class LatentSupervisor(Supervisor):
    """The source's supervisor; an answer is reviewed, arbitrated and installed only at the
    first decision after its delay, on the state of that moment. A role is not asked again
    while its answer is on the way."""

    def __init__(self, *args: Any, latency: str = "measured", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.latency = latency
        self.pending: list[_Pending] = []
        self.delays: list[float] = []
        self.delivered = 0

    def _execute(self, due, t, states, snapshot, messages, complexity, evs, pedestrians):
        waiting = {p.role for p in self.pending}
        roles = [r for r in due if r in self.agents and r not in waiting]
        if roles:
            self._request(roles, t, snapshot, messages, complexity, evs, pedestrians)
        return self._deliver(t, states, snapshot, complexity)

    def _request(self, roles, t, snapshot, messages, complexity, evs, pedestrians) -> None:
        if self.config.max_calls > 0:
            remaining = max(0, self.config.max_calls - self.stats["calls"] - len(self.pending))
            if len(roles) > remaining:
                self.stats["skipped_budget"] += len(roles) - remaining
                roles = roles[:remaining]
        efforts = {role: self._effort_for(complexity, role, evs, pedestrians) for role in roles}
        for role in roles:
            self._last_run[role] = t

        def ask(role: str) -> tuple[AgentCall, float]:
            # the model call alone: the role's code review runs when the answer arrives
            start = time.perf_counter()
            call = LLMAgent.ask(self.agents[role], t, snapshot, messages, effort=efforts[role])
            return call, time.perf_counter() - start

        started = time.perf_counter()
        workers = max(1, int(self.config.parallel_workers))
        if len(roles) > 1 and self.config.parallel and workers > 1:
            with ThreadPoolExecutor(max_workers=min(workers, len(roles))) as pool:
                answers = dict(zip(roles, pool.map(ask, roles), strict=True))
        else:
            answers = {role: ask(role) for role in roles}
        self.wall_time_s += time.perf_counter() - started
        for role in roles:
            call, latency = answers[role]
            delay = delay_for(self.latency, latency)
            self.pending.append(_Pending(role, call, t, latency, t + delay))

    def _deliver(self, t, states, snapshot, complexity):
        ready = [p for p in self.pending if p.ready_at <= t]
        self.pending = [p for p in self.pending if p.ready_at > t]
        results = []
        for p in sorted(ready, key=lambda p: (p.asked_at, ROLE_ORDER.index(p.role))):
            agent = self.agents[p.role]
            call = agent.review(t, snapshot, p.call) if hasattr(agent, "review") else p.call
            self.delays.append(t - p.asked_at)
            self.delivered += 1
            if self.logger is not None:
                self.logger.log(
                    {
                        "t": t,
                        "agent": p.role,
                        "event": "delivered",
                        "asked_at": p.asked_at,
                        "latency_s": round(p.latency_s, 3),
                        "delay_s": round(t - p.asked_at, 3),
                    }
                )
            # from here on, as Supervisor._execute (source lines 541-562)
            result, envelope_error = self._submit(p.role, call, t, states, complexity)
            self._log(t, call, result, envelope_error, complexity)
            if result is None:
                continue
            results.append(result)
            self.blackboard.post_message(
                "arbiter_result",
                "arbiter",
                t,
                payload=result.feedback_payload(),
                ttl_s=self.config.feedback_ttl_s,
            )
            for alert in result.alerts:
                self.blackboard.post_message(
                    str(alert.get("kind", "alert")),
                    p.role,
                    t,
                    payload={k: v for k, v in alert.items() if k != "kind"},
                    ttl_s=self.config.feedback_ttl_s,
                )
        return results


# ---------------------------------------------------------------- controller
class TeamController(LLMTeamController):
    """``team_rules`` or ``team_qwen``: the source's controller with a local client."""

    def __init__(
        self,
        method: str = "team_rules",
        model: str | None = None,
        latency: str | None = None,
        options: Options | None = None,
        log_path: str = "",
        client: Any = None,
        **_: Any,
    ) -> None:
        if method not in TEAM_METHODS:
            raise ValueError(f"unknown team method {method!r}; expected one of {TEAM_METHODS}")
        settings = load_settings()
        cfg_timeout = 90.0  # configs/agents/llm_team.yaml (timeout_s)
        if method == "team_rules":
            client, model, latency = client or MockClient(), "mock", latency or "zero"
        else:
            model = model or settings.model
            options = options or replace(
                settings.options, num_ctx=TEAM_NUM_CTX, timeout_s=cfg_timeout
            )
            client = client or LocalTeamClient(model, options)
            latency = latency or settings.advisor.latency
        super().__init__(
            provider="mock" if method == "team_rules" else "ollama",
            model=model,
            backend="mock" if method == "team_rules" else "ollama",
            client=client,
            max_calls=0,
        )
        self.name = method
        self.options = options
        self.latency_mode = latency
        self.log_path = log_path
        self.supervisor_class = partial(LatentSupervisor, latency=latency)
        # a local model costs nothing per token
        self.supervisor_cfg = replace(
            self.supervisor_cfg,
            price_input_per_1m=0.0,
            price_output_per_1m=0.0,
            price_cached_per_1m=0.0,
        )

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        view = env if hasattr(env, "ev_states") else TeamEnvView(env)
        return super().act(view, obs)

    def metrics(self) -> dict[str, Any]:
        out = super().metrics()
        sup = self._supervisor
        delays = list(getattr(sup, "delays", []))
        out.update(
            {
                "team_latency_mode": self.latency_mode,
                "team_answers_delivered": int(getattr(sup, "delivered", 0)),
                "team_answers_dropped": len(getattr(sup, "pending", [])),
                "team_delay_mean_s": round(float(np.mean(delays)), 3) if delays else 0.0,
                "team_delay_p95_s": round(float(np.percentile(delays, 95)), 3) if delays else 0.0,
            }
        )
        return out
