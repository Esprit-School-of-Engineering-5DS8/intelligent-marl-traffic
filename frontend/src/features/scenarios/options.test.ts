import { describe, expect, it } from "vitest";

import type { Meta } from "@/shared/schemas";

import { creationOptions, defaultRequest, fitRequest, presets } from "./options";

const study = ["act", "coop_full", "ev_rule_mp", "ft", "mp", "ped_rule_mp"];
const meta = {
  methods: study,
  creation: {
    networks: [
      {
        network: "grid4x4",
        events: ["emergency", "pedestrians", "incident", "buses"],
        methods: ["hybrid_h2", "hybrid_h2_llmstrat", "ft", "act", "mp", "coop_full"],
        scale: 1,
        window: 480,
        bigCity: false,
      },
      {
        network: "paris",
        events: ["emergency"],
        methods: ["hybrid_h2", "hybrid_h2_llmstrat", "ft", "mp", "coop_full"],
        scale: 0.5,
        window: 300,
        bigCity: true,
      },
      {
        network: "atlantis",
        events: ["emergency"],
        methods: ["ft"],
        scale: 1,
        window: 300,
        bigCity: false,
      },
    ],
    demands: ["low", "medium", "peak"],
    candidate: "hybrid_h2",
    llm: "hybrid_h2_llmstrat",
  },
} as unknown as Meta;

describe("scenario creation options", () => {
  it("reads the exported catalog and ignores unknown networks", () => {
    const o = creationOptions(meta);
    expect(o.networks.map((n) => n.network)).toEqual(["grid4x4", "paris"]);
    expect(o.networks[1]?.scale).toBe(0.5);
  });

  it("falls back to the first study without a catalog", () => {
    const o = creationOptions({ ...meta, creation: undefined });
    expect(o.networks.map((n) => n.network)).toEqual(["grid4x4", "real_district"]);
    expect(o.networks[0]?.methods).toEqual(study);
  });

  it("defaults to our candidate against Max-Pressure, with ambulances and pedestrians", () => {
    const r = defaultRequest(creationOptions(meta));
    expect(r).toMatchObject({ network: "grid4x4", left: "mp", right: "hybrid_h2" });
    expect(r.events).toEqual(["emergency", "pedestrians"]);
  });

  it("drops the events a network cannot generate", () => {
    const o = creationOptions(meta);
    const paris = o.networks[1]!;
    const r = fitRequest(defaultRequest(o), paris, o);
    expect(r.network).toBe("paris");
    expect(r.events).toEqual(["emergency"]);
  });

  it("replaces controllers the network does not offer", () => {
    const o = creationOptions(meta);
    const paris = o.networks[1]!;
    const r = fitRequest({ ...defaultRequest(o), left: "act", right: "ped_rule_mp" }, paris, o);
    expect(r.left).not.toBe(r.right);
    expect(paris.methods).toContain(r.left);
    expect(r.right).toBe("hybrid_h2");
  });

  it("offers the duels whose two controllers exist on the network", () => {
    const o = creationOptions(meta);
    expect(presets(o.networks[0]!, o).map((p) => p.key)).toEqual(["vsMp", "vsFt", "vsLlm"]);
    const only = { ...o.networks[0]!, methods: ["hybrid_h2", "ft"] };
    expect(presets(only, o).map((p) => p.key)).toEqual(["vsFt"]);
  });
});
