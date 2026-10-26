import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { env } from "@/shared/lib/env";
import { safeStorage } from "@/shared/lib/storage";

export type ThemeChoice = "dark" | "light" | "system";
export type Language = "fr" | "en" | "ar";
export type TimeUnit = "s" | "min";
export type SpeedUnit = "kmh" | "ms";
export type DataSource = "mock" | "live";
/** The model answering in the assistant; the backend holds any key, never the browser. */
export type LlmProvider = "ollama" | "claude" | "openai";
/**
 * Which controller the live simulation runs: a scripted baseline, a trained policy, or the
 * language-model controller. Sent to the backend as PUT /api/policy.
 */
export type ControlMode = "baseline" | "learned" | "llm";

/** Baseline `method` names accepted by the controller registry. */
export const BASELINE_METHODS = ["mp", "ft", "act", "ev_rule_mp", "ped_rule_mp"] as const;
/** Learned `method` names that need a trained checkpoint. */
export const LEARNED_METHODS = [
  "coop",
  "ind",
  "coop_full",
  "coop_eco",
  "coop_eco05",
  "dqn",
] as const;

/** The `method` string a settings combination means on the backend. */
export function controlMethod(settings: Settings): string {
  if (settings.controlMode === "llm") return "llm";
  if (settings.controlMode === "learned") return settings.learnedMethod;
  return settings.baselineMethod;
}

export interface Settings {
  theme: ThemeChoice;
  language: Language;
  timeUnit: TimeUnit;
  speedUnit: SpeedUnit;
  dataSource: DataSource;
  llmProvider: LlmProvider;
  controlMode: ControlMode;
  baselineMethod: string;
  learnedMethod: string;
}

interface SettingsStore extends Settings {
  update: (patch: Partial<Settings>) => void;
  reset: () => void;
}

export const DEFAULT_SETTINGS: Settings = {
  theme: "dark",
  language: "fr",
  timeUnit: "s",
  speedUnit: "kmh",
  dataSource: env.VITE_DATA_SOURCE,
  llmProvider: "ollama",
  controlMode: "baseline",
  baselineMethod: "mp",
  learnedMethod: "coop",
};

export const useSettings = create<SettingsStore>()(
  persist(
    (set) => ({
      ...DEFAULT_SETTINGS,
      update: (patch) => set(patch),
      reset: () => set(DEFAULT_SETTINGS),
    }),
    {
      // Keep the key stable so existing preferences survive; new fields fall back to
      // DEFAULT_SETTINGS because persist merges the stored object over the defaults.
      name: "cotraffic-settings",
      version: 3,
      migrate: (persisted) => persisted as Settings,
      storage: createJSONStorage(() => safeStorage),
    },
  ),
);
