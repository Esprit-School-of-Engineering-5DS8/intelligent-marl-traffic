// The sentences of the new pages are built from the exported tests: their numbers must be
// those of the frozen analysis (and of final_controller.json, written by another script).
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { filterCommands, normalize } from "@/app/command/filter";
import { collapse, forestRows, xBounds } from "@/features/final-controller/forest";
import { FinalController } from "@/shared/schemas";
import { Cells, Study, Tests } from "@/shared/schemas/combined";

import { findTest, summarize } from "./claims";

const DATA = join(process.cwd(), "public", "data");
const read = (file: string): unknown => JSON.parse(readFileSync(join(DATA, file), "utf-8"));
const final = FinalController.parse(read("final_controller.json"));
const study = Study.parse(read("combined/study.json"));
const tests = Tests.parse(read("combined/tests.json")).tests;
const cells = Cells.parse(read("combined/cells.json")).cells;

describe("claims of the final evaluation", () => {
  const s = summarize(tests, study);

  it("count the preregistered tests as the figure script does", () => {
    expect(s.total).toBe(final.tests.total);
    expect(s.best).toBe(final.tests.best);
    expect(s.holds).toBe(final.tests.best + final.tests.noninf);
    expect(s.loss).toBe(final.tests.loss);
    expect(s.wide).toBe(final.tests.wide);
    expect(s.total).toBe(study.tests);
  });

  it("report every true loss with its whole interval below zero", () => {
    expect(s.lossRows.every((r) => r.high < 0)).toBe(true);
    expect(s.lossMin).toBe(Math.min(...s.lossRows.map((r) => r.gain)));
  });

  it("find the noisy-sensor waiting test, proven better", () => {
    const sensors = findTest(tests, "grid4x4", "sensor_noise", "peak", "waiting");
    expect(sensors?.verdict).toBe("best");
    expect(sensors?.low).toBeGreaterThan(0);
  });

  it("order the forest like the report and filter it", () => {
    const all = forestRows(tests, cells, {
      network: "all",
      metric: "all",
      verdicts: new Set(["best", "noninf", "loss", "wide"]),
    });
    expect(all).toHaveLength(s.total);
    expect(all[0]).toMatchObject({ network: "grid4x4", scenario: "normal", metric: "travel" });
    const district = forestRows(tests, cells, {
      network: "real_district",
      metric: "waiting",
      verdicts: new Set(["wide"]),
    });
    expect(district.every((r) => r.network === "real_district" && r.metric === "waiting")).toBe(
      true,
    );
    expect(district.every((r) => collapse(r.verdict) === "wide")).toBe(true);
  });

  it("never cut the axis: every interval, 0 and the margin fit", () => {
    const [lo, hi] = xBounds(tests, study.marginPct);
    expect(lo).toBeLessThanOrEqual(Math.min(...tests.map((r) => r.low), -study.marginPct));
    expect(hi).toBeGreaterThanOrEqual(Math.max(...tests.map((r) => r.high), 0));
  });
});

describe("command palette search", () => {
  const commands = [
    { label: "Résultats", hint: "Synthèse" },
    { label: "Robustesse et généralisation", hint: "Résultats" },
    { label: "Paramètres", keywords: "settings" },
  ];

  it("ignores accents and case", () => {
    expect(normalize("Généralisation")).toBe("generalisation");
    expect(filterCommands(commands, "GENERAL").map((c) => c.label)).toEqual([
      "Robustesse et généralisation",
    ]);
  });

  it("needs every word, searches hints and keywords, keeps the order", () => {
    expect(filterCommands(commands, "resultats").map((c) => c.label)).toEqual([
      "Résultats",
      "Robustesse et généralisation",
    ]);
    expect(filterCommands(commands, "settings").map((c) => c.label)).toEqual(["Paramètres"]);
    expect(filterCommands(commands, "robustesse settings")).toEqual([]);
    expect(filterCommands(commands, "  ")).toHaveLength(3);
  });
});
