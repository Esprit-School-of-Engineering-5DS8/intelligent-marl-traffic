/**
 * Data contract of the dashboard: every type is inferred from these Zod schemas, which the
 * backend's Pydantic models mirror (api/schemas.py). Values are those of the project's
 * result files (results/summary/summary.csv, results/extra/, decision and training logs).
 */
import { z } from "zod";

export const Controller = z.enum([
  "ft",
  "act",
  "mp",
  "ev_rule",
  "ev_rule_mp",
  "ped_rule_mp",
  "ind",
  "coop",
  "coop_eco05",
  "coop_eco",
  "coop_full",
  "coop_forecast",
  "dqn",
]);
export const BASELINES = ["ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp"] as const;
export const LEARNED = [
  "ind",
  "coop",
  "coop_eco05",
  "coop_eco",
  "coop_full",
  "coop_forecast",
  "dqn",
] as const;

export const Network = z.enum(["grid4x4", "grid8x8", "real_district", "real_district_ped"]);
export const Scenario = z.enum([
  "normal",
  "incident",
  "emergency",
  "pedestrians",
  "buses",
  "sensor_noise",
  "comm_dropout_10",
  "comm_dropout_30",
  "comm_dropout_50",
]);
export const Demand = z.enum(["low", "medium", "peak", "rush_profile"]);

/** Metrics of the report (results/raw) and of the dashboard's extra runs (results/extra). */
export const Metric = z.enum([
  "mean_travel_time",
  "mean_waiting_time",
  "mean_time_loss",
  "stops_per_vehicle",
  "throughput_per_h",
  "mean_queue",
  "p95_waiting_time",
  "co2_g_per_km",
  "co2_total_kg",
  "ped_mean_waiting_time",
  "ped_max_waiting_time",
  "ev_delay",
  "ev_travel_time",
  "bus_delay",
  "person_weighted_delay",
  "ssm_conflicts_per_1000_veh",
  "ped_p95_waiting_time",
  "ped_crossings_in_green_pct",
  "ped_green_slope_s_per_person",
  "ev_stops_at_red_mean",
  "ev_eta_error_mean_s",
  "ev_eta_abs_error_mean_s",
  "reward_delay",
  "reward_co2",
  "reward_ev",
  "reward_ped",
]);
export const Cell = z.object({ network: Network, scenario: Scenario, demand: Demand });

/** Aggregated result (95 % CI by bootstrap over training runs and test seeds). */
export const SummaryRow = Cell.extend({
  method: Controller,
  metric: Metric,
  n: z.number().int().positive(),
  nTrain: z.number().int().nonnegative(),
  mean: z.number(),
  ciLo: z.number(),
  ciHi: z.number(),
  std: z.number(),
});
export const Comparison = Cell.extend({
  method: Controller,
  reference: Controller,
  metric: Metric,
  mean: z.number(),
  referenceMean: z.number(),
  pairedImprovementPct: z.number(),
  pairedCiLo: z.number(),
  pairedCiHi: z.number(),
  pHolm: z.number().min(0).max(1),
  significant: z.boolean(),
  family: z.enum(["core", "exploratory", "dqn"]),
});
export const TimeseriesPoint = z.object({
  minute: z.number().int().nonnegative(),
  halting: z.number(),
  running: z.number(),
  waiting: z.number(),
  meanWaitingTime: z.number(),
  meanSpeed: z.number(),
});
export const RunSeries = z.object({
  runId: z.string(),
  method: Controller,
  cell: Cell,
  seed: z.number().int(),
  points: z.array(TimeseriesPoint),
});
export const TrainingPoint = z.object({
  timesteps: z.number().int(),
  episodeReward: z.number(),
  meanHalting: z.number(),
  demand: Demand,
});

/** Network geometry, SUMO coordinates in metres. */
export const Point = z.tuple([z.number(), z.number()]);
export const Lane = z.object({
  id: z.string(),
  edge: z.string(),
  shape: z.array(Point).min(2),
  width: z.number().positive(),
  allows: z.enum(["vehicle", "pedestrian", "both"]),
});
export const Junction = z.object({
  id: z.string(),
  position: Point,
  signalised: z.boolean(),
  shape: z.array(Point),
});
export const NetworkGeometry = z.object({
  network: Network,
  bounds: z.tuple([Point, Point]),
  lanes: z.array(Lane),
  junctions: z.array(Junction),
});

/** One simulated second, live or replayed. */
export const VehicleKind = z.enum(["car", "bus", "emergency", "incident"]);
export const VehicleState = z.object({
  id: z.string(),
  kind: VehicleKind,
  x: z.number(),
  y: z.number(),
  angle: z.number(),
  speed: z.number().nonnegative(),
});
export const PersonState = z.object({
  id: z.string(),
  x: z.number(),
  y: z.number(),
  angle: z.number(),
  waiting: z.boolean(),
});
export const SignalState = z.object({
  tls: z.string(),
  state: z.string().regex(/^[rRyYgGsuoO]+$/),
  phase: z.number().int(),
  remainingS: z.number().nonnegative(),
});
export const SimFrame = z.object({
  runId: z.string(),
  side: z.enum(["left", "right"]),
  t: z.number().nonnegative(),
  vehicles: z.array(VehicleState),
  persons: z.array(PersonState),
  signals: z.array(SignalState),
});

/** A scenario to run: the options of scripts/demo_side_by_side.py. */
export const ScenarioRequest = z
  .object({
    network: Network,
    demand: Demand,
    events: z.array(Scenario.exclude(["normal"])).default([]),
    seed: z.number().int().min(0).max(999),
    left: Controller,
    right: Controller,
    quick: z.boolean().default(true),
  })
  .refine((r) => r.left !== r.right, { message: "two different controllers", path: ["right"] });
export const RunStatus = z.enum(["queued", "running", "done", "failed"]);
export const Run = z.object({
  id: z.string(),
  request: ScenarioRequest,
  status: RunStatus,
  createdAt: z.string(),
  error: z.string().optional(),
});

/** Assistant: the page the user sees, the tools the model may call, the streamed events. */
export const PageContext = z.object({
  page: z.string(),
  filters: Cell.partial().extend({ controllers: z.array(Controller).optional() }),
});
export const ToolCall = z.discriminatedUnion("name", [
  z.object({ name: z.literal("getKpis"), args: z.object({ cell: Cell, controller: Controller }) }),
  z.object({
    name: z.literal("compareControllers"),
    args: z.object({ cell: Cell, a: Controller, b: Controller, metric: Metric }),
  }),
  z.object({
    name: z.literal("focusIntersection"),
    args: z.object({ network: Network, junction: z.string() }),
  }),
  z.object({ name: z.literal("runScenario"), args: ScenarioRequest }),
  z.object({
    name: z.literal("generateChart"),
    args: z.object({ cell: Cell, metric: Metric, controllers: z.array(Controller).min(1) }),
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

export type Controller = z.infer<typeof Controller>;
export type Network = z.infer<typeof Network>;
export type Scenario = z.infer<typeof Scenario>;
export type Demand = z.infer<typeof Demand>;
export type Metric = z.infer<typeof Metric>;
export type Cell = z.infer<typeof Cell>;
export type SummaryRow = z.infer<typeof SummaryRow>;
export type Comparison = z.infer<typeof Comparison>;
export type TimeseriesPoint = z.infer<typeof TimeseriesPoint>;
export type RunSeries = z.infer<typeof RunSeries>;
export type TrainingPoint = z.infer<typeof TrainingPoint>;
export type NetworkGeometry = z.infer<typeof NetworkGeometry>;
export type VehicleKind = z.infer<typeof VehicleKind>;
export type SimFrame = z.infer<typeof SimFrame>;
export type ScenarioRequest = z.infer<typeof ScenarioRequest>;
export type Run = z.infer<typeof Run>;
export type PageContext = z.infer<typeof PageContext>;
export type ToolCall = z.infer<typeof ToolCall>;
export type ChatEvent = z.infer<typeof ChatEvent>;
