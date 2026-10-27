import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { useSettings } from "@/features/settings/store";
import { Run, type ScenarioRequest } from "@/shared/schemas";

import { DataError } from "./source";

/** Calls to the FastAPI backend (live source only). No key or secret ever lives here. */
export async function api<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new DataError("backend unreachable");
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new DataError(
      (detail as { detail?: string } | null)?.detail ?? `HTTP ${response.status}`,
      response.status,
    );
  }
  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) throw new DataError(`${path}: unexpected response`);
  return parsed.data;
}

const Bounds = z.object({
  west: z.number(),
  south: z.number(),
  east: z.number(),
  north: z.number(),
});

export const CatalogController = z.object({
  method: z.string(),
  label: z.string(),
  learned: z.boolean(),
  trained: z.boolean(),
  available: z.boolean(),
  reason: z.string().nullable(),
  checkpointPath: z.string().nullable(),
});

export const CatalogNetwork = z.object({
  network: z.string(),
  title: z.string(),
  description: z.string(),
  tlsCount: z.number(),
  edgeCount: z.number(),
  junctionCount: z.number(),
  bounds: Bounds,
  geoBounds: Bounds,
  measuredWallTimeS: z.number(),
  runnable: z.boolean(),
  disabledReason: z.string().nullable(),
  controllers: z.record(z.string(), CatalogController),
});

export const CatalogAgent = z.object({
  name: z.string(),
  label: z.string(),
  family: z
    .enum(["rl", "llm", "legacy"])
    .optional()
    .nullable()
    .transform((value) => value ?? "legacy"),
  algorithm: z.string(),
  note: z.string(),
  source: z.string(),
  hash: z.string(),
  overlays: z
    .array(z.string())
    .nullish()
    .transform((value) => value ?? []),
  trainable: z.boolean(),
  error: z.string().nullable().optional(),
});

export const Catalog = z.object({
  networks: z.array(CatalogNetwork),
  agentConfigs: z.array(CatalogAgent),
  controllers: z.array(
    z.object({
      method: z.string(),
      label: z.string(),
      learned: z.boolean(),
    }),
  ),
});

export type CatalogNetwork = z.infer<typeof CatalogNetwork>;
export type CatalogController = z.infer<typeof CatalogController>;

export function useCatalog() {
  const live = useSettings((s) => s.dataSource) === "live";
  return useQuery({
    queryKey: ["catalog"],
    queryFn: () => api("catalog", Catalog),
    enabled: live,
    staleTime: 60_000,
    retry: false,
  });
}

const LlmProvider = z.object({
  id: z.string(),
  label: z.string(),
  available: z.boolean(),
  models: z.array(
    z.object({
      id: z.string(),
      context_window: z.number().nullish().transform((value) => value ?? 0),
    }),
  ).nullish().transform((value) => value ?? []),
});

const ProvidersResponse = z.object({ providers: z.array(LlmProvider) });

export type LlmProviderList = z.infer<typeof ProvidersResponse>;

export function useLlmProviders() {
  const live = useSettings((s) => s.dataSource) === "live";
  return useQuery({
    queryKey: ["llm-providers"],
    queryFn: () => api("llm/providers", ProvidersResponse),
    enabled: live,
    staleTime: 60_000,
    retry: false,
  });
}

const RecipeResponse = z.object({
  id: z.string(),
  hash: z.string(),
  config: z.record(z.string(), z.unknown()),
});

export type RecipeResponse = z.infer<typeof RecipeResponse>;

export function useRecipe(recipeId: string) {
  const live = useSettings((s) => s.dataSource) === "live";
  return useQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => api(`recipes/${recipeId}`, RecipeResponse),
    enabled: live && Boolean(recipeId),
    staleTime: 60_000,
    retry: false,
  });
}

export function useRuns() {
  const live = useSettings((s) => s.dataSource) === "live";
  return useQuery({
    queryKey: ["runs"],
    queryFn: () => api("runs", z.array(Run)),
    enabled: live,
    // follow the simulations while some are still running
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "queued" || r.status === "running") ? 3000 : false,
  });
}

export function useCreateRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (request: ScenarioRequest) =>
      api("runs", Run, { method: "POST", body: JSON.stringify(request) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export const LlmStatus = z.object({
  available: z.boolean(),
  provider: z.string(),
  model: z.string().nullable(),
});

export function useLlmStatus() {
  const live = useSettings((s) => s.dataSource) === "live";
  const provider = useSettings((s) => s.llmProvider);
  return useQuery({
    queryKey: ["llm-status", provider],
    queryFn: () => api(`assistant/status?provider=${provider}`, LlmStatus),
    enabled: live,
    staleTime: 30_000,
    retry: false,
  });
}
