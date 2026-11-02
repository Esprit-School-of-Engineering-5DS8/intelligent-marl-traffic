/** Controller names, order and colours: the same as the report's figures (analysis/style.py). */
export const METHOD_LABELS: Record<string, string> = {
  hybrid_h2: "Candidate (H2 β=4)",
  ft: "FT",
  act: "ACT",
  mp: "MP",
  ev_rule: "EV-RULE",
  ev_rule_mp: "EV-RULE-MP",
  ped_rule_mp: "PED-RULE-MP",
  team_rules: "TEAM-RULES",
  ind: "IND",
  coop: "COOP",
  coop_eco05: "COOP-ECO (λ=0.5)",
  coop_eco: "COOP-ECO (λ=1.0)",
  coop_full: "COOP-FULL",
  coop_forecast: "COOP + forecast",
  coop_full_ev1: "COOP-FULL (λ_ev=1)",
  coop_full_ev4: "COOP-FULL (λ_ev=4)",
  dqn: "DQN",
  hybrid_h1: "H1 (q90)",
  hybrid_h3: "H3 (q90)",
  coop_full_evrule_switch: "V1 : COOP-FULL + EV-RULE",
  coop_full_pedrule_switch: "COOP-FULL + EV-RULE + PED-RULE",
  coop_full_teamped_switch: "COOP-FULL + EV-RULE + règles piétons du coéquipier",
  hybrid_h2_llm: "Candidate + LLM conseiller",
  hybrid_h2_llmstrat: "Candidate + LLM stratège",
  oracle: "Oracle",
  placebo: "Placebo",
};

/**
 * The controllers of the final study have one fixed colour each, defined per theme in
 * theme/index.css (validated: colour-blind separation and contrast, light and dark). The
 * oracle is a ceiling, not a controller: a neutral dashed line, never a colour of its own.
 */
const FIXED: Record<string, string> = {
  hybrid_h2: "--ctl-candidate",
  mp: "--ctl-mp",
  coop_full: "--ctl-coop-full",
  ev_rule_mp: "--ctl-ev-rule-mp",
  team_rules: "--ctl-team",
  hybrid_h2_llm: "--ctl-llm",
  hybrid_h2_llmstrat: "--ctl-llm",
  ft: "--ctl-neutral",
  placebo: "--ctl-placebo",
  oracle: "--ctl-oracle",
};

/** Light-theme values of the fixed colours: used where no stylesheet is loaded (tests). */
const FIXED_FALLBACK: Record<string, string> = {
  "--ctl-candidate": "#2a78d6",
  "--ctl-mp": "#eb6834",
  "--ctl-coop-full": "#1baf7a",
  "--ctl-ev-rule-mp": "#eda100",
  "--ctl-team": "#e87ba4",
  "--ctl-llm": "#4a3aa7",
  "--ctl-neutral": "#8f8d88",
  "--ctl-placebo": "#b8b6b0",
  "--ctl-oracle": "#52514e",
};

/** Colours of the exploration pages' other controllers (never next to the candidate). */
const OTHER_COLORS: Record<string, string> = {
  act: "#7c6cf0",
  ev_rule: "#e34948",
  ped_rule_mp: "#a8874a",
  ind: "#7a5c3e",
  coop: "#5b8fb9",
  coop_eco05: "#b07aa1",
  coop_eco: "#2e9e2e",
  coop_forecast: "#7f8fa6",
  coop_full_ev1: "#14866a",
  coop_full_ev4: "#5fc7a2",
  dqn: "#d6337a",
  hybrid_h1: "#7f8fa6",
  hybrid_h3: "#256abf",
  coop_full_evrule_switch: "#8c6d5a",
  coop_full_pedrule_switch: "#a8874a",
  coop_full_teamped_switch: "#b07aa1",
};

export const METHOD_ORDER = Object.keys(METHOD_LABELS);
export const BASELINES = new Set([
  "ft",
  "act",
  "mp",
  "ev_rule",
  "ev_rule_mp",
  "ped_rule_mp",
  "team_rules",
]);

export const methodLabel = (m: string) => METHOD_LABELS[m] ?? m;
export const isLearned = (m: string) => !BASELINES.has(m);
/** Whether a controller has a fixed colour token (the final study's controllers). */
export const hasFixedColor = (m: string) => m in FIXED;

/** The colour of a controller in the current theme (hex, for charts and swatches). */
export function methodColor(m: string): string {
  const token = FIXED[m];
  if (!token) return OTHER_COLORS[m] ?? "#9aa4ae";
  const value =
    typeof document === "undefined"
      ? ""
      : getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  return value || FIXED_FALLBACK[token]!;
}

/** The colour as a CSS value that follows the theme by itself (for DOM swatches). */
export function methodColorVar(m: string): string {
  const token = FIXED[m];
  return token ? `var(${token}, ${FIXED_FALLBACK[token]})` : (OTHER_COLORS[m] ?? "#9aa4ae");
}

export function sortMethods(methods: Iterable<string>): string[] {
  const rank = (m: string) => {
    const i = METHOD_ORDER.indexOf(m);
    return i === -1 ? METHOD_ORDER.length : i;
  };
  return [...methods].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}
