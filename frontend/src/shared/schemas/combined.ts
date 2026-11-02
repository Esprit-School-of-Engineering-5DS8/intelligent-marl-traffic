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

/** The candidate with the LLM strategist (scripts/llm_loop.py, exploratory). */
export const StrategyMode = z.enum(["equilibre", "fluidite", "agent"]);
const LlmMetric = z.object({
  llm: maybe,
  candidate: maybe,
  gain: maybe,
  oracle: maybe.optional(),
  placeboBest: maybe.optional(),
});
const LlmCell = Situation.extend({
  seeds: num,
  switches: num,
  shares: z.record(StrategyMode, num),
  travel: LlmMetric.optional(),
  waiting: LlmMetric.optional(),
  ambulances: LlmMetric.optional(),
});
const Paired = z.object({ gain: num, low: num, high: num, pairs: num }).nullable();
export const LlmLoop = z.object({
  source: z.string(),
  model: z.string(),
  prompt: z.string(),
  windowS: num,
  beta: num,
  episodes: num,
  calls: num,
  validRate: num,
  latencyP50S: num,
  shares: z.record(StrategyMode, num),
  validation: z.array(LlmCell),
  test: z.array(LlmCell),
  testOverall: z.object({
    travel: Paired.optional(),
    waiting: Paired.optional(),
    ambulances: Paired.optional(),
  }),
  timeline: Situation.extend({
    seed: num,
    end: num,
    calls: z.array(
      z.object({
        time: num,
        appliesAt: num,
        mode: StrategyMode,
        valid: z.boolean(),
        reason: z.string(),
        latency: num,
        halted: maybe,
        backlog: maybe,
      }),
    ),
  }),
  advisor: z
    .object({
      travel: Paired.optional(),
      waiting: Paired.optional(),
      ambulances: Paired.optional(),
    })
    .optional(),
});

export type StrategyMode = z.infer<typeof StrategyMode>;
export type LlmLoop = z.infer<typeof LlmLoop>;

/** Paris and Barcelona with every controller (scripts/bigcity.py demo, exploratory). */
export const Cities = z.object({
  source: z.string(),
  cities: z.array(
    z.object({
      network: z.string(),
      lights: num,
      driven: num,
      drivenLightsPct: num,
      drivenLanesPct: num,
      wideLights: num,
      scale: num,
      seeds: z.array(num),
      vehPerH: maybe,
      results: z.array(
        z.object({
          controller: z.string(),
          scenario: z.string(),
          n: num,
          travel: maybe,
          waiting: maybe,
          teleports: maybe,
          unfinished: maybe,
          ambulances: maybe,
        }),
      ),
      llmShares: z.record(StrategyMode, num).nullable(),
      map: z.object({
        width: num,
        height: num,
        edges: z.array(z.array(num)),
        lights: z.array(z.object({ x: num, y: num, driven: z.boolean() })),
      }),
    }),
  ),
});
export type Cities = z.infer<typeof Cities>;
