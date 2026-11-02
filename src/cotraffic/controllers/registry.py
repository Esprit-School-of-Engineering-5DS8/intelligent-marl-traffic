"""Controller names used on the command line and in experiment configs."""

from __future__ import annotations

from pathlib import Path

from cotraffic.controllers.base import Controller

BASELINES = ("ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp")
LEARNED = ("ind", "coop", "coop_eco", "coop_eco05", "coop_full", "dqn")
# the teammate's LLM team (controllers/llm_team/PROVENANCE.md):
# Max-Pressure + the team's code rules (team_rules) or + the local model (team_qwen)
TEAM = ("team_rules", "team_qwen")
# the final controller of the combined study (docs/COMBINED_PREREGISTRATION.md, frozen at
# 2c0dd1d): COOP-FULL with a bias of 4 towards Max-Pressure and EV-RULE pre-emption, built as
# scripts/combined_eval.py builds it (method hybrid_h2, beta 4)
CANDIDATE = "hybrid_h2"
# the candidate with the LLM strategist on top (llm/strategist.py, exploratory)
LLM_CANDIDATE = "hybrid_h2_llmstrat"
# built on a COOP-FULL model: their checkpoint is the one of coop_full
ON_COOP_FULL = (CANDIDATE, LLM_CANDIDATE)

# "<method>_guard": the same controller behind the shield with the spillback guard and
# detector recall (FAILURES F-012, F-014), evaluated as a family of its own.
GUARD_SUFFIX = "_guard"
GUARD_OPTIONS = {"spillback": 0.8, "recall_failed": True}


def base_method(method: str) -> str:
    return method.removesuffix(GUARD_SUFFIX)


def make_controller(method: str, checkpoint: Path | None = None, **kwargs) -> Controller:
    if method.endswith(GUARD_SUFFIX):
        controller = make_controller(base_method(method), checkpoint, **kwargs)
        if not controller.controlled:
            raise ValueError(f"{method}: SUMO signal programs do not use the shield")
        controller.agent_cfg = {**controller.agent_cfg, "shield": dict(GUARD_OPTIONS)}
        controller.name = method
        return controller
    if method == "ft":
        from cotraffic.controllers.classical import FixedTime

        return FixedTime(**kwargs)
    if method == "act":
        from cotraffic.controllers.classical import Actuated

        return Actuated()
    if method == "mp":
        from cotraffic.controllers.classical import MaxPressure

        return MaxPressure()
    if method == "ev_rule":
        from cotraffic.controllers.ev_preemption import EmergencyPreemption

        return EmergencyPreemption()
    if method == "ev_rule_mp":
        from cotraffic.controllers.ev_preemption import MaxPressurePreemption

        return MaxPressurePreemption()
    if method == "ped_rule_mp":
        from cotraffic.controllers.pedestrian_rule import PedestrianRule

        return PedestrianRule()
    if method == "random":
        from cotraffic.controllers.random_policy import RandomPolicy

        return RandomPolicy(**kwargs)
    if method in TEAM:
        from cotraffic.controllers.team import TeamController

        return TeamController(method, **kwargs)
    if method == CANDIDATE:
        from cotraffic.controllers.combined import EvRuleGuide
        from cotraffic.controllers.hybrid import HybridPolicy

        if checkpoint is None:
            raise ValueError(f"method {method!r} needs a COOP-FULL checkpoint")
        base = make_controller("coop_full", checkpoint)
        beta = float(kwargs.get("beta", 4.0))
        return HybridPolicy(base, mp_beta=beta, ev_guide=EvRuleGuide(), name=CANDIDATE)
    if method == LLM_CANDIDATE:
        from cotraffic.llm.client import Ollama
        from cotraffic.llm.settings import load_settings
        from cotraffic.llm.strategist import LlmStrategist, LlmStrategyPolicy, StrategistPrompt

        if checkpoint is None:
            raise ValueError(f"method {method!r} needs a COOP-FULL checkpoint")
        cfg = load_settings()
        strategist = LlmStrategist(Ollama(cfg.model, cfg.options), StrategistPrompt.load())
        beta = float(kwargs.get("beta", 4.0))
        return LlmStrategyPolicy(make_controller("coop_full", checkpoint), strategist, beta, method)
    if method in LEARNED or checkpoint is not None:
        from cotraffic.controllers.rl_policy import LearnedPolicy

        if checkpoint is None:
            raise ValueError(f"method {method!r} needs a checkpoint")
        return LearnedPolicy(method, checkpoint)
    raise ValueError(f"unknown method {method!r}")
