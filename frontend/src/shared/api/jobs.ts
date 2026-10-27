import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { z } from "zod";

import { useSettings } from "@/features/settings/store";

import { api } from "./backend";

export const JobStatus = z.enum(["queued", "running", "done", "failed", "cancelled"]);

export const JobMetric = z.object({
  step: z.number(),
  reward: z.number().nullable(),
  halting: z.number().nullable(),
  t: z.number(),
  seed: z.number(),
});

export const Job = z.object({
  id: z.string(),
  kind: z.enum(["train", "compare"]),
  request: z.record(z.string(), z.unknown()),
  status: JobStatus,
  createdAt: z.string(),
  startedAt: z.string().nullable(),
  endedAt: z.string().nullable(),
  step: z.number(),
  totalSteps: z.number(),
  stepsPerS: z.number(),
  etaS: z.number(),
  reward: z.number().nullable(),
  meanHalting: z.number().nullable(),
  checkpointPath: z.string().nullable(),
  result: z.unknown().nullable(),
  metricsRing: z.array(JobMetric),
  log: z.array(z.string()),
  error: z.string().nullable(),
});

export type Job = z.infer<typeof Job>;

const ACTIVE: ReadonlySet<Job["status"]> = new Set(["queued", "running"]);
const TERMINAL: ReadonlySet<Job["status"]> = new Set(["done", "failed", "cancelled"]);

export function isActiveJob(job: Job | null | undefined): boolean {
  return Boolean(job && ACTIVE.has(job.status));
}

export function useJobs() {
  const live = useSettings((s) => s.dataSource) === "live";
  return useQuery({
    queryKey: ["jobs"],
    queryFn: () => api("jobs", z.array(Job)),
    enabled: live,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.some((job) => ACTIVE.has(job.status)) ? 2000 : 5000,
  });
}

export type TrainRequest = {
  recipe_id?: string;
  recipe?: Record<string, unknown>;
  network: string;
  seeds: number[];
  timesteps: number;
};

export function useStartTraining() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (request: TrainRequest) =>
      api("train", Job, { method: "POST", body: JSON.stringify(request) }),
    onSuccess: (job) => {
      client.setQueryData<Job[]>(["jobs"], (current) => [
        job,
        ...(current ?? []).filter((item) => item.id !== job.id),
      ]);
    },
  });
}

export type CompareRequest = {
  network: string;
  scenario?: string;
  demand?: string;
  seed?: number;
  seeds?: number[];
  methods: string[];
  quick?: boolean;
  overrides?: Record<string, Record<string, unknown>>;
};

export function useStartCompare() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (request: CompareRequest) =>
      api("compare", Job, { method: "POST", body: JSON.stringify(request) }),
    onSuccess: (job) => {
      client.setQueryData<Job[]>(["jobs"], (current) => [
        job,
        ...(current ?? []).filter((item) => item.id !== job.id),
      ]);
    },
  });
}

export function useDeleteJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      api(`jobs/${jobId}`, z.object({ ok: z.boolean(), jobId: z.string() }), {
        method: "DELETE",
      }),
    onSuccess: (_data, jobId) => {
      client.setQueryData<Job[]>(["jobs"], (current) =>
        current ? current.filter((item) => item.id !== jobId) : current,
      );
    },
  });
}

export function useCancelJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      api(`jobs/${jobId}/cancel`, z.object({ ok: z.boolean(), jobId: z.string() }), {
        method: "POST",
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

/** Stream one job's progress; the list query stays the source for recent jobs. */
export function useJobStream(jobId: string | null) {
  const client = useQueryClient();
  useEffect(() => {
    if (!jobId || typeof EventSource === "undefined") return;
    const source = new EventSource(`/api/jobs/${jobId}/events`);

    source.onmessage = (event) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      const parsed = Job.safeParse(payload);
      if (!parsed.success) return;
      const job = parsed.data;
      client.setQueryData<Job[]>(["jobs"], (current) => {
        if (!current) return [job];
        return current.some((item) => item.id === job.id)
          ? current.map((item) => (item.id === job.id ? job : item))
          : [job, ...current];
      });
      if (TERMINAL.has(job.status)) source.close();
    };

    return () => source.close();
  }, [client, jobId]);
}
