"""Language-model traffic controller with a deterministic safety fallback.

The LLM is asked once for a batch of decisions covering every intersection. Its
answer is validated, missing or invalid intersections are filled by Max-Pressure,
and every request is logged as counters on the controller. The environment's safety
shield remains the last line of defence, exactly as for the learned policies.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Mapping
from typing import Any

from cotraffic import config
from cotraffic.assistant.llm import LLMUnavailableError
from cotraffic.controllers.base import Controller
from cotraffic.controllers.classical import MaxPressure
from cotraffic.envs.observations import phase_pressures
from cotraffic.llm.providers import BaseProvider, make_provider
from cotraffic.llm.trace import LLMTracer

LOGGER = logging.getLogger("cotraffic.llm")

SYSTEM_PROMPT = """You control traffic lights at every intersection of a SUMO network.
Choose one green phase per intersection. The phases are indexed from 0; phase 0 and
phase 1 serve different approaches. Never return a yellow phase. Keep a phase that is
already serving traffic when there is no clear benefit to switching. Prefer the phase
with the largest queues and pressure, but avoid starving an approach: the environment
enforces minimum green, maximum green and anti-starvation after your decision.
Return only JSON matching the provided schema: a `phases` array with exactly one valid
phase index per intersection, in the same order as the `intersections` array."""


class LLMController(Controller):
    name = "llm"
    controlled = True
    needs_observations = False

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        interval_s: float | None = None,
        client: BaseProvider | None = None,
        max_calls: int | None = None,
        fallback: str = "mp",
        **_: Any,
    ) -> None:
        super().__init__()
        self.agent_cfg = config.load_agent("llm")
        cfg = self.agent_cfg
        self.provider_name = (
            provider
            or os.environ.get("COTRAFFIC_LLM_PROVIDER")
            or str(cfg.get("provider", "groq"))
        )
        self.model_name = model or os.environ.get("COTRAFFIC_LLM_MODEL") or cfg.get("model")
        self.interval_s = float(
            interval_s
            if interval_s is not None
            else os.environ.get("COTRAFFIC_LLM_INTERVAL_S", cfg.get("call_interval_s", 30))
        )
        self.timeout_s = float(
            os.environ.get("COTRAFFIC_LLM_TIMEOUT", cfg.get("timeout_s", 30))
        )
        self.attempts = int(os.environ.get("COTRAFFIC_LLM_ATTEMPTS", cfg.get("attempts", 2)))
        self.max_tokens = int(os.environ.get("COTRAFFIC_LLM_MAX_TOKENS", cfg.get("max_tokens", 700)))
        configured_max = os.environ.get("COTRAFFIC_LLM_MAX_CALLS", cfg.get("max_calls", 0))
        self.max_calls = int(max_calls if max_calls is not None else configured_max or 0)
        self.fallback_name = fallback or str(cfg.get("fallback", "mp"))
        if self.fallback_name != "mp":
            raise ValueError("the LLM controller currently supports fallback='mp' only")

        self._client = client
        self._client_error: str | None = None
        self._fallback = MaxPressure()
        self._last_actions: dict[str, int] = {}
        self._next_call = -1.0
        self._retry_after = -1.0
        self._failures = 0
        self._logged_unavailable = False
        self._logged_max_calls = False
        self._metrics: dict[str, Any] = {}
        self._tracer: LLMTracer | None = None
        self._trace_summary_written = False

    def reset(self, env) -> None:
        self._last_actions = {}
        self._next_call = -1.0
        self._retry_after = -1.0
        self._failures = 0
        self._logged_unavailable = False
        self._logged_max_calls = False
        run_id = str(
            getattr(env, "run_id", None)
            or f"adhoc-{time.strftime('%Y%m%d-%H%M%S')}"
        )
        self._tracer = LLMTracer(
            run_id,
            root=getattr(env, "trace_dir", None),
            enabled=os.environ.get("COTRAFFIC_LLM_TRACE", "1").lower()
            not in ("", "0", "false", "no", "off"),
        )
        self._trace_summary_written = False
        self._metrics = {
            "llm_provider": self.provider_name,
            "llm_model": "",
            "llm_available": 0,
            "llm_calls": 0,
            "llm_success": 0,
            "llm_partial": 0,
            "llm_fallbacks": 0,
            "llm_cache_hits": 0,
            "llm_errors": 0,
            "llm_budget_hit": 0,
            "llm_interval_s": self.interval_s,
            "llm_max_calls": self.max_calls,
            "llm_latency_ms_total": 0.0,
            "llm_latency_ms_max": 0.0,
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "llm_last_error": "",
            "llm_trace_path": str(self._tracer.path) if self._tracer else "",
        }
        if self._client is None:
            try:
                self._client = make_provider(
                    provider=self.provider_name,
                    model=self.model_name,
                    timeout_s=self.timeout_s,
                    attempts=self.attempts,
                    tracer=self._tracer,
                )
            except LLMUnavailableError as error:
                self._client_error = str(error)
                self._metrics["llm_last_error"] = self._client_error[:200]
        if self._client is not None:
            self._metrics["llm_available"] = 1
            self._metrics["llm_model"] = getattr(self._client, "model", "") or self.model_name or ""

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        now = float(getattr(env, "now", 0.0))
        agents = sorted(env.intersections)
        if self._last_actions and now < self._next_call:
            self._metrics["llm_cache_hits"] += 1
            self._trace_event({"event": "cache_hit", "sim_time_s": now, "agents": len(agents)})
            return {agent: int(self._last_actions.get(agent, 0)) for agent in agents}

        fallback = self._fallback.act(env, obs)
        if self._client is None:
            if not self._logged_unavailable:
                LOGGER.warning("LLM unavailable: %s; using MaxPressure", self._client_error)
                self._logged_unavailable = True
            self._metrics["llm_fallbacks"] += 1
            self._trace_event(
                {
                    "event": "fallback",
                    "reason": "unavailable",
                    "sim_time_s": now,
                    "error": self._client_error or "",
                }
            )
            return fallback
        if now < self._retry_after:
            self._metrics["llm_fallbacks"] += 1
            self._trace_event(
                {"event": "fallback", "reason": "retry_backoff", "sim_time_s": now}
            )
            return fallback
        if self.max_calls and self._metrics["llm_calls"] >= self.max_calls:
            if not self._logged_max_calls:
                LOGGER.warning(
                    "max_calls=%d reached at sim=%.1fs; the rest of this episode runs on "
                    "MaxPressure, so its metrics describe the fallback, not the LLM",
                    self.max_calls,
                    now,
                )
                self._logged_max_calls = True
            self._metrics["llm_budget_hit"] = 1
            self._metrics["llm_fallbacks"] += 1
            self._trace_event(
                {"event": "fallback", "reason": "budget", "sim_time_s": now}
            )
            return fallback

        call_number = self._metrics["llm_calls"] + 1
        LOGGER.info(
            "call %d start sim=%.1fs agents=%d provider=%s model=%s",
            call_number,
            now,
            len(agents),
            self.provider_name,
            getattr(self._client, "model", None) or self.model_name or "configured",
        )
        try:
            state = self._state(env, agents)
            schema = self._schema(env, agents)
            result = self._client.chat_json(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(state, separators=(",", ":"))},
                ],
                schema,
                max_tokens=self.max_tokens,
            )
            actions, missing = self._parse(result.data, env, agents)
            if not actions:
                raise ValueError("the model returned no valid intersection decision")
            for agent in agents:
                actions.setdefault(agent, int(fallback.get(agent, 0)))
            self._last_actions = actions
            self._next_call = now + self.interval_s
            self._failures = 0
            self._metrics["llm_calls"] += 1
            self._metrics["llm_success"] += 1
            self._metrics["llm_partial"] += int(bool(missing))
            self._metrics["llm_latency_ms_total"] += result.latency_ms
            self._metrics["llm_latency_ms_max"] = max(
                self._metrics["llm_latency_ms_max"], result.latency_ms
            )
            self._metrics["llm_prompt_tokens"] += int(result.prompt_tokens or 0)
            self._metrics["llm_completion_tokens"] += int(result.completion_tokens or 0)
            self._trace_event(
                {
                    "event": "decision",
                    "sim_time_s": now,
                    "call": call_number,
                    "actions": {a: int(v) for a, v in actions.items()},
                    "missing": int(missing),
                    "latency_ms": round(float(result.latency_ms), 2),
                    "prompt_tokens": int(result.prompt_tokens or 0),
                    "completion_tokens": int(result.completion_tokens or 0),
                }
            )
            LOGGER.info(
                "call %d ok latency=%.0fms tokens=%s/%s partial=%d phases=%s",
                call_number,
                result.latency_ms,
                result.prompt_tokens if result.prompt_tokens is not None else "?",
                result.completion_tokens if result.completion_tokens is not None else "?",
                len(agents) - len(actions),
                actions,
            )
            return {agent: int(actions[agent]) for agent in agents}
        except Exception as error:  # noqa: BLE001 - any provider/schema failure must fall back
            self._metrics["llm_calls"] += 1
            self._metrics["llm_errors"] += 1
            self._metrics["llm_fallbacks"] += 1
            self._metrics["llm_last_error"] = self._safe_error(error)
            self._failures += 1
            backoff = min(300.0, max(self.interval_s, 10.0) * (2 ** (self._failures - 1)))
            self._retry_after = now + backoff
            self._trace_event(
                {
                    "event": "fallback",
                    "reason": "error",
                    "sim_time_s": now,
                    "call": call_number,
                    "error": self._metrics["llm_last_error"],
                    "backoff_s": round(backoff, 1),
                }
            )
            LOGGER.warning(
                "call %d failed (sim=%.1fs): %s; MaxPressure, retry in %.0fs",
                call_number,
                now,
                self._metrics["llm_last_error"],
                backoff,
            )
            return fallback

    def parameters(self) -> dict[str, Any]:
        return {
            "controller": "llm",
            "provider": self.provider_name,
            "model": getattr(self._client, "model", None) or self.model_name or "",
            "interval_s": self.interval_s,
            "timeout_s": self.timeout_s,
            "attempts": self.attempts,
            "max_tokens": self.max_tokens,
            "max_calls": self.max_calls,
            "fallback": self.fallback_name,
            "safety_shield": True,
        }

    def metrics(self) -> dict[str, Any]:
        calls = int(self._metrics.get("llm_calls", 0))
        success = int(self._metrics.get("llm_success", 0))
        errors = int(self._metrics.get("llm_errors", 0))
        total = float(self._metrics.get("llm_latency_ms_total", 0.0))
        status = self._status(success, errors)
        if self._tracer is not None and not self._trace_summary_written:
            self._tracer.write_summary()
            self._trace_summary_written = True
        trace = self._tracer.summary() if self._tracer is not None else {}
        return {
            **self._metrics,
            "llm_trace_path": trace.get("trace_path", self._metrics.get("llm_trace_path", "")),
            "llm_trace_calls": trace.get("calls", 0),
            # A round is one decision the model was asked for, not one simulation step:
            # the steps between calls are cache hits, and a fallback step (a retry backoff
            # or the tail after the budget) is not a round either.
            "llm_rounds": calls,
            "llm_coverage_pct": round(100.0 * success / calls, 1) if calls else 0.0,
            "llm_latency_ms_mean": round(total / calls, 2) if calls else 0.0,
            "llm_latency_ms_max": round(float(self._metrics.get("llm_latency_ms_max", 0.0)), 2),
            "llm_status": status,
            "llm_valid": int(status == "ok"),
        }

    def _status(self, success: int, errors: int) -> str:
        """Whether an episode's metrics describe the LLM or its fallback.

        ``ok`` is the only interpretable state: the provider was ready and the model
        answered *every* round it was asked in. ``degraded`` means some calls failed
        (quota, network, invalid JSON), so part of the episode ran on Max-Pressure and
        the numbers are the fallback's, not the model's; ``budget`` means the
        per-episode call cap was reached and the tail of the episode is fallback too;
        ``unavailable`` means no call was ever possible (no API key); ``silent`` means
        the provider was ready but the model never answered once. Only ``ok`` is a
        result about the LLM - the others are results about Max-Pressure with an LLM
        attempt in front of it, and the aggregate drops them.
        """
        if not int(self._metrics.get("llm_available", 0)):
            return "unavailable"
        if errors:
            return "degraded"
        if self._metrics.get("llm_budget_hit"):
            return "budget"
        if not success:
            return "silent"
        return "ok"

    # ------------------------------------------------------------------ prompt state
    def _state(self, env, agents: list[str]) -> dict[str, Any]:
        intersections = []
        for agent in agents:
            inter = env.intersections[agent]
            pressures = phase_pressures(inter, env.meas)
            phases = []
            for phase, lanes in enumerate(inter.phase_lanes):
                phases.append(
                    {
                        "phase": phase,
                        "queue_on_green": round(float(env.meas.queue(lanes)), 3),
                        "pressure": round(float(pressures[phase]), 3),
                    }
                )
            ev = getattr(env, "ev_info", {}).get(agent, {})
            intersections.append(
                {
                    "tls_id": agent,
                    "current_phase": int(inter.phase),
                    "green_elapsed_s": round(float(inter.green_elapsed(env.now)), 1),
                    "in_yellow": bool(inter.in_yellow),
                    "phases": phases,
                    "pedestrians_waiting": round(
                        float(sum(env.ped_waiting.get(crossing, 0.0) for crossing in inter.crossings)),
                        1,
                    ),
                    "emergency_approaching": bool(ev),
                }
            )
        return {
            "sim_time_s": round(float(env.now), 1),
            "decision_interval_s": self.interval_s,
            "intersections": intersections,
        }

    def _schema(self, env, agents: list[str]) -> dict[str, Any]:
        max_phase = max(int(env.action_space(agent).n) for agent in agents) - 1
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["phases"],
            "properties": {
                "phases": {
                    "type": "array",
                    "items": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": max(0, max_phase),
                    },
                },
            },
        }

    def _parse(
        self, data: Mapping[str, Any], env, agents: list[str]
    ) -> tuple[dict[str, int], int]:
        actions: dict[str, int] = {}
        raw = data.get("phases")
        if isinstance(raw, list):
            for agent, phase in zip(agents, raw, strict=False):
                if (
                    isinstance(phase, int)
                    and not isinstance(phase, bool)
                    and 0 <= phase < int(env.action_space(agent).n)
                ):
                    actions[agent] = phase
        else:
            raw = data.get("decisions")
            if not isinstance(raw, list):
                raise TypeError("missing phases array")
            for item in raw:
                if not isinstance(item, dict):
                    continue
                agent = item.get("tls_id")
                phase = item.get("phase")
                if agent not in agents or not isinstance(phase, int) or isinstance(phase, bool):
                    continue
                if not 0 <= phase < int(env.action_space(agent).n):
                    continue
                actions[agent] = phase
        return actions, len(agents) - len(actions)

    def _trace_event(self, event: dict[str, Any]) -> None:
        if self._tracer is not None:
            self._tracer.record(
                {
                    "provider": self.provider_name,
                    "model": getattr(self._client, "model", None) or self.model_name or "",
                    **event,
                }
            )

    def _safe_error(self, error: Exception) -> str:
        text = f"{type(error).__name__}: {error}"
        client = self._client
        key = getattr(client, "api_key", "") if client is not None else ""
        if key:
            text = text.replace(key, "***")
        return text[:200]


def make_llm_controller(**kwargs: Any) -> LLMController:
    return LLMController(**kwargs)
