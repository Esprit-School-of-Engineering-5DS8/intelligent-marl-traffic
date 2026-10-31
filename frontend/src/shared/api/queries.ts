import { useQuery } from "@tanstack/react-query";
import { z, type ZodType } from "zod";

import { useSettings } from "@/features/settings/store";
import { cellKey } from "@/shared/domain/cells";
import {
  Comparisons,
  Decisions,
  DistributionCell,
  EmergencyLog,
  Meta,
  NetworkGeometry,
  PedestrianGreens,
  Replay,
  RunsRegistry,
  Summary,
  TimeseriesCell,
  Training,
  ModelsRegistry,
  type Cell,
} from "@/shared/schemas";

import { fetchData } from "./source";

export const useRunsRegistry = () => useQuery({
  queryKey: ["data", "live", "runs"],
  queryFn: () => fetchData("live", "runs", RunsRegistry),
  staleTime: 0,
  refetchInterval: 5000,
  retry: false,
});
export const useModelsRegistry = () => useQuery({
  queryKey: ["models-registry"],
  queryFn: () => fetch("/api/models").then(async (response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const parsed = ModelsRegistry.safeParse(await response.json());
    if (!parsed.success) throw new Error("models: invalid registry response");
    return parsed.data;
  }),
  refetchInterval: 5000,
  staleTime: 0,
  retry: false,
});

export const useTrainingCandidates = () => useQuery({
  queryKey: ["training-candidates"],
  queryFn: async () => {
    const response = await fetch("/api/models/candidates");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return z.object({ candidates: z.array(z.object({ id: z.string(), agent: z.string(), label: z.string(), network: z.string(), seed: z.number(), timesteps: z.number(), checkpoint: z.string(), sha256: z.string(), bytes: z.number(), recipeHash: z.string(), algorithm: z.string(), recipe: z.record(z.string(), z.unknown()) })) }).parse(await response.json());
  },
  retry: false,
});

function useData<T>(path: string | null, schema: ZodType<T>, optional = false) {
  const source = useSettings((s) => s.dataSource);
  return useQuery({
    queryKey: ["data", source, path],
    queryFn: ({ signal }) => fetchData(source, path ?? "", schema, { signal, optional }),
    enabled: path !== null,
    // exported files only change when the export runs again
    staleTime: source === "mock" ? Infinity : 60_000,
  });
}

export const useMeta = () => useData("meta", Meta);
export const useSummary = () => useData("summary", Summary);
export const useComparisons = () => useData("comparisons", Comparisons);
export const usePedestrianGreens = () => useData("pedestrian_greens", PedestrianGreens, true);
export const useEmergencyLog = () => useData("emergency_log", EmergencyLog, true);

export const useTimeseries = (cell: Cell | null) =>
  useData(cell ? `timeseries/${cellKey(cell)}` : null, TimeseriesCell, true);
export const useDistribution = (cell: Cell | null) =>
  useData(cell ? `distributions/${cellKey(cell)}` : null, DistributionCell, true);
export const useTraining = (agent: string | null, network: string | null) =>
  useData(agent && network ? `training/${agent}__${network}` : null, Training, true);
export const useDecisions = (runId: string | null) =>
  useData(runId ? `decisions/${runId}` : null, Decisions, true);
export const useNetwork = (network: string | null) =>
  useData(network ? `networks/${network}` : null, NetworkGeometry, true);
export const useReplay = (id: string | null) => useData(id ? `replays/${id}` : null, Replay, true);
