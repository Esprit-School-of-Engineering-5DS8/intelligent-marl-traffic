export type Unit =
  | "s"
  | "kg"
  | "g"
  | "gkm"
  | "vehh"
  | "veh"
  | "count"
  | "pct"
  | "ratio"
  | "ms"
  | "spp"
  | "usd";

export interface MetricInfo {
  unit: Unit;
  /** Which way is an improvement. */
  better: "lower" | "higher" | "none";
}

/** Units and direction of the metrics; their names are translated (metrics.<name>). */
export const METRICS: Record<string, MetricInfo> = {
  mean_travel_time: { unit: "s", better: "lower" },
  mean_waiting_time: { unit: "s", better: "lower" },
  mean_time_loss: { unit: "s", better: "lower" },
  p95_waiting_time: { unit: "s", better: "lower" },
  max_waiting_time: { unit: "s", better: "lower" },
  stops_per_vehicle: { unit: "count", better: "lower" },
  throughput_per_h: { unit: "vehh", better: "higher" },
  mean_queue: { unit: "veh", better: "lower" },
  co2_total_kg: { unit: "kg", better: "lower" },
  co2_g_per_km: { unit: "gkm", better: "lower" },
  fuel_total_kg: { unit: "kg", better: "lower" },
  nox_total_g: { unit: "g", better: "lower" },
  person_weighted_delay: { unit: "s", better: "lower" },
  bus_delay: { unit: "s", better: "lower" },
  ev_delay: { unit: "s", better: "lower" },
  ev_travel_time: { unit: "s", better: "lower" },
  ped_mean_waiting_time: { unit: "s", better: "lower" },
  ped_max_waiting_time: { unit: "s", better: "lower" },
  ped_p95_waiting_time: { unit: "s", better: "lower" },
  ped_crossings_in_green_pct: { unit: "pct", better: "higher" },
  ped_green_slope_s_per_person: { unit: "spp", better: "higher" },
  ev_stops_at_red_mean: { unit: "count", better: "lower" },
  ev_eta_error_mean_s: { unit: "s", better: "none" },
  ev_eta_abs_error_mean_s: { unit: "s", better: "lower" },
  llm_calls: { unit: "count", better: "lower" },
  llm_fallbacks: { unit: "count", better: "lower" },
  llm_prompt_tokens: { unit: "count", better: "lower" },
  llm_completion_tokens: { unit: "count", better: "lower" },
  llm_latency_ms_mean: { unit: "ms", better: "lower" },
  llm_team_calls: { unit: "count", better: "lower" },
  llm_team_operator_calls: { unit: "count", better: "lower" },
  llm_team_emergency_calls: { unit: "count", better: "lower" },
  llm_team_fallbacks: { unit: "count", better: "lower" },
  llm_team_retries: { unit: "count", better: "lower" },
  llm_team_tokens_in: { unit: "count", better: "lower" },
  llm_team_tokens_out: { unit: "count", better: "lower" },
  llm_team_tokens_reasoning: { unit: "count", better: "lower" },
  llm_team_latency_mean_s: { unit: "s", better: "lower" },
  llm_team_estimated_cost_usd: { unit: "usd", better: "lower" },
  ssm_conflicts_per_1000_veh: { unit: "count", better: "lower" },
  hard_braking_events: { unit: "count", better: "lower" },
  gini_waiting_time: { unit: "ratio", better: "lower" },
  teleports_total: { unit: "count", better: "lower" },
  unfinished: { unit: "count", better: "lower" },
  never_inserted: { unit: "count", better: "lower" },
  shield_interventions: { unit: "count", better: "none" },
  inference_ms_per_decision: { unit: "ms", better: "lower" },
  inference_ms_per_step: { unit: "ms", better: "lower" },
  sim_wall_time_s: { unit: "s", better: "none" },
  reward_delay: { unit: "ratio", better: "higher" },
  reward_co2: { unit: "ratio", better: "higher" },
  reward_ev: { unit: "ratio", better: "higher" },
  reward_ped: { unit: "ratio", better: "higher" },
};

export const metricInfo = (m: string): MetricInfo =>
  METRICS[m] ?? { unit: "count", better: "none" };

/** Metrics offered in pickers, most useful first. */
export const MAIN_METRICS = [
  "mean_travel_time",
  "mean_waiting_time",
  "mean_time_loss",
  "person_weighted_delay",
  "p95_waiting_time",
  "stops_per_vehicle",
  "throughput_per_h",
  "co2_total_kg",
  "co2_g_per_km",
  "ped_mean_waiting_time",
  "ev_delay",
  "bus_delay",
];

/** Relative change of `value` against `reference`, signed so that positive = better. */
export function gainPct(metric: string, value: number, reference: number): number | null {
  if (!Number.isFinite(value) || !Number.isFinite(reference) || reference === 0) return null;
  const change = ((value - reference) / Math.abs(reference)) * 100;
  const { better } = metricInfo(metric);
  return better === "higher" ? change : -change;
}
