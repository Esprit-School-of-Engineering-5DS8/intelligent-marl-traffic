"""Three-role LLM team on top of the integration environment."""

from __future__ import annotations

import os
import time
from typing import Any

from cotraffic import config
from cotraffic.assistant.llm import LLMUnavailableError
from cotraffic.controllers.base import Controller
from cotraffic.controllers.classical import MaxPressure
from cotraffic.controllers.llm_team.arbiter import Arbiter
from cotraffic.controllers.llm_team.blackboard import Blackboard
from cotraffic.controllers.llm_team.client import CallLogger, make_team_client
from cotraffic.controllers.llm_team.detector import QueueAlertDetector
from cotraffic.controllers.llm_team.directive_layer import DirectiveLayer
from cotraffic.controllers.llm_team.roles.emergency import EmergencyAgent
from cotraffic.controllers.llm_team.roles.operator import OperatorAgent
from cotraffic.controllers.llm_team.roles.pedestrian import PedestrianAgent
from cotraffic.controllers.llm_team.snapshot import (
    build_evs,
    build_pedestrians,
    build_phase_maps,
    build_states,
)
from cotraffic.controllers.llm_team.supervisor import Supervisor, SupervisorConfig


class LLMTeamController(Controller):
    name = "llm_team"
    controlled = True
    needs_observations = False
    supervisor_class = Supervisor  # CoTraffic: hook for the latency model (team.py)

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        backend: str | None = None,
        client: Any = None,
        max_calls: int | None = None,
        cache_path: str | None = None,
        **_: Any,
    ) -> None:
        super().__init__()
        self.agent_cfg = config.load_agent("llm_team")
        cfg = self.agent_cfg
        supervisor_cfg = dict(cfg.get("supervisor") or {})
        tokens = dict(cfg.get("tokens") or {})
        self.provider_name = (
            provider
            or os.environ.get("COTRAFFIC_LLM_PROVIDER")
            or str(cfg.get("provider", "opencode"))
        )
        self.model_name = model or os.environ.get("COTRAFFIC_LLM_MODEL") or cfg.get("model")
        self.backend = (
            backend
            or os.environ.get("COTRAFFIC_LLM_BACKEND")
            or str(cfg.get("backend", "opencode"))
        )
        self.timeout_s = float(
            os.environ.get("COTRAFFIC_LLM_TIMEOUT", cfg.get("timeout_s", 60))
        )
        self.attempts = int(os.environ.get("COTRAFFIC_LLM_ATTEMPTS", cfg.get("attempts", 1)))
        self.max_retries = int(cfg.get("max_retries", 1))
        configured_max = os.environ.get("COTRAFFIC_LLM_MAX_CALLS", cfg.get("max_calls", 0))
        self.max_calls = int(max_calls if max_calls is not None else configured_max or 0)
        self.cache_path = (
            cache_path
            or os.environ.get("COTRAFFIC_LLM_CACHE")
            or str(cfg.get("cache_path", ""))
        )
        self.log_path = os.environ.get("COTRAFFIC_LLM_LOG_PATH") or str(
            cfg.get("log_path", "")
        )
        self.max_tokens = {
            "operator": int(tokens.get("operator", 300)),
            "emergency": int(tokens.get("emergency", 500)),
            "pedestrian": int(tokens.get("pedestrian", 300)),
        }
        snapshot_cfg = dict(cfg.get("snapshot") or {})
        pricing_cfg = dict(cfg.get("pricing") or {})
        self.supervisor_cfg = SupervisorConfig(
            delta_s=float(supervisor_cfg.get("delta_s", 30.0)),
            quiet_delta_s=float(supervisor_cfg.get("quiet_delta_s", 60.0)),
            congested_delta_s=float(supervisor_cfg.get("congested_delta_s", 20.0)),
            ev_replan_s=float(supervisor_cfg.get("ev_replan_s", 60.0)),
            pedestrian_interval_s=float(supervisor_cfg.get("pedestrian_interval_s", 30.0)),
            feedback_ttl_s=float(supervisor_cfg.get("feedback_ttl_s", 60.0)),
            max_calls=self.max_calls,
            quiet_queue_threshold=int(supervisor_cfg.get("quiet_queue_threshold", 8)),
            congested_queue_threshold=int(
                supervisor_cfg.get("congested_queue_threshold", 15)
            ),
            base_effort=str(supervisor_cfg.get("base_effort", "")),
            escalate_effort=str(supervisor_cfg.get("escalate_effort", "low")),
            ev_event_triggers=bool(supervisor_cfg.get("ev_event_triggers", True)),
            ev_event_min_gap_s=float(supervisor_cfg.get("ev_event_min_gap_s", 5.0)),
            ev_eta_thresholds=tuple(
                float(value)
                for value in supervisor_cfg.get("ev_eta_thresholds") or ()
            ),
            ped_trigger_wait_s=float(supervisor_cfg.get("ped_trigger_wait_s", 20.0)),
            ped_event_min_gap_s=float(supervisor_cfg.get("ped_event_min_gap_s", 20.0)),
            ped_group_min_gap_s=float(
                supervisor_cfg.get("ped_group_min_gap_s", 30.0)
            ),
            parallel=bool(supervisor_cfg.get("parallel", True)),
            parallel_workers=int(supervisor_cfg.get("parallel_workers", 3)),
            max_alerts=int(snapshot_cfg.get("max_alerts", 5)),
            max_blackboard_messages=int(snapshot_cfg.get("max_blackboard", 6)),
            ev_horizon_s=float(snapshot_cfg.get("ev_horizon_s", 60.0)),
            ev_lookahead=int(snapshot_cfg.get("ev_lookahead", 3)),
            price_input_per_1m=float(pricing_cfg.get("input_per_1m", 0.0)),
            price_output_per_1m=float(pricing_cfg.get("output_per_1m", 0.0)),
            price_cached_per_1m=float(pricing_cfg.get("cached_per_1m", 0.0)),
        )
        self._client = client
        self._client_error: str | None = None
        self._supervisor: Supervisor | None = None
        self._layer = DirectiveLayer()
        self._base = MaxPressure()
        self._phase_maps = {}
        self._metrics: dict[str, Any] = {}
        self.preemptions = 0

    def reset(self, env) -> None:
        self._phase_maps = build_phase_maps(env)
        self._layer = DirectiveLayer()
        self._base = MaxPressure()
        self.preemptions = 0
        self._metrics = {
            "llm_team_provider": self.provider_name,
            "llm_team_model": "",
            "llm_team_backend": self.backend,
            "llm_team_available": 0,
            "llm_team_fallbacks": 0,
            "llm_team_directives": 0,
            "llm_team_guard_events": 0,
            "llm_team_last_error": "",
            "llm_team_wall_time_s": 0.0,
        }
        self._supervisor = None
        if self._client is None:
            try:
                self._client = make_team_client(
                    provider_name=self.provider_name,
                    model=self.model_name,
                    timeout_s=self.timeout_s,
                    attempts=self.attempts,
                    backend=self.backend,
                    cache_path=self.cache_path,
                )
            except (LLMUnavailableError, ValueError) as error:
                self._client_error = str(error)
                self._metrics["llm_team_last_error"] = self._client_error[:200]
                return
        self._metrics["llm_team_available"] = 1
        self._metrics["llm_team_model"] = getattr(self._client, "model", "") or ""
        neighbors = {
            tid: {side: link[0] for side, link in links.items()}
            for tid, links in getattr(env, "neighbour_links", {}).items()
        }
        self._supervisor = self.supervisor_class(
            agents={
                "operator": OperatorAgent(
                    self._client,
                    max_retries=self.max_retries,
                    max_tokens=self.max_tokens["operator"],
                ),
                "emergency": EmergencyAgent(
                    self._client,
                    max_retries=self.max_retries,
                    phase_maps=self._phase_maps,
                    max_tokens=self.max_tokens["emergency"],
                ),
                "pedestrian": PedestrianAgent(
                    self._client,
                    max_retries=self.max_retries,
                    max_tokens=self.max_tokens["pedestrian"],
                ),
            },
            arbiter=Arbiter(self._phase_maps),
            blackboard=Blackboard(),
            config=self.supervisor_cfg,
            logger=CallLogger(self.log_path or None),
            neighbors=neighbors,
            pedestrian_trigger=True,
            network=str(getattr(env, "network", "")),
            phase_maps=self._phase_maps,
        )
        self._detector = QueueAlertDetector()

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        base = self._base.act(env, obs)
        if self._supervisor is None:
            self._metrics["llm_team_fallbacks"] = (
                self._metrics.get("llm_team_fallbacks", 0) + 1
            )
            return base
        now = float(getattr(env, "now", 0.0))
        states = build_states(env, self._phase_maps)
        evs = build_evs(env)
        pedestrians = build_pedestrians(env, self._phase_maps)
        new_alerts = self._detector.update(states, now)
        active_alerts = [alert.to_dict() for alert in self._detector.active(now)]
        force_roles = ["operator"] if new_alerts else []
        if new_alerts and evs:
            force_roles.append("emergency")
        started = time.perf_counter()
        try:
            results = self._supervisor.tick(
                now,
                states,
                evs,
                active_alerts,
                pedestrians,
                tuple(force_roles),
            )
            for result in results:
                self._layer.install(result.accepted, now)
                self._metrics["llm_team_directives"] += len(result.accepted)
                self.preemptions += sum(
                    1 for directive in result.accepted if directive.type == "preempt"
                )
        except Exception as error:  # noqa: BLE001 - the team must degrade, not crash
            self._metrics["llm_team_last_error"] = f"{type(error).__name__}: {error}"[:200]
            self._metrics["llm_team_fallbacks"] = (
                self._metrics.get("llm_team_fallbacks", 0) + 1
            )
        finally:
            self._metrics["llm_team_wall_time_s"] += time.perf_counter() - started
        actions: dict[str, int] = {}
        for tid, inter in env.intersections.items():
            state = states.get(tid) or {}
            action = int(base.get(tid, inter.phase))
            actions[tid] = int(self._layer.apply(tid, state, action, now))
        events = self._layer.drain_events()
        if events:
            self._metrics["llm_team_guard_events"] += len(events)
        return actions

    def metrics(self) -> dict[str, Any]:
        team = self._supervisor.metrics() if self._supervisor is not None else {}
        wall = float(self._metrics.get("llm_team_wall_time_s", 0.0))
        return {
            **self._metrics,
            **team,
            "llm_team_fallbacks": int(team.get("llm_team_fallbacks", 0))
            + int(self._metrics.get("llm_team_fallbacks", 0)),
            "llm_team_wall_time_s": round(wall, 3),
        }


def make_llm_team_controller(**kwargs: Any) -> LLMTeamController:
    return LLMTeamController(**kwargs)
