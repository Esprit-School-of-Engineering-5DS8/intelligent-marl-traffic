/**
 * Data contract of the dashboard. Every file is validated on arrival; the types are
 * inferred from these schemas. The files are written by scripts/export_dashboard_data.py
 * and scripts/record_replay.py from the project's result files, and the FastAPI backend
 * (api/) serves the same files, so the two data sources show identical numbers.
 *
 * Controllers and metrics are open strings: a new experiment must not break the screen.
 * Known ones get labels, colours and units in shared/domain.
 */
import { z } from "zod";

const num = z.number();
/** JSON has no NaN: a missing measurement is exported as null. */
const maybe = z.number().nullable();

export const Cell = z.object({ network: z.string(), scenario: z.string(), demand: z.string() });

export const SummaryRow = Cell.extend({
  method: z.string(),
  metric: z.string(),
  n: num,
  nTrain: num,
  mean: maybe,
  ciLo: maybe,
  ciHi: maybe,
  std: maybe,
});
export const Summary = z.array(SummaryRow);

export const Comparison = Cell.extend({
  method: z.string(),
  reference: z.string(),
  metric: z.string(),
  mean: maybe,
  referenceMean: maybe,
  improvementPct: maybe,
  pairedImprovementPct: maybe,
  pairedCiLo: maybe,
  pairedCiHi: maybe,
  pValue: maybe,
  pHolm: maybe,
  cliffsDelta: maybe,
  effect: z.string().nullable(),
  significant: z.boolean(),
  n: num,
  comparison: z.string(),
  family: z.string(),
});
export const Comparisons = z.array(Comparison);

export const LlmRun = z.object({
  runId: z.string(),
  network: z.string(),
  scenario: z.string(),
  demand: z.string(),
  method: z.string(),
  seed: num,
  calls: maybe,
  success: maybe,
  partial: maybe,
  fallbacks: maybe,
  retries: maybe,
  tokensIn: maybe,
  tokensOut: maybe,
  cachedTokens: maybe,
  latencyS: maybe,
  costUsd: maybe,
  wallS: maybe,
});
export type LlmRun = z.infer<typeof LlmRun>;
export const LlmRuns = z.array(LlmRun);

export const Meta = z.object({
  generatedAt: z.string(),
  cells: z.array(Cell.extend({ methods: z.array(z.string()) })),
  methods: z.array(z.string()),
  metrics: z.array(z.string()),
  runs: z.number().nullable(),
  extraRuns: num,
  dqnAvailable: z.boolean(),
  replays: z.array(z.object({ id: z.string(), left: z.string(), right: z.string(), window: num })),
  timeseries: z.array(z.string()),
  decisions: z.array(
    z.object({
      runId: z.string(),
      method: z.string(),
      network: z.string(),
      scenario: z.string(),
      demand: z.string(),
      seed: num,
      decisions: num,
    }),
  ),
  training: z.array(
    z.object({ agent: z.string(), network: z.string(), seeds: z.array(num), episodes: num }),
  ),
  networks: z.array(z.object({ network: z.string() }).passthrough()),
});

const Series = z.array(maybe);
export const TimeseriesCell = z.object({
  cell: Cell,
  methods: z.record(
    z.string(),
    z
      .object({
        minute: z.array(num),
        halting: Series,
        running: Series,
        waiting: Series,
        meanWaitingTime: Series,
        meanSpeed: Series,
      })
      .catchall(Series),
  ),
});

export const DistributionCell = z.object({
  cell: Cell,
  methods: z.record(
    z.string(),
    z.object({ from: z.array(num), to: z.array(num), vehicles: z.array(num) }),
  ),
});

export const Decisions = z.object({
  runId: z.string(),
  method: z.string(),
  network: z.string(),
  scenario: z.string(),
  demand: z.string(),
  seed: num,
  agents: z.array(z.string()),
  time: z.array(num),
  agent: z.array(z.string()),
  requested: z.array(num),
  executed: z.array(num),
  shield: z.array(z.string()),
  dependsOn: z.array(z.string()),
  explanation: z.array(z.string()),
});

export const TrainingRun = z.object({
  seed: num,
  totalTimesteps: z.number().nullable().optional(),
  algorithm: z.string(),
  timesteps: z.array(num),
  episodeReward: z.array(maybe),
  meanHalting: z.array(maybe),
  demand: z.array(z.string()),
  switches: z.array(num),
  shieldMinGreen: z.array(num),
});
export const Training = z.object({
  agent: z.string(),
  network: z.string(),
  runs: z.array(TrainingRun),
});

export const PedestrianGreens = z.object({
  cells: z.record(
    z.string(),
    z.record(
      z.string(),
      z.object({
        greens: num,
        crossed: num,
        crowd: z.array(num),
        meanDuration: z.array(maybe),
        count: z.array(num),
      }),
    ),
  ),
});

export const EmergencyVehicle = z
  .object({
    runId: z.string(),
    method: z.string(),
    network: z.string(),
    scenario: z.string(),
    demand: z.string(),
    seed: num,
  })
  .catchall(z.union([z.number(), z.string(), z.boolean(), z.null()]));
export const EmergencyLog = z.object({ vehicles: z.array(EmergencyVehicle) });

/** Network geometry, SUMO coordinates in metres. */
export const Point = z.tuple([num, num]);
export const Lane = z.object({
  id: z.string(),
  edge: z.string(),
  shape: z.array(Point).min(2),
  width: num,
  allows: z.enum(["vehicle", "pedestrian", "both"]),
  kind: z.enum(["normal", "internal", "crossing"]),
});
export const Junction = z.object({
  id: z.string(),
  position: Point,
  signalised: z.boolean(),
  shape: z.array(Point),
});
export const SignalLinks = z.object({
  tls: z.string(),
  links: z.array(z.object({ index: num, lane: z.string(), position: Point })),
});
export const NetworkGeometry = z.object({
  network: z.string(),
  bounds: z.tuple([Point, Point]),
  lanes: z.array(Lane),
  junctions: z.array(Junction),
  signals: z.array(SignalLinks),
});

/**
 * Side-by-side replay. Frames are flat integer arrays: vehicles as
 * [id, kind, x dm, y dm, angle deg, speed dm/s] repeated, persons as [x dm, y dm, waiting].
 * Signal states follow the order of `signals`.
 */
export const ReplayFrame = z.object({
  t: num,
  v: z.array(num),
  p: z.array(num),
  s: z.array(z.string()),
});
export const ReplaySide = z.object({
  method: z.string(),
  kpis: z.record(z.string(), maybe),
  frames: z.array(ReplayFrame),
  events: z.array(z.object({ t: num, type: z.string(), id: z.string() })),
});
export const Replay = z.object({
  id: z.string(),
  network: z.string(),
  scenario: z.string(),
  demand: z.string(),
  seed: num,
  every: num,
  window: num,
  start: num,
  signals: z.array(z.string()),
  kinds: z.array(z.string()),
  sides: z.object({ left: ReplaySide, right: ReplaySide }),
});

/** A scenario to run on the backend: the options of scripts/record_replay.py. */
export const NETWORKS = ["grid4x4", "real_district"] as const;
export const EVENTS = ["emergency", "pedestrians", "incident", "buses"] as const;
export const DEMANDS = ["low", "medium", "peak"] as const;
export const ScenarioRequest = z
  .object({
    network: z.enum(NETWORKS),
    demand: z.enum(DEMANDS),
    events: z.array(z.enum(EVENTS)),
    seed: z.number().int().min(0).max(999),
    left: z.string().min(1),
    right: z.string().min(1),
  })
  .refine((r) => r.left !== r.right, { message: "different", path: ["right"] });
export const RunStatus = z.enum(["queued", "running", "done", "failed"]);
export const Run = z.object({
  id: z.string(),
  request: z.record(z.string(), z.unknown()),
  status: RunStatus,
  createdAt: z.string(),
  replayId: z.string().nullable().optional(),
  log: z.array(z.string()).optional(),
  error: z.string().nullable().optional(),
});

/** Assistant: the page the user sees, the tools the model may call, the streamed events. */
export const PageContext = z.object({
  page: z.string(),
  cell: Cell.partial().optional(),
  controllers: z.array(z.string()).optional(),
});
export const ToolCall = z.discriminatedUnion("name", [
  z.object({ name: z.literal("getKpis"), args: z.object({ cell: Cell, controller: z.string() }) }),
  z.object({
    name: z.literal("compareControllers"),
    args: z.object({ cell: Cell, a: z.string(), b: z.string(), metric: z.string() }),
  }),
  z.object({
    name: z.literal("focusIntersection"),
    args: z.object({ network: z.string(), junction: z.string() }),
  }),
  z.object({ name: z.literal("runScenario"), args: ScenarioRequest }),
  z.object({
    name: z.literal("generateChart"),
    args: z.object({ cell: Cell, metric: z.string(), controllers: z.array(z.string()).min(1) }),
  }),
]);
/** Tools that change state: the user confirms before they run. */
export const MUTATING_TOOLS: ReadonlySet<ToolCall["name"]> = new Set(["runScenario"]);
export const ChatEvent = z.discriminatedUnion("type", [
  z.object({ type: z.literal("token"), text: z.string() }),
  z.object({ type: z.literal("tool_call"), id: z.string(), call: ToolCall }),
  z.object({ type: z.literal("source"), file: z.string() }),
  z.object({ type: z.literal("done"), writtenBy: z.enum(["model", "code"]) }),
  z.object({ type: z.literal("error"), message: z.string() }),
]);

export type Cell = z.infer<typeof Cell>;
export type SummaryRow = z.infer<typeof SummaryRow>;
export type Comparison = z.infer<typeof Comparison>;
export type Meta = z.infer<typeof Meta>;
export type TimeseriesCell = z.infer<typeof TimeseriesCell>;
export type DistributionCell = z.infer<typeof DistributionCell>;
export type Decisions = z.infer<typeof Decisions>;
export type Training = z.infer<typeof Training>;
export type TrainingRun = z.infer<typeof TrainingRun>;
export type PedestrianGreens = z.infer<typeof PedestrianGreens>;
export type EmergencyLog = z.infer<typeof EmergencyLog>;
export type NetworkGeometry = z.infer<typeof NetworkGeometry>;
export type Replay = z.infer<typeof Replay>;
export type ReplayFrame = z.infer<typeof ReplayFrame>;
export type ScenarioRequest = z.infer<typeof ScenarioRequest>;
export type Run = z.infer<typeof Run>;
export type PageContext = z.infer<typeof PageContext>;
export type ToolCall = z.infer<typeof ToolCall>;
export type ChatEvent = z.infer<typeof ChatEvent>;
