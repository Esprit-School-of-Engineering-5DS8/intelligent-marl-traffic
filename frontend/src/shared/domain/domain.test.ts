import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useSettings } from "@/features/settings/store";
import { toCsv } from "@/shared/lib/csv";

import { compareCells, parseCellKey } from "./cells";
import { useFormat } from "./format";
import { gainPct } from "./metrics";

describe("domain helpers", () => {
  it("signs gains so that positive is an improvement", () => {
    expect(gainPct("mean_waiting_time", 58.1, 91.1)).toBeCloseTo(36.22, 1);
    expect(gainPct("throughput_per_h", 110, 100)).toBeCloseTo(10);
    expect(gainPct("mean_waiting_time", 1, 0)).toBeNull();
  });

  it("formats metrics in the chosen units and language", () => {
    const { result, rerender } = renderHook(() => useFormat());
    expect(result.current.metric(91.1, "mean_waiting_time")).toBe("91,1 s");
    act(() => useSettings.getState().update({ timeUnit: "min" }));
    rerender();
    expect(result.current.metric(90, "mean_waiting_time")).toBe("1,5 min");
    expect(result.current.metricInSentence("co2_total_kg")).toBe("CO2 total");
    expect(result.current.metricInSentence("mean_waiting_time")).toBe("attente moyenne aux feux");
    expect(result.current.clock(3725)).toBe("1:02:05");
  });

  it("orders and parses scenario cells", () => {
    expect(parseCellKey("grid4x4__normal__peak")).toEqual({
      network: "grid4x4",
      scenario: "normal",
      demand: "peak",
    });
    expect(parseCellKey("broken")).toBeNull();
    const a = { network: "grid4x4", scenario: "normal", demand: "low" };
    const b = { network: "grid4x4", scenario: "normal", demand: "peak" };
    expect(compareCells(a, b)).toBeLessThan(0);
  });

  it("writes CSV with quoting", () => {
    expect(toCsv([{ a: "x,y", b: 1, c: null }])).toBe('a,b,c\n"x,y",1,');
  });
});
