"""Runtime overlays that compose on top of any controller.

An overlay receives the actions proposed by the base policy and may replace some of
them. Overlays are ordered by ``priority`` (lowest first, highest last) so that an EV
preemption can override a pedestrian request, while both remain below the environment's
safety shield.

The same stack is used during training and evaluation, which is what lets one policy be
trained with ``ev_preemption`` and ``pedestrian_service`` active, then evaluated with
either of them toggled off without retraining.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cotraffic.controllers.classical import MaxPressure
from cotraffic.controllers.ev_preemption import approaching, phase_for
from cotraffic.controllers.pedestrian_rule import longest_waits


class Overlay:
    id = "base"

    def __init__(self, params: Mapping[str, Any] | None = None) -> None:
        self.params = dict(params or {})
        self.priority = int(self.params.pop("priority", 0))
        self.activations = 0
        self.active: set[str] = set()

    def reset(self, env) -> None:
        self.activations = 0
        self.active = set()

    def apply(self, env, actions: dict[str, int], now: float) -> dict[str, int]:
        return actions

    def parameters(self) -> dict[str, Any]:
        return {"id": self.id, "priority": self.priority, **self.params}

    def summary(self) -> dict[str, Any]:
        return {f"overlay_{self.id}": self.activations}


class EvPreemptionOverlay(Overlay):
    id = "ev_preemption"

    def reset(self, env) -> None:
        super().reset(env)
        self.range_m = float(
            self.params.get("range_m", env.protocol["baselines"]["ev_preemption_range_m"])
        )

    def apply(self, env, actions: dict[str, int], now: float) -> dict[str, int]:
        requests = approaching(env, env.intersections, self.range_m)
        for tid, (_, link) in requests.items():
            inter = env.intersections[tid]
            if inter.in_yellow:
                continue
            actions[tid] = phase_for(inter, link)
        active = set(requests)
        self.activations += len(active - self.active)
        self.active = active
        return actions


class PedestrianServiceOverlay(Overlay):
    id = "pedestrian_service"

    def reset(self, env) -> None:
        super().reset(env)
        self.wait_s = float(self.params.get("wait_s", env.protocol["baselines"]["ped_rule_wait_s"]))

    def apply(self, env, actions: dict[str, int], now: float) -> dict[str, int]:
        waits = longest_waits(env)
        if not waits:
            self.active = set()
            return actions
        active = set()
        for tid, inter in env.intersections.items():
            if inter.in_yellow:
                continue
            due = [
                link
                for link in inter.crossing_links
                if waits.get(link.crossing, 0.0) > self.wait_s
            ]
            if not due:
                continue
            worst = max(due, key=lambda link: waits[link.crossing])
            active.add(tid)
            if worst.index in inter.phase_links[inter.phase]:
                actions[tid] = inter.phase
            else:
                actions[tid] = phase_for(inter, worst.index)
        self.activations += len(active - self.active)
        self.active = active
        return actions


class MaxPressureFallbackOverlay(Overlay):
    """Fill only missing or invalid actions; never overrides a valid policy decision."""

    id = "mp_fallback"

    def reset(self, env) -> None:
        super().reset(env)
        self._mp = MaxPressure()
        self._mp.reset(env)

    def apply(self, env, actions: dict[str, int], now: float) -> dict[str, int]:
        missing = [
            tid
            for tid in env.intersections
            if tid not in actions or not 0 <= int(actions[tid]) < env.action_space(tid).n
        ]
        if not missing:
            self.active = set()
            return actions
        fallback = self._mp.act(env, {})
        for tid in missing:
            if tid in fallback:
                actions[tid] = int(fallback[tid])
        active = set(missing)
        self.activations += len(active - self.active)
        self.active = active
        return actions


_CLASSES = {
    "ev_preemption": EvPreemptionOverlay,
    "pedestrian_service": PedestrianServiceOverlay,
    "mp_fallback": MaxPressureFallbackOverlay,
}
_DEFAULT_PRIORITY = {"ev_preemption": 100, "pedestrian_service": 90, "mp_fallback": 10}


def build_overlays(runtime_cfg: Mapping[str, Any] | None) -> list[Overlay]:
    """Build the ordered overlay stack of a recipe's ``runtime`` block."""
    specs = (runtime_cfg or {}).get("overlays") or []
    overlays: list[Overlay] = []
    for spec in specs:
        if isinstance(spec, str):
            spec = {"id": spec}
        overlay_id = str(spec.get("id", ""))
        cls = _CLASSES.get(overlay_id)
        if cls is None:
            raise ValueError(f"unknown overlay {overlay_id!r}")
        params = {k: v for k, v in spec.items() if k != "id"}
        params.setdefault("priority", _DEFAULT_PRIORITY.get(overlay_id, 0))
        overlays.append(cls(params))
    # lowest priority first, highest last (highest wins)
    return sorted(overlays, key=lambda o: (o.priority, o.id))
