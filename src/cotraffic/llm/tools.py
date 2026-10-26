"""Tools of the advisor (function calling): five read-only views, and submit_advice.

The model may look at the situation through the read-only tools, then must call
submit_advice, the only tool that acts: its arguments become the advice, which is then
checked against the network like any answer, applied as a bounded bias and filtered by
the shield. No tool reaches SUMO: they read a snapshot (ToolContext) taken when the call
starts, so a tool call cannot change the simulation (excessive agency, OWASP LLM06).

Every tool has a strict JSON Schema (no extra field, enumerations of the junctions and
vehicles that exist, bounds), and its arguments are validated with Pydantic before it
runs; an unknown tool or invalid arguments are refused and reported to the model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cotraffic.llm.advice import (
    MAX_ITEMS,
    MAX_PHASE,
    MAX_REASON,
    MAX_VALID_S,
    MIN_VALID_S,
    STRENGTHS,
    Advice,
    Item,
    weight_of,
)
from cotraffic.llm.situation import Situation, _event_text

READ_ONLY = (
    "get_intersection_state",
    "get_neighbors",
    "get_active_events",
    "get_ev_route",
    "forecast_inflow",
)
SUBMIT = "submit_advice"


# ---------------------------------------------------------------- arguments (Pydantic)
class _Strict(BaseModel):  # [Exigences 5 et 9] arguments stricts (Pydantic)
    model_config = ConfigDict(extra="forbid")


class JunctionArgs(_Strict):
    junction: str = Field(min_length=1, max_length=16)


class EvArgs(_Strict):
    ev_id: str = Field(min_length=1, max_length=32)


class NoArgs(_Strict):
    pass


class AdviceItemArgs(_Strict):
    junction: str = Field(min_length=1, max_length=16)
    phase: int = Field(ge=0, le=MAX_PHASE)
    strength: Literal[1, 2, 3]
    seconds: int = Field(ge=MIN_VALID_S, le=MAX_VALID_S)


class SubmitArgs(_Strict):  # [Exigence 5] arguments de submit_advice
    items: list[AdviceItemArgs] = Field(default_factory=list, max_length=MAX_ITEMS)
    reason: str = Field(default="", max_length=MAX_REASON)

    def advice(self) -> Advice:
        return Advice(
            a=[
                Item(j=i.junction, p=i.phase, w=weight_of(i.strength), s=i.seconds)
                for i in self.items
            ],
            r=self.reason,
        )


ARGS: dict[str, type[_Strict]] = {
    "get_intersection_state": JunctionArgs,
    "get_neighbors": JunctionArgs,
    "get_active_events": NoArgs,
    "get_ev_route": EvArgs,
    "forecast_inflow": JunctionArgs,
    SUBMIT: SubmitArgs,
}


# ---------------------------------------------------------------- read-only snapshot
@dataclass
class ToolContext:  # [Exigence 5] copie de la situation : les outils ne modifient rien
    """What the tools can read: a copy of the situation, taken when the call starts."""

    situation: Situation
    neighbours: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    inflow: dict[str, dict[str, int]] = field(default_factory=dict)  # junction -> side -> veh

    @classmethod
    def from_env(cls, env, situation: Situation | None) -> ToolContext:
        neighbours, inflow = {}, {}
        for tid, links in getattr(env, "neighbour_links", {}).items():
            neighbours[tid] = [{"side": side, "junction": nb} for side, (nb, _, _) in links.items()]
            inflow[tid] = {
                side: int(round(sum(env.meas.count.get(ln, 0.0) for ln in lanes)))
                for side, (_, lanes, _) in links.items()
            }
        return cls(situation, neighbours, inflow)

    def junction_ids(self) -> list[str]:
        return sorted(j.id for j in self.situation.junctions)

    def ev_ids(self) -> list[str]:
        return sorted(e["id"] for e in self.situation.events if e["kind"] == "emergency")


def run_tool(ctx: ToolContext, name: str, args: BaseModel) -> dict[str, Any]:
    """Result of a read-only tool (plain data: it is sent back to the model as data)."""
    junctions = {j.id: j for j in ctx.situation.junctions}
    by_junction = ("get_intersection_state", "get_neighbors", "forecast_inflow")
    if name in by_junction and args.junction not in junctions:
        return {"error": f"unknown junction {args.junction!r}"}
    if name == "get_intersection_state":
        j = junctions[args.junction]
        return {
            "junction": j.id,
            "phase": j.phase,
            "phase_sides": j.phases,
            "green_s": j.green_s,
            "halted_per_phase": j.queues,
            "waiting_pedestrians": j.peds,
        }
    if name == "get_neighbors":
        return {"junction": args.junction, "neighbours": ctx.neighbours.get(args.junction, [])}
    if name == "get_active_events":
        return {"events": [_event_text(e) for e in ctx.situation.events]}
    if name == "get_ev_route":
        for e in ctx.situation.events:
            if e["kind"] == "emergency" and e["id"] == args.ev_id:
                return {
                    "ev_id": e["id"],
                    "next": [
                        {"junction": s["j"], "phase": s["p"], "metres": s["m"]} for s in e["next"]
                    ],
                }
        return {"error": f"no active emergency vehicle {args.ev_id!r}"}
    if name == "forecast_inflow":
        # naive forecast: vehicles now on the upstream lanes that feed this junction;
        # at urban speeds they arrive within about a minute
        return {
            "junction": args.junction,
            "vehicles_arriving_per_side": ctx.inflow.get(args.junction, {}),
            "horizon": "about 60 s",
        }
    raise ValueError(f"not a read-only tool: {name}")


# ---------------------------------------------------------------- JSON Schemas
def tool_schemas(ctx: ToolContext) -> list[dict[str, Any]]:  # [Exigence 5] le tool schema
    """Tool definitions for the model (Ollama /api/chat ``tools``), strict schemas."""
    junction = {"type": "string", "enum": ctx.junction_ids()}
    max_phase = max(len(j.phases) for j in ctx.situation.junctions) - 1

    def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }

    ev = {"type": "string", "enum": ctx.ev_ids()} if ctx.ev_ids() else {"type": "string"}
    return [
        tool(
            "get_intersection_state",
            "Current phase, seconds of green, halted vehicles per phase, waiting pedestrians.",
            {"junction": junction},
            ["junction"],
        ),
        tool(
            "get_neighbors",
            "Neighbouring junctions and on which side.",
            {"junction": junction},
            ["junction"],
        ),
        tool(
            "get_active_events",
            "Emergency vehicles, incidents, detector faults, message loss, crowds.",
            {},
            [],
        ),
        tool(
            "get_ev_route",
            "Next junctions of an emergency vehicle, phase it needs, distance.",
            {"ev_id": ev},
            ["ev_id"],
        ),
        tool(
            "forecast_inflow",
            "Vehicles arriving at a junction within about a minute, per side.",
            {"junction": junction},
            ["junction"],
        ),
        tool(  # [Exigence 5] submit_advice : le seul outil qui agit
            SUBMIT,
            "Submit the advice (the only tool that acts). Empty items if nothing needs advice.",
            {
                "items": {
                    "type": "array",
                    "maxItems": MAX_ITEMS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "junction": junction,
                            "phase": {"type": "integer", "minimum": 0, "maximum": max_phase},
                            "strength": {"type": "integer", "enum": list(STRENGTHS)},
                            "seconds": {
                                "type": "integer",
                                "minimum": MIN_VALID_S,
                                "maximum": MAX_VALID_S,
                            },
                        },
                        "required": ["junction", "phase", "strength", "seconds"],
                        "additionalProperties": False,
                    },
                },
                "reason": {"type": "string", "maxLength": MAX_REASON},
            },
            ["items"],
        ),
    ]


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str = ""


def validate_call(name: str, arguments: Any) -> BaseModel:  # [Exigences 5 et 9] validation
    """Arguments of a tool call, validated; raises ValueError when refused."""
    if name not in ARGS:
        raise ValueError(f"unknown tool {name!r}: only {', '.join(ARGS)} exist")
    if isinstance(arguments, str):  # some models send the arguments as a JSON string
        try:
            arguments = json.loads(arguments or "{}")
        except ValueError as err:
            raise ValueError(f"arguments are not JSON: {err}") from err
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    try:
        return ARGS[name].model_validate(arguments)
    except ValidationError as err:
        raise ValueError(f"invalid arguments for {name}: {err.errors()[:2]}") from err
