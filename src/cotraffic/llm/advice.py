"""The only output of an advice source that acts: phase preferences, strictly bounded.

On the wire (what the model writes) an item is a 4-element array
``["<junction>", <phase>, <strength 1-3>, <seconds valid>]``: about 12 tokens instead of 20
for an object with named keys, and generation time sets the latency on a CPU. The
junction and the strength are enumerations in the JSON Schema used for constrained
decoding, so the model cannot name a junction that does not exist nor write a weight of
"100" (decimal bounds are not enforced by the decoder: 3B models wrote percentages in the
first benchmark). Strength 1, 2, 3 = weight 1/3, 2/3, 1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_ITEMS = 4
MIN_VALID_S, MAX_VALID_S = 10, 120
MAX_REASON = 60
MAX_PHASE = 7
STRENGTHS = (1, 2, 3)


def weight_of(strength: int) -> float:
    return round(strength / 3, 4)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    j: str = Field(min_length=1, max_length=16)
    p: int = Field(ge=0, le=MAX_PHASE)
    w: float = Field(ge=0.0, le=1.0)
    s: int = Field(ge=MIN_VALID_S, le=MAX_VALID_S)


class Advice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: list[Item] = Field(default_factory=list, max_length=MAX_ITEMS)
    r: str = Field(default="", max_length=MAX_REASON)


def schema_for(
    junctions: list[str], max_phase: int, reason_max: int = MAX_REASON
) -> dict[str, Any]:
    """JSON Schema of the wire format for one network (constrained decoding). A technique
    without a reason sets ``reason_max`` to 0: the model cannot spend tokens on one."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["a", "r"],
        "properties": {
            "a": {
                "type": "array",
                "maxItems": MAX_ITEMS,
                "items": {
                    "type": "array",
                    "prefixItems": [
                        {"type": "string", "enum": sorted(junctions)},
                        {"type": "integer", "minimum": 0, "maximum": max_phase},
                        {"type": "integer", "enum": list(STRENGTHS)},
                        {"type": "integer", "minimum": MIN_VALID_S, "maximum": MAX_VALID_S},
                    ],
                    "minItems": 4,
                    "maxItems": 4,
                },
            },
            "r": {"type": "string", "maxLength": min(reason_max, MAX_REASON)},
        },
    }


class AdviceError(ValueError):
    """The text is not a valid advice (malformed JSON, wrong shape or out-of-bounds values)."""


def parse(text: str) -> Advice:
    """Wire format -> Advice. Every bound is checked again here: constrained decoding is a
    help, never a guarantee the code relies on."""
    try:
        data = json.loads(text)
    except ValueError as err:
        raise AdviceError(f"invalid JSON: {err}") from err
    if not isinstance(data, dict) or set(data) - {"a", "r"}:
        raise AdviceError("expected an object with keys a and r")
    raw = data.get("a", [])
    if not isinstance(raw, list):
        raise AdviceError("a must be a list")
    items = []
    for entry in raw:
        if not isinstance(entry, list) or len(entry) != 4:
            raise AdviceError(f"item must be [junction, phase, strength, seconds]: {entry!r}")
        j, phase, strength, s = entry
        if any(isinstance(v, bool) for v in (phase, strength, s)):
            raise AdviceError(f"booleans are not numbers: {entry!r}")
        if strength not in STRENGTHS or not isinstance(strength, int):
            raise AdviceError(f"strength must be 1, 2 or 3: {entry!r}")
        try:
            items.append(Item(j=j, p=phase, w=weight_of(strength), s=s))
        except ValidationError as err:
            raise AdviceError(str(err.errors()[:2])) from err
    try:
        return Advice(a=items, r=str(data.get("r", ""))[: MAX_REASON + 1])
    except ValidationError as err:
        raise AdviceError(str(err.errors()[:2])) from err


def to_wire(advice: Advice) -> str:
    return json.dumps(
        {"a": [[i.j, i.p, max(1, min(3, round(3 * i.w))), i.s] for i in advice.a], "r": advice.r},
        separators=(",", ":"),
    )


@dataclass
class Checked:
    """Items kept after checking them against the network, and why the others were not."""

    items: list[Item] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def check(advice: Advice, n_phases: dict[str, int]) -> Checked:
    """Keep items naming an existing junction and phase; one item per junction (the
    strongest), zero weights dropped."""
    out = Checked()
    best: dict[str, Item] = {}
    for item in advice.a:
        if item.j not in n_phases:
            out.rejected.append(f"unknown junction {item.j!r}")
        elif item.p >= n_phases[item.j]:
            out.rejected.append(f"{item.j}: phase {item.p} does not exist")
        elif item.w == 0:
            continue
        elif item.j not in best or item.w > best[item.j].w:
            if item.j in best:
                out.rejected.append(f"{item.j}: duplicate, weaker item dropped")
            best[item.j] = item
        else:
            out.rejected.append(f"{item.j}: duplicate, weaker item dropped")
    out.items = list(best.values())
    return out
