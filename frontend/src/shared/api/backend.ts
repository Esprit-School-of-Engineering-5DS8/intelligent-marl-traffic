import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { useSettings } from "@/features/settings/store";
import { Run, type ScenarioRequest } from "@/shared/schemas";

import { DataError } from "./source";

/** Calls to the FastAPI backend (live source only). No key or secret ever lives here. */
async function api<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
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
