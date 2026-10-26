import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { useSettings } from "@/features/settings/store";

import { api } from "./backend";

/** One controller the backend can run, as the policy catalog reports it. */
export const PolicyMethod = z.object({
  method: z.string(),
  label: z.string(),
  learned: z.boolean(),
  checkpoint: z.string().nullable(),
});

/** The active control policy plus what the settings screen needs to render it. */
export const Policy = z.object({
  method: z.string(),
  network: z.string(),
  label: z.string(),
  checkpoint: z.string().nullable(),
  available: z.boolean(),
  degraded: z.boolean().optional(),
  reason: z.string().nullable(),
  catalog: z.array(PolicyMethod),
  networks: z.array(z.string()),
});

export type Policy = z.infer<typeof Policy>;
export type PolicyMethod = z.infer<typeof PolicyMethod>;

export function usePolicy() {
  const live = useSettings((s) => s.dataSource) === "live";
  return useQuery({
    queryKey: ["policy"],
    queryFn: () => api("policy", Policy),
    enabled: live,
    staleTime: 15_000,
    retry: false,
  });
}

export function useUpdatePolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ method, network }: { method: string; network?: string }) =>
      api("policy", Policy, { method: "PUT", body: JSON.stringify({ method, network }) }),
    onSuccess: (data) => {
      client.setQueryData(["policy"], data);
    },
  });
}
