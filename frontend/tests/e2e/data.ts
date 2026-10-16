// The exported results the dashboard reads, loaded by the tests to check the numbers shown.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const DATA = new URL("../../public/data/", import.meta.url);

export interface Row {
  network: string;
  scenario: string;
  demand: string;
  method: string;
  metric: string;
  mean: number | null;
}

export interface Test {
  network: string;
  scenario: string;
  demand: string;
  method: string;
  reference: string;
  metric: string;
  pairedImprovementPct: number | null;
  significant: boolean;
}

export const read = <T>(file: string): T =>
  JSON.parse(readFileSync(fileURLToPath(new URL(file, DATA)), "utf-8")) as T;

export const summary = read<Row[]>("summary.json");
export const comparisons = read<Test[]>("comparisons.json");
export const meta = read<{ replays: { id: string; left: string; right: string }[] }>("meta.json");

export function mean(
  network: string,
  scenario: string,
  demand: string,
  method: string,
  metric: string,
): number {
  const row = summary.find(
    (r) =>
      r.network === network &&
      r.scenario === scenario &&
      r.demand === demand &&
      r.method === method &&
      r.metric === metric,
  );
  if (!row || row.mean === null)
    throw new Error(`no result for ${method} ${metric} ${network} ${scenario} ${demand}`);
  return row.mean;
}

export function test(
  network: string,
  scenario: string,
  demand: string,
  method: string,
  reference: string,
  metric: string,
): Test {
  const found = comparisons.find(
    (c) =>
      c.network === network &&
      c.scenario === scenario &&
      c.demand === demand &&
      c.method === method &&
      c.reference === reference &&
      c.metric === metric,
  );
  if (!found) throw new Error(`no test ${method} vs ${reference} ${metric}`);
  return found;
}

/** A number as the dashboard writes it in French (one decimal under 100, none above). */
export function fr(value: number): string {
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
  return new Intl.NumberFormat("fr", { maximumFractionDigits: digits }).format(value);
}
