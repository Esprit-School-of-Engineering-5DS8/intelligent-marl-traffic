import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import i18n from "@/shared/i18n";
import { useFormat } from "@/shared/domain/format";
import type { ChatEvent, Comparison, Meta, SummaryRow } from "@/shared/schemas";

import { answerLocally } from "./local";

const cell = { network: "grid4x4", scenario: "normal", demand: "peak" };
const row = (method: string, metric: string, mean: number): SummaryRow => ({
  ...cell,
  method,
  metric,
  n: 15,
  nTrain: 3,
  mean,
  ciLo: mean - 2,
  ciHi: mean + 2,
  std: 1,
});
const data = {
  meta: {
    generatedAt: "2026-10-15T00:00:00+00:00",
    cells: [{ ...cell, methods: ["ft", "mp", "coop_full"] }],
    methods: ["ft", "mp", "coop_full"],
    metrics: ["mean_waiting_time", "co2_total_kg"],
    runs: 10,
    extraRuns: 0,
    dqnAvailable: false,
    replays: [],
    timeseries: [],
    decisions: [],
    training: [],
    networks: [],
  } satisfies Meta,
  summary: [
    row("ft", "mean_waiting_time", 91.1),
    row("mp", "mean_waiting_time", 55.3),
    row("coop_full", "mean_waiting_time", 58.1),
    row("ft", "co2_total_kg", 4650),
    row("coop_full", "co2_total_kg", 4117),
  ],
  comparisons: [
    {
      ...cell,
      method: "coop_full",
      reference: "ft",
      metric: "mean_waiting_time",
      mean: 58.1,
      referenceMean: 91.1,
      improvementPct: 36.2,
      pairedImprovementPct: 36.2,
      pairedCiLo: 35,
      pairedCiHi: 37.5,
      pValue: 0.001,
      pHolm: 0.005,
      cliffsDelta: -1,
      effect: "large",
      significant: true,
      n: 15,
      comparison: "learned_vs_ft",
      family: "core",
    } satisfies Comparison,
  ],
};

function run(question: string, live = false): ChatEvent[] {
  const { result } = renderHook(() => useFormat());
  const t = i18n.t.bind(i18n) as unknown as (k: string, o?: Record<string, unknown>) => string;
  return [...answerLocally(question, { page: "/" }, data, t, result.current, live)];
}
const text = (events: ChatEvent[]) =>
  events.map((e) => (e.type === "token" ? e.text : "")).join("");

describe("assistant without backend", () => {
  it("compares two named controllers with the paired test", () => {
    const events = run("COOP-FULL est-il meilleur que FT sur l'attente en pointe ?");
    const answer = text(events);
    expect(answer).toContain("58,1");
    expect(answer).toContain("91,1");
    expect(answer).toContain("36,2");
    expect(events).toContainEqual({
      type: "source",
      file: "results/summary/comparisons_mean_waiting_time.csv",
    });
    expect(events.at(-1)).toEqual({ type: "done", writtenBy: "code" });
  });

  it("does not take COOP for COOP-FULL", () => {
    const events = run("compare coop-full et mp");
    const call = events.find((e) => e.type === "tool_call");
    expect(
      call?.type === "tool_call" && call.call.name === "compareControllers" && call.call.args,
    ).toMatchObject({ a: "coop_full", b: "mp" });
  });

  it("answers a chart request with a chart tool call, numbers from the results", () => {
    const events = run("montre le graphique du CO2");
    const call = events.find((e) => e.type === "tool_call");
    expect(call?.type === "tool_call" && call.call.name).toBe("generateChart");
    expect(text(events)).toContain("CO2");
  });

  it("names the best controller when none is named", () => {
    expect(text(run("quel est le meilleur sur l'attente ?"))).toContain("MP");
  });

  it("never proposes a run without the backend", () => {
    const events = run("lance une simulation urgences sur la grille");
    expect(events.some((e) => e.type === "tool_call")).toBe(false);
    const live = run("lance une simulation urgences sur la grille", true);
    const call = live.find((e) => e.type === "tool_call");
    expect(call?.type === "tool_call" && call.call.name).toBe("runScenario");
  });
});
