import { Check, Plus, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/shared/api/backend";
import { useModelsRegistry, useTrainingCandidates } from "@/shared/api/queries";
import { ModelVersion, type ModelsRegistry } from "@/shared/schemas";
import { QueryState, EmptyData } from "@/shared/components/QueryState";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

/** Model registry page: named models, their versions, the runs they came from. */
export default function ModelsPage() {
  const registry = useModelsRegistry();
  const candidates = useTrainingCandidates();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Models"
        description="Reusable, checksum-verified snapshots of trained policies. Register trained runs here, then benchmark exact saved versions under shared conditions."
      />
      <QueryState query={registry} height={480} empty={<NoModels />}>
        {(data: ModelsRegistry) => {
          const names = Object.keys(data.models).sort();
          if (names.length === 0) return <NoModels />;
          return (
            <div className="flex flex-col gap-4">
              {names.map((name) => (
                <ModelCard key={name} name={name} versions={[...data.models[name]].reverse()} />
              ))}
            </div>
          );
        }}
      </QueryState>
      <QueryState query={candidates} height={240}>
        {(data) => <RegisterCandidate candidates={data.candidates} />}
      </QueryState>
    </div>
  );
}

function NoModels() {
  return (
    <EmptyData
      title="No models registered yet"
      text="Choose a completed training run below to save its exact checkpoint as a reusable model version."
    />
  );
}

interface ModelRow {
  version: number;
  runId: string;
  runName?: string;
  network?: string | null;
  checkpoint?: unknown;
  promoted?: boolean;
  createdAt?: string;
  sha256?: string;
  bytes?: number;
  trainingSeed?: number | null;
  available?: boolean;
  algorithm?: string;
}

function ModelCard({ name, versions }: { name: string; versions: ModelRow[] }) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["models-registry"] });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  };
  const promoteVersion = useMutation({
    mutationFn: (version: number) =>
      api(`models/promote-version/${encodeURIComponent(name)}/${version}`, z.object({ model: z.string(), version: ModelVersion, evaluationJob: z.object({ id: z.string() }) }), {
        method: "POST",
      }),
    onSuccess: invalidate,
  });
  const deleteVersion = useMutation({
    mutationFn: async (version: number) => {
      const response = await fetch(`/api/models/${encodeURIComponent(name)}/${version}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error((detail as { detail?: string } | null)?.detail ?? `HTTP ${response.status}`);
      }
    },
    onSuccess: invalidate,
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {name}
          <Badge tone="accent">
            {versions.length} version{versions.length > 1 ? "s" : ""}
          </Badge>
        </CardTitle>
        <CardDescription>
          Latest: v{versions[0]?.version ?? "—"} · run {versions[0]?.runName ?? versions[0]?.runId ?? "—"}
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted">
              <th className="px-4 py-2">Version</th>
              <th className="px-4 py-2">Source run</th>
              <th className="px-4 py-2">Network</th>
              <th className="px-4 py-2">Artifact / integrity</th>
              <th className="px-4 py-2">Created</th>
              <th className="px-4 py-2 text-right">Baseline</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((entry) => (
              <tr key={entry.version} className="border-b border-border/60">
                <td className="px-4 py-2 font-medium text-text">v{entry.version}</td>
                <td className="px-4 py-2 text-text-2">{entry.runName ?? entry.runId}</td>
                <td className="px-4 py-2 text-text-2">{entry.network ?? "—"}</td>
                <td className="px-4 py-2 text-xs text-text-2">{entry.available === false ? "Unavailable" : `${entry.algorithm ?? "policy"} · seed ${entry.trainingSeed ?? "—"} · ${entry.bytes ? `${Math.round(entry.bytes / 1024)} KB` : "weights saved"} · SHA ${entry.sha256?.slice(0, 10) ?? "—"}`}</td>
                <td className="px-4 py-2 text-text-2">{entry.createdAt ?? "—"}</td>
                <td className="px-4 py-2 text-right">
                  <div className="flex items-center justify-end gap-2">
                    {entry.promoted ? <Badge tone="flow"><Star className="size-3" /> baseline</Badge> : null}
                    <Button size="sm" variant="ghost" disabled={promoteVersion.isPending || entry.available === false} onClick={() => promoteVersion.mutate(entry.version)}>
                      {promoteVersion.isPending ? "Evaluating…" : entry.promoted ? "Evaluate baseline" : "Set baseline + evaluate"}
                    </Button>
                    <button
                      type="button"
                      aria-label={`Delete ${name} v${entry.version}`}
                      className="text-muted hover:text-jam"
                      disabled={deleteVersion.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete ${name} v${entry.version}? This removes the saved copy of the weights from the registry.`,
                          )
                        )
                          deleteVersion.mutate(entry.version);
                      }}
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {promoteVersion.isError ? <p role="alert" className="px-4 py-2 text-xs text-jam">{promoteVersion.error instanceof Error ? promoteVersion.error.message : "Promotion evaluation could not be started."}</p> : null}
        {promoteVersion.isSuccess ? <p role="status" className="px-4 py-2 text-xs text-flow">Baseline set; evaluation job {promoteVersion.data.evaluationJob.id} queued.</p> : null}
        {deleteVersion.isError ? <p role="alert" className="px-4 py-2 text-xs text-jam">{deleteVersion.error instanceof Error ? deleteVersion.error.message : "Could not delete the model version."}</p> : null}
      </CardContent>
    </Card>
  );
}

function RegisterCandidate({ candidates }: { candidates: { id: string; agent: string; label: string; network: string; seed: number; timesteps: number; bytes: number; sha256: string }[] }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const register = useMutation({
    mutationFn: async ({ candidate_id, name }: { candidate_id: string; name: string }) =>
      api<{ model: string; version: ModelVersion }>("models/register-candidate", z.object({ model: z.string(), version: ModelVersion }), {
        method: "POST", body: JSON.stringify({ candidate_id, name }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["models-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["training-candidates"] });
    },
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm"><Plus className="size-4" />Completed training checkpoints</CardTitle>
        <CardDescription className="text-xs">Pick the two existing 4,096-step policies to register exact, verified weight copies. Each remains a single shared policy across the intersections.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!candidates.length ? <p className="text-sm text-muted">No completed checkpoint candidates found.</p> : candidates.map((candidate) => {
          const checked = selected.includes(candidate.id);
          return <div key={candidate.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border p-3">
            <button type="button" aria-pressed={checked} onClick={() => setSelected((current) => checked ? current.filter((id) => id !== candidate.id) : [...current, candidate.id])} className={`flex size-6 items-center justify-center rounded border ${checked ? "border-flow bg-flow text-white" : "border-border"}`}>{checked ? <Check className="size-4" /> : null}</button>
            <div className="min-w-48 flex-1"><div className="text-sm font-medium">{candidate.label}</div><div className="text-xs text-muted">{candidate.network} · training seed {candidate.seed} · {candidate.timesteps.toLocaleString()} steps · {Math.round(candidate.bytes / 1024)} KB · SHA {candidate.sha256.slice(0, 10)}</div></div>
            <input className="input-control text-sm" aria-label={`Model name for ${candidate.label}`} placeholder={candidate.agent} value={names[candidate.id] ?? candidate.agent} onChange={(event) => setNames((current) => ({ ...current, [candidate.id]: event.target.value }))} />
            <Button size="sm" disabled={register.isPending || !checked || !(names[candidate.id] ?? candidate.agent).trim()} onClick={() => register.mutate({ candidate_id: candidate.id, name: (names[candidate.id] ?? candidate.agent).trim() })}>{register.isPending ? "Saving…" : "Save model"}</Button>
          </div>;
        })}
        {register.isError ? <p role="alert" className="text-xs text-jam">{register.error instanceof Error ? register.error.message : "Could not save the model."}</p> : null}
        {register.isSuccess ? <p className="text-xs text-flow">Saved {register.data.model} v{register.data.version.version}.</p> : null}
      </CardContent>
    </Card>
  );
}
