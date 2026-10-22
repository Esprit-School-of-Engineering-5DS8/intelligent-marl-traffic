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

export interface Settings {
  theme: ThemeChoice;
  language: Language;
  timeUnit: TimeUnit;
  speedUnit: SpeedUnit;
  dataSource: DataSource;
  llmProvider: LlmProvider;
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
};

export const useSettings = create<SettingsStore>()(
  persist(
    (set) => ({
      ...DEFAULT_SETTINGS,
      update: (patch) => set(patch),
      reset: () => set(DEFAULT_SETTINGS),
    }),
    {
      name: "cotraffic-settings",
      version: 2,
      storage: createJSONStorage(() => safeStorage),
    },
  ),
);
