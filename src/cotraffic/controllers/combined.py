"""COOP-FULL guided during emergencies: the combinations A' (bias) and B' (switch).

A guide says, at each decision, which junctions should serve an emergency vehicle and with
which phase. Two guides, neither uses a language model:

* ``TeamGuide``: the teammate's emergency rules (controllers/llm_team, PROVENANCE.md),
  i.e. the team on the mock backend with no base controller of its own: a junction is
  guided only while one of the team's pre-emption windows holds it;
* ``EvRuleGuide``: our EV-RULE (the vehicle's phase within ``ev_preemption_range_m``, as
  EV-RULE-MP), the control: does a gain come from the teammate's rules or from any
  pre-emption?

Two ways to apply a guide to COOP-FULL, both before our shield:

* ``bias`` (A'): ``+ beta`` on the guided phase of the PPO logits, as our advisor does with
  a full-strength advice (llm/advised.py); beta is tuned on the validation seed;
* ``switch`` (B'): at the guided junctions only, the guided phase replaces PPO's.

Without an emergency vehicle no junction is guided, and the policy is COOP-FULL itself.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from cotraffic.controllers.base import Controller
from cotraffic.controllers.ev_preemption import approaching, phase_for
from cotraffic.controllers.team import TeamController

MODES = ("bias", "switch")


class _NoOpinion(Controller):
    """Base of the team inside a guide: requests nothing, so that the team's directive
    layer returns a phase only where a directive (here, a pre-emption) holds it."""

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        return dict.fromkeys(env.intersections, -1)


class _GuideTeam(TeamController):
    def reset(self, env) -> None:
        super().reset(env)
        self._base = _NoOpinion()


class TeamGuide:
    name = "team"

    def __init__(self) -> None:
        self.team = _GuideTeam("team_rules")

    def reset(self, env) -> None:
        self.team.reset(env)

    def requests(self, env) -> dict[str, int]:
        return {tid: p for tid, p in self.team.act(env, {}).items() if p >= 0}

    def summary(self) -> dict[str, Any]:
        m = self.team.metrics()
        return {
            "guide_preemptions": self.team.preemptions,
            "guide_calls": m.get("llm_team_calls", 0),
        }


class EvRuleGuide:
    name = "ev_rule"

    def __init__(self) -> None:
        self.active: set[str] = set()
        self.preemptions = 0

    def reset(self, env) -> None:
        self.range_m = float(env.protocol["baselines"]["ev_preemption_range_m"])
        self.active: set[str] = set()
        self.preemptions = 0

    def requests(self, env) -> dict[str, int]:
        found = approaching(env, env.intersections, self.range_m)
        self.preemptions += len(set(found) - self.active)
        self.active = set(found)
        return {tid: phase_for(env.intersections[tid], link) for tid, (_, link) in found.items()}

    def summary(self) -> dict[str, Any]:
        return {"guide_preemptions": self.preemptions}


GUIDES = {"team": TeamGuide, "ev_rule": EvRuleGuide}


class GuidedPolicy(Controller):
    """COOP-FULL plus a guide, by bias on its logits or by switching (see module doc)."""

    needs_observations = True

    def __init__(self, base, guide, mode: str = "bias", beta: float | None = 4.0) -> None:
        super().__init__()
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode == "bias" and beta is None:
            raise ValueError("a bias guide needs beta")
        self.base, self.guide, self.mode = base, guide, mode
        self.beta = float(beta) if beta is not None else 0.0  # unused when switching
        self.agent_cfg = base.agent_cfg
        tag = f"bias{beta:g}" if mode == "bias" else "switch"
        self.name = f"{base.name}+{guide.name}-{tag}"
        self.guided_decisions = self.changed_decisions = 0

    def reset(self, env) -> None:
        self.base.reset(env)
        self.guide.reset(env)
        self.guided_decisions = self.changed_decisions = 0

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        import torch

        requests = self.guide.requests(env)
        agents = list(obs)
        batch = np.stack([obs[a] for a in agents])
        policy = self.base.model.policy
        with torch.no_grad():
            logits = policy.get_distribution(policy.obs_to_tensor(batch)[0]).distribution.logits
        logits = logits.numpy().copy()
        plain = logits.argmax(axis=1)  # the phase PPO would choose alone
        chosen = plain.copy()
        for i, a in enumerate(agents):
            phase = requests.get(a)
            if phase is None or phase >= logits.shape[1]:
                continue
            self.guided_decisions += 1
            if self.mode == "bias":
                logits[i, phase] += self.beta
                chosen[i] = int(logits[i].argmax())
            else:
                chosen[i] = phase
        self.changed_decisions += int((chosen != plain).sum())
        return {a: int(chosen[i]) for i, a in enumerate(agents)}

    def summary(self) -> dict[str, Any]:
        return {
            "guide": self.guide.name,
            "guide_mode": self.mode,
            "beta": self.beta if self.mode == "bias" else "",
            "guided_decisions": self.guided_decisions,
            "changed_decisions": self.changed_decisions,
            **self.guide.summary(),
        }
