import { describe, expect, it } from "vitest";

import type { Replay } from "@/shared/schemas";

import { duration, footprint, sceneAt, sceneStats, signalColor } from "./scene";

const side = (method: string) => ({
  method,
  kpis: {},
  events: [],
  frames: [
    // vehicle 7: car at (10 m, 20 m) heading east at 10 m/s, then 20 m further
    { t: 0, v: [7, 0, 100, 200, 90, 100], p: [50, 60, 1], s: ["Gr"] },
    { t: 2, v: [7, 0, 300, 200, 90, 0, 8, 2, 0, 0, 0, 0], p: [], s: ["rG"] },
  ],
});
const replay: Replay = {
  id: "grid4x4__emergency__peak__s3",
  network: "grid4x4",
  scenario: "emergency",
  demand: "peak",
  seed: 3,
  every: 2,
  window: 4,
  start: 900,
  signals: ["A0"],
  kinds: ["car", "bus", "emergency", "incident"],
  sides: { left: side("ft"), right: side("coop_full") },
};

describe("replay scene", () => {
  it("interpolates positions between recorded frames", () => {
    const scene = sceneAt(replay, "left", 1);
    expect(scene.vehicles).toHaveLength(1);
    expect(scene.vehicles[0]).toMatchObject({ id: 7, kind: "car", x: 20, y: 20, speed: 5 });
    expect(scene.signals).toEqual(["Gr"]);
  });

  it("decodes kinds, pedestrians and the last frame", () => {
    const scene = sceneAt(replay, "right", 2);
    expect(scene.vehicles.map((v) => v.kind)).toEqual(["car", "emergency"]);
    expect(sceneAt(replay, "left", 0).persons).toEqual([{ x: 5, y: 6, waiting: true }]);
    expect(duration(replay)).toBe(2);
  });

  it("counts halted vehicles", () => {
    expect(sceneStats(sceneAt(replay, "left", 2))).toMatchObject({ vehicles: 2, halted: 2 });
  });

  it("draws a vehicle behind its front bumper", () => {
    const [front] = footprint({ id: 1, kind: "car", x: 0, y: 0, angle: 90, speed: 0 });
    const corners = footprint({ id: 1, kind: "car", x: 0, y: 0, angle: 90, speed: 0 });
    expect(Math.max(...corners.map(([x]) => x))).toBeCloseTo(0);
    expect(Math.min(...corners.map(([x]) => x))).toBeCloseTo(-4.6);
    expect(front?.[0]).toBeCloseTo(0);
  });

  it("maps SUMO signal letters", () => {
    expect([..."GgyrsO"].map(signalColor)).toEqual([
      "green",
      "green",
      "yellow",
      "red",
      "red",
      "off",
    ]);
  });
});
