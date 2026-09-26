"""Rule-based emergency-vehicle preemption: EV-RULE (on actuated control) and EV-RULE-MP
(on Max-Pressure).

EV-RULE, on top of actuated control:

When an emergency vehicle is within ``ev_preemption_range_m`` of its next signal, the
rule takes the signal over and gives green to the movement the vehicle will use:

* if that movement is already green, the green is held until the vehicle has passed;
* otherwise the current green is ended as soon as it has lasted ``min_green`` (same
  rule as everywhere else), followed by the normal yellow, then the vehicle's green.

When no emergency vehicle approaches any more, the actuated program resumes from the
phase that was held. Signals without emergency vehicles run actuated control untouched.

EV-RULE-MP applies the same rule on top of Max-Pressure, so that the cost of preemption
can be measured against the best base controller at peak: at each decision, a signal with
an emergency vehicle within the same range requests the vehicle's phase; the others follow
Max-Pressure. Requests go through the shield like every controller of the environment
(minimum green, then the yellow), at the 5-s decision interval of the learned agents.
"""

from __future__ import annotations

from dataclasses import dataclass

from cotraffic.controllers.classical import Actuated, MaxPressure
from cotraffic.envs.intersection import yellow_state

IDLE, CLEARING, HOLDING = "idle", "clearing", "holding"


def approaching(env, signals, range_m: float) -> dict[str, tuple[float, int]]:
    """Closest approaching emergency vehicle per signal: (distance, link index)."""
    out: dict[str, tuple[float, int]] = {}
    for ev in env.ev_ids:
        upcoming = env.conn.vehicle.getNextTLS(ev)
        if not upcoming:
            continue
        tls, link, dist, _ = upcoming[0]
        if tls in signals and dist <= range_m and (tls not in out or dist < out[tls][0]):
            out[tls] = (dist, link)
    return out


def phase_for(inter, link: int) -> int:
    """Green phase serving a link, preferring a protected (G) over a permissive (g) green."""
    states = inter.green_states
    strict = [p for p, s in enumerate(states) if s[link] == "G"]
    return (strict or [p for p, s in enumerate(states) if s[link] in "Gg"] or [0])[0]


@dataclass
class _Takeover:
    mode: str = IDLE
    target: int = 0  # green phase index (in the intersection model)
    current: int = 0  # green phase currently shown while in override
    since: float = 0.0  # start of the current override state


class EmergencyPreemption(Actuated):
    name = "ev_rule"

    def __init__(self) -> None:
        super().__init__()
        self.takeovers: dict[str, _Takeover] = {}
        self.preemptions = 0

    def step_hooks(self) -> list:
        return [self._on_step]

    def reset(self, env) -> None:
        self.takeovers = {tid: _Takeover() for tid in env.intersections}
        self.preemptions = 0
        b, t = env.protocol["baselines"], env.protocol["timing"]
        self.range_m = float(b["ev_preemption_range_m"])
        self.min_green = float(t["min_green"])
        self.yellow = float(t["yellow_time"])

    def _requests(self, env) -> dict[str, tuple[float, int]]:
        return approaching(env, self.takeovers, self.range_m)

    @staticmethod
    def _phase_for(inter, link: int) -> int:
        return phase_for(inter, link)

    def _on_step(self, env, now: float) -> None:
        tl = env.conn.trafficlight
        requests = self._requests(env)
        for tid, take in self.takeovers.items():
            inter = env.intersections[tid]
            if tid in requests:
                target = self._phase_for(inter, requests[tid][1])
                if take.mode == IDLE:
                    state = tl.getRedYellowGreenState(tid)
                    if "y" in state:
                        continue  # the program is already changing phase; decide at its next green
                    shown = next((p for p, s in enumerate(inter.green_states) if s == state), None)
                    if shown is None:
                        continue
                    self.preemptions += 1
                    take.current = shown
                    take.since = now - tl.getSpentDuration(tid)
                    take.mode = HOLDING
                    tl.setRedYellowGreenState(tid, inter.green_states[shown])
                take.target = target
                if (
                    take.mode == HOLDING
                    and take.current != target
                    and now - take.since >= self.min_green
                ):
                    old, new = inter.green_states[take.current], inter.green_states[target]
                    tl.setRedYellowGreenState(tid, yellow_state(old, new, inter.crossing_signals))
                    take.mode, take.since = CLEARING, now
                elif take.mode == CLEARING and now - take.since >= self.yellow:
                    tl.setRedYellowGreenState(tid, inter.green_states[take.target])
                    take.mode, take.current, take.since = HOLDING, take.target, now
            elif take.mode == CLEARING and now - take.since >= self.yellow:
                tl.setRedYellowGreenState(tid, inter.green_states[take.target])
                take.mode, take.current, take.since = HOLDING, take.target, now
            elif take.mode == HOLDING:
                # emergency vehicle gone: hand back to the actuated program at the held phase
                tl.setProgram(tid, "act")
                tl.setPhase(tid, 2 * take.current if inter.n_phases > 1 else 0)
                take.mode = IDLE


class MaxPressurePreemption(MaxPressure):
    name = "ev_rule_mp"

    def __init__(self) -> None:
        super().__init__()
        self.preemptions = 0
        self.active: set[str] = set()

    def reset(self, env) -> None:
        self.range_m = float(env.protocol["baselines"]["ev_preemption_range_m"])
        self.preemptions = 0
        self.active = set()

    def act(self, env, obs):
        actions = super().act(env, obs)
        requests = approaching(env, env.intersections, self.range_m)
        for tid, (_, link) in requests.items():
            actions[tid] = phase_for(env.intersections[tid], link)
        self.preemptions += len(set(requests) - self.active)
        self.active = set(requests)
        return actions
