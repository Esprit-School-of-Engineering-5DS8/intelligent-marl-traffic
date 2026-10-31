/** Controller names, order and colours: the same as the report's figures (analysis/style.py). */
export const METHOD_LABELS: Record<string, string> = {
  ft: "Fixed-Time Baseline",
  act: "Actuated Sensor Baseline",
  mp: "Max-Pressure Baseline",
  ev_rule: "Emergency Preemption Rule",
  ev_rule_mp: "Emergency Rule + Max-Pressure",
  ped_rule_mp: "Pedestrian Cross Rule + Max-Pressure",
  ind: "Independent RL (IPPO)",
  coop: "Cooperative MARL (MAPPO)",
  coop_eco05: "Cooperative MARL (Eco-Optimized)",
  coop_eco: "Cooperative MARL (Zero-Emission)",
  coop_full: "Cooperative MARL (Full Reward)",
  coop_ev: "Cooperative MARL (Emergency Priority)",
  coop_ped: "Cooperative MARL (Pedestrian Safeguard)",
  coop_ev_ped: "Hybrid MARL + Emergency/Pedestrian",
  ind_ev_ped: "Independent RL + Multi-User Priority",
  coop_forecast: "Predictive MARL (Traffic Forecast)",
  coop_full_ev1: "Cooperative MARL (Priority EV)",
  coop_full_ev4: "Cooperative MARL (High-Density Priority)",
  dqn: "Deep Q-Network Agent",
  llm: "Autonomous LLM Traffic Supervisor",
};

const METHOD_COLORS: Record<string, string> = {
  ft: "#8f8d88",
  act: "#7c6cf0",
  mp: "#eb6834",
  ev_rule: "#e34948",
  ev_rule_mp: "#c4553f",
  ped_rule_mp: "#a8874a",
  ind: "#1baf7a",
  coop: "#2a78d6",
  coop_eco05: "#e87ba4",
  coop_eco: "#2e9e2e",
  coop_full: "#eda100",
  coop_ev: "#d96a2b",
  coop_ped: "#8a6fce",
  coop_ev_ped: "#b0477a",
  ind_ev_ped: "#1b9e8a",
  coop_forecast: "#5b8fb9",
  coop_full_ev1: "#c98a00",
  coop_full_ev4: "#f4c455",
  dqn: "#d6337a",
  llm: "#7cbd40",
};

export const METHOD_ORDER = Object.keys(METHOD_LABELS);
export const BASELINES = new Set(["ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp"]);

/** The controllers worth showing on a scenario card; legacy experiments stay behind "more". */
export const PRIMARY_METHODS = new Set([
  "ft",
  "act",
  "mp",
  "ev_rule",
  "ev_rule_mp",
  "ped_rule_mp",
  "coop",
  "coop_full",
  "coop_ev",
  "coop_ped",
  "coop_ev_ped",
  "ind",
  "ind_ev_ped",
  "dqn",
  "llm",
]);

export const methodLabel = (m: string) => METHOD_LABELS[m] ?? m;

/** Human names for the runs registry: what a method *is*, not what it is called in the
 * study's CSVs. The Runs page shows these instead of the raw codes. */
export const MODEL_NAMES: Record<string, string> = {
  ft: "Fixed-time baseline",
  act: "Adaptive-cycle baseline",
  mp: "Max-pressure baseline",
  ev_rule: "Emergency-rule override",
  ev_rule_mp: "Emergency-rule + max-pressure",
  ped_rule_mp: "Pedestrian-rule + max-pressure",
  ind: "Independent RL agent",
  coop: "Cooperative RL agent",
  coop_full: "Cooperative RL agent · full reward",
  coop_ev: "Cooperative RL agent · EV service",
  coop_ped: "Cooperative RL agent · pedestrian service",
  coop_ev_ped: "Cooperative RL agent · EV + pedestrian",
  dqn: "DQN agent",
  llm: "LLM traffic agent",
};
export const modelName = (m: string) => MODEL_NAMES[m] ?? methodLabel(m);
/** Registered model names (rl-shortpilot, generalist-shortpilot, …) are not in the table,
 *  but two policies must never share a grey: pick a stable colour from the name itself. */
const MODEL_FALLBACK = ["#2a78d6", "#eda100", "#d6337a", "#1baf7a", "#7c6cf0"];

function fallbackColor(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) % 9973;
  return MODEL_FALLBACK[hash % MODEL_FALLBACK.length];
}

export const methodColor = (m: string) => METHOD_COLORS[m] ?? fallbackColor(m);
export const isLearned = (m: string) => !BASELINES.has(m);
export const isPrimaryMethod = (m: string) => PRIMARY_METHODS.has(m);

export function sortMethods(methods: Iterable<string>): string[] {
  const rank = (m: string) => {
    const i = METHOD_ORDER.indexOf(m);
    return i === -1 ? METHOD_ORDER.length : i;
  };
  return [...methods].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}
