/** Controller names, order and colours: the same as the report's figures (analysis/style.py). */
export const METHOD_LABELS: Record<string, string> = {
  ft: "FT",
  act: "ACT",
  mp: "MP",
  ev_rule: "EV-RULE",
  ev_rule_mp: "EV-RULE-MP",
  ped_rule_mp: "PED-RULE-MP",
  ind: "IND",
  coop: "COOP",
  coop_eco05: "COOP-ECO (λ=0.5)",
  coop_eco: "COOP-ECO (λ=1.0)",
  coop_full: "COOP-FULL",
  coop_forecast: "COOP + forecast",
  coop_full_ev1: "COOP-FULL (λ_ev=1)",
  coop_full_ev4: "COOP-FULL (λ_ev=4)",
  dqn: "DQN",
  hybrid_h2: "Candidate (H2 β=4)",
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
  coop_forecast: "#5b8fb9",
  coop_full_ev1: "#c98a00",
  coop_full_ev4: "#f4c455",
  dqn: "#d6337a",
  hybrid_h2: "#6250d6",
};

export const METHOD_ORDER = Object.keys(METHOD_LABELS);
export const BASELINES = new Set(["ft", "act", "mp", "ev_rule", "ev_rule_mp", "ped_rule_mp"]);

export const methodLabel = (m: string) => METHOD_LABELS[m] ?? m;
export const methodColor = (m: string) => METHOD_COLORS[m] ?? "#9aa4ae";
export const isLearned = (m: string) => !BASELINES.has(m);

export function sortMethods(methods: Iterable<string>): string[] {
  const rank = (m: string) => {
    const i = METHOD_ORDER.indexOf(m);
    return i === -1 ? METHOD_ORDER.length : i;
  };
  return [...methods].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}
