import { describe, expect, it } from "vitest";

import { firstWith, orderReplays, replayEvents, type ReplayEntry } from "./catalog";

const r = (id: string, left: string, right: string, llm = false): ReplayEntry => ({
  id,
  left,
  right,
  window: 480,
  llm,
});

const list = [
  r("grid4x4__pedestrians__peak__s3", "ped_rule_mp", "coop_full"),
  r("grid4x4__emergency+pedestrians__peak__s3", "mp", "hybrid_h2"),
  r("paris__emergency__peak__s0", "mp", "hybrid_h2_llmstrat", true),
];

describe("replay catalog", () => {
  it("offers the LLM first, then our candidate, then the first study", () => {
    expect(orderReplays(list).map((x) => x.id)).toEqual([
      "paris__emergency__peak__s0",
      "grid4x4__emergency+pedestrians__peak__s3",
      "grid4x4__pedestrians__peak__s3",
    ]);
  });

  it("reads the events from the id", () => {
    expect(replayEvents("grid4x4__emergency+pedestrians__peak__s3")).toEqual([
      "emergency",
      "pedestrians",
    ]);
  });

  it("finds a replay with pedestrians, our candidate's first", () => {
    expect(firstWith(list, "pedestrians")?.id).toBe("grid4x4__emergency+pedestrians__peak__s3");
    expect(firstWith(list, "buses")).toBeUndefined();
  });
});
