import { useQuery } from "@tanstack/react-query";
import type { ZodType } from "zod";

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
  Summary,
  TimeseriesCell,
  Training,
  type Cell,
} from "@/shared/schemas";

import { fetchData } from "./source";

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
