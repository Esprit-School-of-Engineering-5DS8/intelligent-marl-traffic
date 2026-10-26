"""What an advice source knows: a compact, normalised picture of the network and its events.

Events come from feeds a traffic-management centre has: emergency-vehicle dispatch
(vehicle and route), incident reports (location and time), detector diagnostics (failed
detectors) and the communication layer (message loss). Pedestrian crowds are measured at
the crossings. The text form is short (one line per junction) because prompt length and,
above all, output length set the latency of a local model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# waiting pedestrians at one junction that count as a crowd: the top 1 % on validation
# seed 1000 (largest observed 3, 99th percentile 2.9)
PED_CROWD = 3
EV_HORIZON = 4  # upcoming signals of an emergency vehicle shown to the source


@dataclass
class Junction:
    id: str
    phases: list[str]  # sides served by each phase, e.g. ["NS", "EW"]
    phase: int
    green_s: int
    queues: list[int]  # halted vehicles on the lanes each phase serves
    peds: int


@dataclass
class Situation:
    time: float
    trigger: str
    junctions: list[Junction]
    events: list[dict[str, Any]] = field(default_factory=list)

    def n_phases(self) -> dict[str, int]:
        return {j.id: len(j.phases) for j in self.junctions}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_text(self) -> str:  # [Exigence 4] la situation résumée en texte pour le prompt
        """One header, one line per junction, one line per event."""
        layouts = sorted({"/".join(j.phases) for j in self.junctions})
        lines = [f"t={int(self.time)}s trigger={self.trigger}"]
        lines.append("phase sides: " + "; ".join(layouts))
        lines.append("junction phase green_s queue_per_phase peds")
        for j in self.junctions:
            q = ",".join(str(x) for x in j.queues)
            lines.append(f"{j.id} p{j.phase} {j.green_s} [{q}] {j.peds}")
        for e in self.events:
            lines.append(_event_text(e))
        return "\n".join(lines)


def _event_text(e: dict[str, Any]) -> str:
    kind = e["kind"]
    if kind == "emergency":
        route = " ".join(f"{s['j']}(p{s['p']},{s['m']}m)" for s in e["next"])
        return f"EMERGENCY {e['id']} next: {route}"
    if kind == "incident":
        return f"INCIDENT lane blocked on {e['edge']} between {e['from']} and {e['to']}"
    if kind == "detector_fault":
        return "DETECTOR FAULT (reads 0): " + " ".join(e["approaches"])
    if kind == "message_loss":
        return f"MESSAGE LOSS {round(100 * e['rate'])}% between neighbours"
    if kind == "pedestrians":
        return "PEDESTRIAN CROWD " + " ".join(f"{c['j']}:{c['n']}" for c in e["crowds"])
    return kind.upper()


def _sides(inter) -> list[str]:
    out = []
    for lanes in inter.phase_lanes:
        sides = sorted({inter.lane_side[ln][0].upper() for ln in lanes}, key="NESW".index)
        out.append("".join(sides) or "-")
    return out


def phase_for_link(inter, link_index: int) -> int | None:
    for p, links in enumerate(inter.phase_links):
        if link_index in links:
            return p
    return None


def observe(env, trigger: str) -> Situation:  # [Exigence 4] ce que le LLM voit de la simulation
    meas = env.meas
    junctions = []
    for tid, inter in env.intersections.items():
        peds = int(sum(env.ped_waiting.get(c, 0.0) for c in inter.crossings))
        junctions.append(
            Junction(
                id=tid,
                phases=_sides(inter),
                phase=int(inter.phase),
                green_s=int(inter.green_elapsed(env.now)),
                queues=[
                    int(round(sum(meas.halting[ln] for ln in lanes))) for lanes in inter.phase_lanes
                ],
                peds=peds,
            )
        )
    return Situation(time=env.now, trigger=trigger, junctions=junctions, events=events(env))


def events(env) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    conn = env.conn
    for ev in sorted(env.ev_ids):
        upcoming = []
        try:
            nxt = conn.vehicle.getNextTLS(ev)
        except Exception:  # the vehicle left between two decisions
            continue
        for tls, link, dist, _state in nxt:
            inter = env.intersections.get(tls)
            if inter is None:
                continue
            p = phase_for_link(inter, link)
            if p is not None:
                upcoming.append({"j": tls, "p": p, "m": int(dist)})
            if len(upcoming) >= EV_HORIZON:
                break
        if upcoming:
            out.append({"kind": "emergency", "id": ev, "next": upcoming})
    incident = env.episode.bundle.meta.get("incident")
    if incident and incident["start"] <= env.now < incident["end"]:
        edge = incident["edge"]
        out.append(
            {
                "kind": "incident",
                "edge": edge,
                "from": conn.edge.getFromJunction(edge),
                "to": conn.edge.getToJunction(edge),
            }
        )
    noise = env.runtime.get("sensor_noise")
    if noise is not None and noise.failed:
        approaches = sorted(
            {
                f"{env.lane_owner[ln][0]}:{env.lane_owner[ln][1][0].upper()}"
                for ln in noise.failed
                if ln in env.lane_owner
            }
        )
        if approaches:
            out.append({"kind": "detector_fault", "approaches": approaches})
    dropout = env.runtime.get("comm_dropout")
    if dropout is not None and dropout.sent:
        out.append({"kind": "message_loss", "rate": dropout.lost / dropout.sent})
    crowds = []
    for tid, inter in env.intersections.items():
        n = int(sum(env.ped_waiting.get(c, 0.0) for c in inter.crossings))
        if n >= PED_CROWD:
            crowds.append({"j": tid, "n": n})
    if crowds:
        out.append({"kind": "pedestrians", "crowds": crowds})
    return out
