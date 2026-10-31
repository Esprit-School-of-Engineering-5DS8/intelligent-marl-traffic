/**
 * Data contract of the pages on the combined study (frontend/public/data/combined/),
 * written by scripts/dashboard_combined.py from results/combined (final evaluation),
 * results/exploration/combined (validation) and results/bigcity (stopped attempts).
 */
import { z } from "zod";

const num = z.number();
const maybe = z.number().nullable();
const Situation = z.object({ network: z.string(), scenario: z.string(), demand: z.string() });

export const Study = z.object({
  source: z.string(),
  prereg: z.string(),
  commits: z.array(z.string()),
  episodes: num,
  episodeMinutes: num,
  testSeeds: z.array(num),
  models: num,
  situations: num,
  tests: num,
  marginPct: num,
  alpha: num,
  bootstrapDraws: num,
  validationSeeds: z.array(num),
  variantsTried: num,
  /** the robustness perturbations and the generalisation network, from their configs */
  perturbations: z.object({
    sensorNoise: z.object({ countStdVeh: num, failedPct: num }),
    commDropout: z.object({ lossPct: num, mode: z.string() }),
    buses: z.object({ periodMin: num }),
    generalisation: z.record(
      z.string(),
      z.object({ trainedOn: z.string(), lights: num, trainedLights: num }),
    ),
  }),
  candidate: z.object({
    beta: num,
    decisionS: num,
    evRangeM: num,
    minGreenS: num,
    maxRedS: num,
  }),
});

export const Estimate = z.object({ mean: maybe, low: maybe, high: maybe, n: num });
export const CriterionKey = z.enum(["travel", "waiting", "ambulances", "pedestrians"]);
export const Cells = z.object({
  source: z.string(),
  cells: z.array(
    Situation.extend({
      controllers: z.array(
        z.object({
          controller: z.string(),
          /** the controller was not played here: by construction it is this one */
          sameAs: z.string().nullable(),
          values: z.partialRecord(CriterionKey, Estimate),
        }),
      ),
    }),
  ),
});

export const TestVerdict = z.enum(["best", "noninf", "loss", "lossBeyond", "wide", "notSup"]);
export const Family = z.enum(["hybrid", "hybrid-sup", "hybrid-ablation"]);
export const TestRow = Situation.extend({
  family: Family,
  variant: z.string(),
  metric: z.enum(["travel", "waiting"]),
  reference: z.string(),
  referenceMean: maybe,
  variantMean: maybe,
  gain: num,
  low: num,
  high: num,
  pHolm: num,
  pHolmSup: num.optional(),
  cliff: maybe,
  n: z.string(),
  verdict: TestVerdict,
});
export const Tests = z.object({ source: z.string(), tests: z.array(TestRow) });

export const Layers = z.object({
  source: z.string(),
  cells: z.array(
    Situation.extend({
      layers: z.array(
        z.object({
          layer: z.string(),
          values: z.object({
            travel: z.object({ mean: maybe, gainVsCoopFull: maybe }),
            waiting: z.object({ mean: maybe, gainVsCoopFull: maybe }),
          }),
        }),
      ),
    }),
  ),
});

export const Validation = z.object({
  source: z.string(),
  seeds: z.array(
    z.object({
      seed: num,
      rows: z.array(
        z.object({
          variant: z.string(),
          param: z.enum(["beta", "q"]).nullable(),
          value: maybe,
          rank: num,
          label: z.string(),
          cells: num,
          betterOrEqual: num,
          uncertain: num,
          worse: num,
          evDelay: maybe,
          pedWait: maybe,
        }),
      ),
    }),
  ),
});

export const BilanVerdict = z.enum(["better", "same", "worseSmall", "worseLarge"]);
export const Bilan = z.object({
  source: z.string(),
  references: z.array(
    z.object({
      reference: z.string(),
      better: num,
      same: num,
      worseSmall: num,
      worseLarge: num,
      criteria: num,
    }),
  ),
  detail: z.array(
    Situation.extend({
      reference: z.string(),
      criterion: CriterionKey,
      gain: num,
      low: num,
      high: num,
      verdict: BilanVerdict,
    }),
  ),
});

export const BigCity = z.object({
  source: z.string(),
  status: z.literal("stopped"),
  seed: num,
  cities: z.array(
    z.object({
      network: z.string(),
      lights: num,
      driven: num,
      drivenLightsPct: num,
      drivenLanesPct: num,
      wideLights: num,
    }),
  ),
  parisSweep: z.array(
    z.object({
      controller: z.string(),
      vehPerH: num,
      waiting: num,
      travel: num,
      teleports: num,
      unfinished: num,
    }),
  ),
});

export type Study = z.infer<typeof Study>;
export type Estimate = z.infer<typeof Estimate>;
export type CriterionKey = z.infer<typeof CriterionKey>;
export type Cells = z.infer<typeof Cells>;
export type TestVerdict = z.infer<typeof TestVerdict>;
export type TestRow = z.infer<typeof TestRow>;
export type Tests = z.infer<typeof Tests>;
export type Layers = z.infer<typeof Layers>;
export type Validation = z.infer<typeof Validation>;
export type Bilan = z.infer<typeof Bilan>;
export type BilanVerdict = z.infer<typeof BilanVerdict>;
export type BigCity = z.infer<typeof BigCity>;
