// Every file of the dashboard export must pass its schema: a file that does not is a
// widget showing an error instead of the results.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";
import type { ZodType } from "zod";

import {
  Comparisons,
  Decisions,
  DistributionCell,
  EmergencyLog,
  FinalController,
  Meta,
  NetworkGeometry,
  PedestrianGreens,
  Replay,
  Summary,
  TimeseriesCell,
  Training,
} from "./index";

const DATA = join(process.cwd(), "public", "data");

const SCHEMAS: [RegExp, ZodType][] = [
  [/^meta$/, Meta],
  [/^summary$/, Summary],
  [/^comparisons$/, Comparisons],
  [/^pedestrian_greens$/, PedestrianGreens],
  [/^emergency_log$/, EmergencyLog],
  [/^final_controller$/, FinalController],
  [/^timeseries\//, TimeseriesCell],
  [/^distributions\//, DistributionCell],
  [/^decisions\//, Decisions],
  [/^training\//, Training],
  [/^networks\//, NetworkGeometry],
  [/^replays\//, Replay],
];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : path.endsWith(".json") ? [path] : [];
  });
}

const all = files(DATA).map((path) =>
  relative(DATA, path)
    .split(sep)
    .join("/")
    .replace(/\.json$/, ""),
);

describe("exported data", () => {
  it("every file has a schema", () => {
    expect(all.filter((id) => !SCHEMAS.some(([re]) => re.test(id)))).toEqual([]);
  });

  it.each(all)("%s passes its schema", (id) => {
    const schema = SCHEMAS.find(([re]) => re.test(id))?.[1];
    if (!schema) return;
    const result = schema.safeParse(JSON.parse(readFileSync(join(DATA, `${id}.json`), "utf-8")));
    const issue = result.success ? null : result.error.issues[0];
    expect(issue ? `${issue.path.join(".")}: ${issue.message}` : null).toBeNull();
  });
});
