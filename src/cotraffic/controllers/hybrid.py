"""The layered controller of the combined study, without any language model (phase A).

Every decision (5 s) goes down four layers:

1. strategy (slow): the mode of each junction, decided every ``period_s`` (300 s):
   * ``CoopStrategy``: COOP-FULL everywhere;
   * ``CongestionStrategy`` (H1): Max-Pressure at a junction whose neighbourhood is
     congested (mean normalised queue of the last minute above a threshold), COOP-FULL
     elsewhere; the thresholds are quantiles of that congestion under COOP-FULL on the
     validation seed (``congestion_thresholds``);
   * ``BacklogStrategy`` (H3): Max-Pressure at every junction while the queue at the
     entrances of the network (vehicles SUMO could not insert yet, mean of the last minute)
     exceeds a threshold; the thresholds are quantiles of that queue under H2 on the
     validation seed (``backlog_thresholds``);
2. tactics: the mode decides the phase; in the COOP-FULL mode, ``mp_beta`` > 0 (H2) adds
   ``mp_beta`` to the logit of Max-Pressure's phase (Max-Pressure as a guide of COOP-FULL);
3. pre-emption, by switching at the concerned junctions only: pedestrians (PED-RULE or the
   teammate's serve_ped rules), then emergency vehicles (EV-RULE or the teammate's rules),
   the later taking precedence;
4. the shield of the environment, which always has the last word.

The summary gives the share of the decisions taken by each layer, and how many decisions
differ from what COOP-FULL alone would have chosen.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import numpy as np

from cotraffic.controllers.base import Controller
from cotraffic.controllers.classical import MaxPressure
from cotraffic.controllers.combined import TeamGuide
from cotraffic.controllers.ev_preemption import phase_for
from cotraffic.controllers.pedestrian_rule import longest_waits

SOURCES = ("coop", "mp", "mix", "ped", "ev")


# ---------------------------------------------------------------- strategy
def neighbourhood_queue(env) -> dict[str, float]:
    """Normalised queue of each junction and its neighbours (the largest of them)."""
    own = {tid: env.meas.queue(inter.in_lanes) for tid, inter in env.intersections.items()}
    out = {}
    for tid, q in own.items():
        nbs = [nb for nb, _, _ in getattr(env, "neighbour_links", {}).get(tid, {}).values()]
        out[tid] = max([q] + [own[nb] for nb in nbs if nb in own])
    return out


class CoopStrategy:
    name = "coop"

    def reset(self, env) -> None:
        pass

    def modes(self, env) -> dict[str, str]:
        return {}  # no junction in another mode

    def summary(self) -> dict[str, Any]:
        return {}


class CongestionStrategy:
    """H1: Max-Pressure where the neighbourhood is congested, decided every ``period_s``."""

    name = "congestion"

    def __init__(self, threshold: float, period_s: float = 300.0, window_s: float = 60.0):
        self.threshold, self.period_s, self.window_s = float(threshold), period_s, window_s

    def reset(self, env) -> None:
        self.history: dict[str, deque] = defaultdict(deque)
        self.current: dict[str, str] = dict.fromkeys(env.intersections, "coop")
        self.next_update = 0.0
        self.switches = 0

    def observe(self, env) -> dict[str, float]:
        """Mean neighbourhood queue of the last ``window_s`` (one sample per decision)."""
        now = env.now
        for tid, c in neighbourhood_queue(env).items():
            h = self.history[tid]
            h.append((now, c))
            while h and h[0][0] < now - self.window_s:
                h.popleft()
        return {tid: float(np.mean([c for _, c in h])) for tid, h in self.history.items()}

    def modes(self, env) -> dict[str, str]:
        congestion = self.observe(env)
        if env.now >= self.next_update:
            new = {tid: "mp" if c >= self.threshold else "coop" for tid, c in congestion.items()}
            self.switches += sum(new[t] != self.current.get(t) for t in new)
            self.current = new
            self.next_update = env.now + self.period_s
        return self.current

    def summary(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "period_s": self.period_s,
            "mode_switches": self.switches,
        }


def insertion_backlog(env) -> int:
    """Vehicles whose departure time has come but that SUMO could not insert yet: the queue
    at the entrances of the network (``waiting`` in SUMO's summary)."""
    return len(env.conn.simulation.getPendingVehicles())


class BacklogStrategy:
    """H3: Max-Pressure at every junction while the queue at the entrances exceeds a
    threshold, decided every ``period_s``; otherwise every junction stays in the COOP-FULL
    mode (with the bias of H2 when the policy has one)."""

    name = "backlog"

    def __init__(self, threshold: float, period_s: float = 300.0, window_s: float = 60.0):
        self.threshold, self.period_s, self.window_s = float(threshold), period_s, window_s

    def reset(self, env) -> None:
        self.history: deque = deque()
        self.current = "coop"
        self.next_update = 0.0
        self.switches = 0
        self.periods = {"coop": 0, "mp": 0}

    def observe(self, env) -> float:
        """Mean queue at the entrances over the last ``window_s`` (one sample per decision)."""
        now = env.now
        self.history.append((now, insertion_backlog(env)))
        while self.history and self.history[0][0] < now - self.window_s:
            self.history.popleft()
        return float(np.mean([b for _, b in self.history]))

    def modes(self, env) -> dict[str, str]:
        backlog = self.observe(env)
        if env.now >= self.next_update:
            new = "mp" if backlog > self.threshold else "coop"
            self.switches += new != self.current
            self.current = new
            self.periods[new] += 1
            self.next_update = env.now + self.period_s
        return dict.fromkeys(env.intersections, "mp") if self.current == "mp" else {}

    def summary(self) -> dict[str, Any]:
        n = max(1, sum(self.periods.values()))
        return {
            "threshold": self.threshold,
            "period_s": self.period_s,
            "mode_switches": self.switches,
            "periods_mp": round(self.periods["mp"] / n, 4),
        }


# ---------------------------------------------------------------- pre-emption guides
class TeamRoleGuide(TeamGuide):
    """The teammate's rules of the given roles only, without any LLM: ``emergency``
    (pre-emption windows) or ``pedestrian`` (serve_ped windows)."""

    def __init__(self, roles: tuple[str, ...]) -> None:
        super().__init__()
        self.roles = tuple(roles)
        self.name = "team_" + "_".join(self.roles)

    def reset(self, env) -> None:
        super().reset(env)
        sup = self.team._supervisor
        sup.agents = {role: agent for role, agent in sup.agents.items() if role in self.roles}


class PedRuleGuide:
    """Our PED-RULE (as PED-RULE-MP): a crossing whose longest-waiting pedestrian has waited
    more than ``ped_rule_wait_s`` gets its green (held if it already has it)."""

    name = "ped_rule"

    def __init__(self) -> None:
        self.requests_made = 0

    def reset(self, env) -> None:
        self.wait_s = float(env.protocol["baselines"]["ped_rule_wait_s"])
        self.requests_made = 0

    def requests(self, env) -> dict[str, int]:
        waits = longest_waits(env)
        out = {}
        if not waits:
            return out
        for tid, inter in env.intersections.items():
            due = [lk for lk in inter.crossing_links if waits.get(lk.crossing, 0.0) > self.wait_s]
            if not due:
                continue
            worst = max(due, key=lambda lk: waits[lk.crossing])
            if worst.index in inter.phase_links[inter.phase] and not inter.in_yellow:
                out[tid] = inter.phase
            else:
                out[tid] = phase_for(inter, worst.index)
                self.requests_made += 1
        return out

    def summary(self) -> dict[str, Any]:
        return {"ped_requests": self.requests_made}


# ---------------------------------------------------------------- the layered policy
class HybridPolicy(Controller):
    """COOP-FULL under a strategy, with Max-Pressure, pre-emption and the shield."""

    needs_observations = True

    def __init__(
        self,
        base,
        strategy=None,
        mp_beta: float = 0.0,
        ped_guide=None,
        ev_guide=None,
        name: str = "",
    ) -> None:
        super().__init__()
        self.base = base
        self.strategy = strategy or CoopStrategy()
        self.mp_beta = float(mp_beta)
        self.ped_guide, self.ev_guide = ped_guide, ev_guide
        self.mp = MaxPressure()
        self.agent_cfg = base.agent_cfg
        self.name = name or "hybrid"
        self.counts = dict.fromkeys(SOURCES, 0)
        self.changed_decisions = self.mix_changed = 0

    def reset(self, env) -> None:
        self.base.reset(env)
        self.mp.reset(env)
        self.strategy.reset(env)
        for guide in (self.ped_guide, self.ev_guide):
            if guide is not None:
                guide.reset(env)
        self.counts = dict.fromkeys(SOURCES, 0)
        self.changed_decisions = self.mix_changed = 0

    def act(self, env, obs: dict[str, Any]) -> dict[str, int]:
        import torch

        modes = self.strategy.modes(env)
        need_mp = self.mp_beta > 0 or any(m == "mp" for m in modes.values())
        mp = self.mp.act(env, obs) if need_mp else {}
        pre: dict[str, tuple[int, str]] = {}
        for guide, source in ((self.ped_guide, "ped"), (self.ev_guide, "ev")):
            if guide is not None:  # emergency vehicles last: they take precedence
                pre.update({tid: (p, source) for tid, p in guide.requests(env).items()})

        agents = list(obs)
        batch = np.stack([obs[a] for a in agents])
        policy = self.base.model.policy
        with torch.no_grad():
            logits = policy.get_distribution(policy.obs_to_tensor(batch)[0]).distribution.logits
        logits = logits.numpy()
        plain = logits.argmax(axis=1)  # the phase COOP-FULL would choose alone
        actions = {}
        for i, a in enumerate(agents):
            phase, source = int(plain[i]), "coop"
            if modes.get(a) == "mp":
                phase, source = int(mp[a]), "mp"
            elif self.mp_beta > 0 and mp.get(a, -1) < logits.shape[1]:
                row = logits[i].copy()
                row[int(mp[a])] += self.mp_beta
                phase, source = int(row.argmax()), "mix"
                self.mix_changed += phase != int(plain[i])
            if a in pre and pre[a][0] < logits.shape[1]:
                phase, source = pre[a]
            self.counts[source] += 1
            self.changed_decisions += phase != int(plain[i])
            actions[a] = int(phase)
        return actions

    def summary(self) -> dict[str, Any]:
        total = max(1, sum(self.counts.values()))
        out = {
            "strategy": self.strategy.name,
            "mp_beta": self.mp_beta,
            "ped_guide": getattr(self.ped_guide, "name", ""),
            "ev_guide": getattr(self.ev_guide, "name", ""),
            **{f"share_{s}": round(self.counts[s] / total, 4) for s in SOURCES},
            "changed_decisions": self.changed_decisions,
            "mix_changed_decisions": self.mix_changed,
            **self.strategy.summary(),
        }
        for guide, prefix in ((self.ped_guide, "ped"), (self.ev_guide, "ev")):
            if guide is not None:
                out.update({f"{prefix}_{k}": v for k, v in guide.summary().items()})
        return out
