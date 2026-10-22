import { z } from "zod";

import type { Settings } from "./store";

export const SettingsSchema = z.object({
  theme: z.enum(["dark", "light", "system"]),
  language: z.enum(["fr", "en", "ar"]),
  timeUnit: z.enum(["s", "min"]),
  speedUnit: z.enum(["kmh", "ms"]),
  dataSource: z.enum(["mock", "live"]),
  llmProvider: z.enum(["ollama", "claude", "openai"]),
}) satisfies z.ZodType<Settings>;
