import { useState } from "react";

import type { ChartTokens } from "@/shared/charts/tokens";
import type { Cells, TestRow, TestVerdict } from "@/shared/schemas/combined";

export type NetworkFilter = "all" | "grid4x4" | "real_district" | "grid8x8";
export type MetricFilter = "all" | "travel" | "waiting";

/** The four groups of the situations, as in the report's figure. */
export type Group = "main" | "district" | "robustness" | "generalisation";

const ROBUSTNESS = new Set(["sensor_noise", "comm_dropout_30", "buses"]);

export function groupOf(t: Pick<TestRow, "network" | "scenario">): Group {
  if (t.network === "grid8x8") return "generalisation";
  if (t.network === "real_district") return "district";
  return ROBUSTNESS.has(t.scenario) ? "robustness" : "main";
}

/** The verdicts in the order of the legend: proven, then not proven. */
export const VERDICT_ORDER: TestVerdict[] = ["best", "noninf", "loss", "wide"];

/**
 * The preregistered tests in the report's order (the order of the exported situations,
 * then travel before waiting), filtered by network, measure and verdict.
 */
export function forestRows(
  tests: TestRow[],
  cells: Cells["cells"],
  filters: { network: NetworkFilter; metric: MetricFilter; verdicts: ReadonlySet<TestVerdict> },
): TestRow[] {
  const position = (t: TestRow) =>
    cells.findIndex(
      (c) => c.network === t.network && c.scenario === t.scenario && c.demand === t.demand,
    );
  return tests
    .filter((t) => t.family === "hybrid")
    .filter((t) => filters.network === "all" || t.network === filters.network)
    .filter((t) => filters.metric === "all" || t.metric === filters.metric)
    .filter((t) => filters.verdicts.has(collapse(t.verdict)))
    .sort(
      (a, b) =>
        position(a) - position(b) || (a.metric === b.metric ? 0 : a.metric === "travel" ? -1 : 1),
    );
}

/** A "true loss beyond the margin" counts as a true loss in the legend. */
export function collapse(v: TestVerdict): TestVerdict {
  return v === "lossBeyond" ? "loss" : v;
}

/** The whole range of the intervals, with 0 and the margin always in view: no cut axis. */
export function xBounds(rows: TestRow[], margin: number): [number, number] {
  const lo = Math.min(-margin, ...rows.map((r) => r.low));
  const hi = Math.max(0, ...rows.map((r) => r.high));
  const step = 10; // the axis ticks
  return [Math.floor((lo - 1) / step) * step, Math.ceil((hi + 1) / step) * step];
}

/** The colour of a verdict's mark (the forest plot and the interval lines). */
export function verdictColor(v: TestVerdict, t: ChartTokens): string {
  if (v === "best") return t.good;
  if (v === "noninf") return t.candidate;
  if (v === "loss" || v === "lossBeyond") return t.critical;
  return t.wide;
}

/** The filters shared by the forest plot and the final table. */
export function useForestFilters() {
  const [network, setNetwork] = useState<NetworkFilter>("all");
  const [metric, setMetric] = useState<MetricFilter>("all");
  const [verdicts, setVerdicts] = useState<ReadonlySet<TestVerdict>>(new Set(VERDICT_ORDER));
  const toggle = (v: TestVerdict) =>
    setVerdicts((current) => {
      const next = new Set(current);
      if (next.has(v)) next.delete(v);
      else next.add(v);
      return next.size ? next : new Set(VERDICT_ORDER);
    });
  return { network, setNetwork, metric, setMetric, verdicts, toggle };
}

export type ForestFilters = ReturnType<typeof useForestFilters>;
