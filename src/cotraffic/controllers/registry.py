"""Controller names used on the command line and in experiment configs."""

from __future__ import annotations

from pathlib import Path

from cotraffic.controllers.base import Controller

BASELINES = ("ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp")
LEARNED = ("ind", "coop", "coop_eco", "coop_eco05", "coop_full", "dqn")

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
    if method in LEARNED or checkpoint is not None:
        from cotraffic.controllers.rl_policy import LearnedPolicy

        if checkpoint is None:
            raise ValueError(f"method {method!r} needs a checkpoint")
        return LearnedPolicy(method, checkpoint)
    raise ValueError(f"unknown method {method!r}")
