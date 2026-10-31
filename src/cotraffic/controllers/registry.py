"""Controller names used on the command line and in experiment configs."""

from __future__ import annotations

from pathlib import Path

from cotraffic.controllers.base import Controller

BASELINES = ("ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp")
LLM = ("llm",)
NO_CHECKPOINT = BASELINES + LLM


def _trainable_recipe_ids() -> tuple[str, ...]:
    """Trainable learned agents = the editable recipes themselves (rl templates and
    every rl_<hash> profile frozen by the training editor). Legacy preset ids are gone."""
    from cotraffic import recipes

    out: list[str] = []
    for entry in recipes.list_recipes():
        rid = entry.get("id", "")
        if entry.get("error"):
            continue
        kind = entry.get("source")
        trainable = entry.get("trainable")
        if kind == "recipe" and trainable and rid not in ("base", "llm"):
            out.append(rid)
    return tuple(out)


LEARNED = _trainable_recipe_ids()


def make_controller(method: str, checkpoint: Path | None = None, **kwargs) -> Controller:
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
    if method == "llm":
        from cotraffic.controllers.llm import LLMController

        return LLMController(**kwargs)
    if method in LEARNED or checkpoint is not None:
        from cotraffic.controllers.rl_policy import LearnedPolicy

        if checkpoint is None:
            raise ValueError(f"method {method!r} needs a checkpoint")
        return LearnedPolicy(method, checkpoint)
    raise ValueError(f"unknown method {method!r}")
