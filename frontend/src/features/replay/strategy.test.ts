import { describe, expect, it } from "vitest";

import type { StrategyCall } from "@/shared/schemas";

import { modeAt, segments } from "./strategy";

const call = (t: number, mode: string, previous: string, valid = true): StrategyCall => ({
  t,
  asked: t - 10,
  mode,
  previous,
  valid,
  reason: `${mode} at ${t}`,
  latency: 10,
});

const calls = [
  call(-90, "equilibre", "equilibre"),
  call(210, "fluidite", "equilibre"),
  call(510, "agent", "fluidite", false),
  call(810, "equilibre", "fluidite"),
];

describe("LLM strategist in a replay", () => {
  it("keeps the mode of the last valid call applied", () => {
    expect(modeAt(calls, 0).mode).toBe("equilibre");
    expect(modeAt(calls, 209).mode).toBe("equilibre");
    expect(modeAt(calls, 210)).toMatchObject({ mode: "fluidite", call: calls[1] });
    // an invalid answer changes nothing
    expect(modeAt(calls, 600).mode).toBe("fluidite");
    expect(modeAt(calls, 900).mode).toBe("equilibre");
  });

  it("starts from the mode the first call found", () => {
    expect(modeAt([call(100, "agent", "fluidite")], 50)).toEqual({ mode: "fluidite", call: null });
  });

  it("cuts the window into mode segments", () => {
    expect(segments(calls, 1000)).toEqual([
      { mode: "equilibre", from: 0, to: 210 },
      { mode: "fluidite", from: 210, to: 810 },
      { mode: "equilibre", from: 810, to: 1000 },
    ]);
  });
});
