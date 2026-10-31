/**
 * What the final evaluation allows to say, computed from the exported tests: the pages
 * write sentences around these numbers, never numbers of their own.
 */
import type { FinalController } from "@/shared/schemas";
import type { Study, TestRow } from "@/shared/schemas/combined";

export interface MainSummary {
  total: number;
  /** proven non-inferior, superior ones included */
  holds: number;
  best: number;
  loss: number;
  wide: number;
  bestRows: TestRow[];
  lossRows: TestRow[];
  wideRows: TestRow[];
  lossMin: number;
  lossMax: number;
  /** the "too wide" ones on real_district at peak */
  wideRealPeak: number;
  /** "too wide" with a clearly unfavourable estimate (below the margin) */
  wideUnfavourable: TestRow[];
}

/** The preregistered family "hybrid": the candidate against the best reference. */
export const mainTests = (tests: TestRow[]) => tests.filter((t) => t.family === "hybrid");

export function summarize(tests: TestRow[], study: Pick<Study, "marginPct">): MainSummary {
  const main = mainTests(tests);
  const of = (v: TestRow["verdict"]) => main.filter((t) => t.verdict === v);
  const bestRows = of("best");
  const lossRows = main.filter((t) => t.verdict === "loss" || t.verdict === "lossBeyond");
  const wideRows = of("wide");
  const losses = lossRows.map((t) => t.gain);
  return {
    total: main.length,
    holds: bestRows.length + of("noninf").length,
    best: bestRows.length,
    loss: lossRows.length,
    wide: wideRows.length,
    bestRows,
    lossRows,
    wideRows,
    lossMin: Math.min(...losses),
    lossMax: Math.max(...losses),
    wideRealPeak: wideRows.filter((t) => t.network === "real_district" && t.demand === "peak")
      .length,
    wideUnfavourable: wideRows.filter((t) => t.gain < -study.marginPct),
  };
}

/** One test of the main family, by situation and measure. */
export function findTest(
  tests: TestRow[],
  network: string,
  scenario: string,
  demand: string,
  metric: TestRow["metric"],
): TestRow | undefined {
  return mainTests(tests).find(
    (t) =>
      t.network === network &&
      t.scenario === scenario &&
      t.demand === demand &&
      t.metric === metric,
  );
}

/** Mean delay of the emergency vehicles of a controller (grid, emergencies). */
export function ambulanceDelay(
  final: FinalController,
  controller: string,
  demand: string,
): FinalController["ambulanceDelays"][number] | undefined {
  return final.ambulanceDelays.find((d) => d.controller === controller && d.demand === demand);
}
