import type { Cell, Comparison, SummaryRow } from "@/shared/schemas";

import { sameCell } from "./cells";

/** Lookups over the summary and comparison tables. */
export function indexSummary(rows: SummaryRow[]) {
  const map = new Map<string, SummaryRow>();
  for (const r of rows)
    map.set(`${r.network}|${r.scenario}|${r.demand}|${r.method}|${r.metric}`, r);
  return {
    get: (cell: Cell, method: string, metric: string) =>
      map.get(`${cell.network}|${cell.scenario}|${cell.demand}|${method}|${metric}`),
    methods: (cell: Cell, metric?: string) => [
      ...new Set(
        rows
          .filter((r) => sameCell(r, cell) && (!metric || r.metric === metric))
          .map((r) => r.method),
      ),
    ],
    metrics: (cell: Cell) => [
      ...new Set(rows.filter((r) => sameCell(r, cell)).map((r) => r.metric)),
    ],
  };
}

export type SummaryIndex = ReturnType<typeof indexSummary>;

export function findComparison(
  comparisons: Comparison[],
  cell: Cell,
  method: string,
  reference: string,
  metric: string,
): Comparison | undefined {
  return comparisons.find(
    (c) =>
      sameCell(c, cell) && c.method === method && c.reference === reference && c.metric === metric,
  );
}
