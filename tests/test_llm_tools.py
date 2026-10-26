"""Tool schema of the advisor: strict schemas, validated arguments, read-only tools, and
submit_advice as the only tool that acts."""

from __future__ import annotations

import pytest

from cotraffic.llm.advice import weight_of
from cotraffic.llm.client import ToolReply
from cotraffic.llm.prompts import load
from cotraffic.llm.situation import Junction, Situation
from cotraffic.llm.sources import ToolLlmSource
from cotraffic.llm.tools import (
    READ_ONLY,
    SUBMIT,
    ToolContext,
    run_tool,
    tool_schemas,
    validate_call,
)

EV = {"kind": "emergency", "id": "ev_0", "next": [{"j": "B1", "p": 1, "m": 80}]}


def context() -> ToolContext:
    junctions = [
        Junction("A0", ["NS", "EW"], 0, 30, [2, 9], 1),
        Junction("B1", ["NS", "EW"], 1, 12, [4, 1], 0),
    ]
    situation = Situation(time=900.0, trigger="emergency:ev_0", junctions=junctions, events=[EV])
    return ToolContext(
        situation,
        neighbours={"A0": [{"side": "E", "junction": "B1"}]},
        inflow={"A0": {"E": 6}},
    )


def walk(schema):
    """Every object schema inside a tool definition."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for value in schema.values():
            yield from walk(value)
    elif isinstance(schema, list):
        for value in schema:
            yield from walk(value)


def test_schemas_are_strict_and_enumerate_what_exists():  # [Exigence 5]
    tools = {t["function"]["name"]: t["function"]["parameters"] for t in tool_schemas(context())}
    assert set(tools) == {*READ_ONLY, SUBMIT}
    for params in tools.values():
        for obj in walk(params):
            assert obj["additionalProperties"] is False
    assert tools["get_intersection_state"]["properties"]["junction"]["enum"] == ["A0", "B1"]
    assert tools["get_ev_route"]["properties"]["ev_id"]["enum"] == ["ev_0"]
    item = tools[SUBMIT]["properties"]["items"]["items"]["properties"]
    assert item["strength"]["enum"] == [1, 2, 3] and item["phase"]["maximum"] == 1


@pytest.mark.parametrize(
    "name, arguments",
    [
        ("set_traffic_light", {"junction": "A0", "state": "GGGG"}),  # does not exist
        ("get_intersection_state", {"junction": "A0", "extra": 1}),  # extra field
        ("get_intersection_state", {}),  # missing argument
        (SUBMIT, {"items": [{"junction": "A0", "phase": 1, "strength": 9, "seconds": 60}]}),
        (SUBMIT, {"items": [{"junction": "A0", "phase": 1, "strength": 3, "seconds": 9999}]}),
        (SUBMIT, {"items": [], "reason": "x" * 500}),
        (SUBMIT, "not json"),
    ],
)
def test_invalid_tool_calls_are_refused(name, arguments):  # [Exigences 5 et 9]
    with pytest.raises(ValueError):
        validate_call(name, arguments)


def test_read_only_tools_return_data_from_the_snapshot():
    ctx = context()
    state = run_tool(
        ctx, "get_intersection_state", validate_call("get_intersection_state", {"junction": "A0"})
    )
    assert state["halted_per_phase"] == [2, 9] and state["phase"] == 0
    assert run_tool(ctx, "get_neighbors", validate_call("get_neighbors", {"junction": "A0"}))[
        "neighbours"
    ] == [{"side": "E", "junction": "B1"}]
    assert run_tool(ctx, "get_ev_route", validate_call("get_ev_route", {"ev_id": "ev_0"}))["next"][
        0
    ] == {"junction": "B1", "phase": 1, "metres": 80}
    inflow = run_tool(ctx, "forecast_inflow", validate_call("forecast_inflow", {"junction": "A0"}))
    assert inflow["vehicles_arriving_per_side"] == {"E": 6}
    assert "error" in run_tool(
        ctx, "get_neighbors", validate_call("get_neighbors", {"junction": "Z9"})
    )


class ScriptedClient:
    """Stands for Ollama with function calling: returns scripted tool calls."""

    model = "fake"

    def __init__(self, *turns):
        self.turns = list(turns)
        self.seen: list[list[dict]] = []

    def chat_tools(self, messages, tools):
        self.seen.append(list(messages))
        calls = self.turns.pop(0) if self.turns else []
        message = {"role": "assistant", "content": "", "tool_calls": calls}
        return ToolReply(message, 1.0, 50, 10)


def call(name, **arguments):
    return {"function": {"name": name, "arguments": arguments}}


def advise(client):
    source = ToolLlmSource(client, load(technique="zero"))
    source._env_view = (context().neighbours, context().inflow)
    return source.advise(context().situation)


def test_the_model_reads_then_submits_and_only_submit_acts():  # [Exigence 5]
    client = ScriptedClient(
        [call("get_ev_route", ev_id="ev_0")],
        [call(SUBMIT, items=[{"junction": "B1", "phase": 1, "strength": 3, "seconds": 60}])],
    )
    reply = advise(client)
    assert [(i.j, i.p, i.w, i.s) for i in reply.advice.a] == [("B1", 1, weight_of(3), 60)]
    tool_messages = [m for m in client.seen[1] if m["role"] == "tool"]
    assert tool_messages and '"metres": 80' in tool_messages[0]["content"]
    assert reply.latency_s == 2.0 and [c["name"] for c in reply.meta["tools"]] == [
        "get_ev_route",
        SUBMIT,
    ]


def test_an_unknown_tool_is_refused_and_reported_to_the_model():  # [Exigences 5 et 9]
    client = ScriptedClient(
        [call("set_traffic_light", junction="A0", state="GGGG")],
        [call(SUBMIT, items=[])],
    )
    reply = advise(client)
    assert reply.advice is not None and reply.advice.a == []
    assert "unknown tool" in reply.meta["tools"][0]["error"]
    assert "unknown tool" in [m for m in client.seen[1] if m["role"] == "tool"][0]["content"]


def test_no_submit_within_the_budget_means_no_advice():
    client = ScriptedClient(*[[call("get_active_events")] for _ in range(10)])
    reply = advise(client)
    assert reply.advice is None and "budget" in reply.meta["error"]
    assert reply.meta["attempts"] == 4  # max_rounds model turns, then the policy alone
