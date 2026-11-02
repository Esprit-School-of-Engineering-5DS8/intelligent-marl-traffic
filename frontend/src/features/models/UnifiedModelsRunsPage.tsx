import {
  ChevronRight,
  SlidersHorizontal,
  Trash2,
  X,
  Star,
  Plus,
  Box,
  Layers,
  Check,
  Tag,
  Dna,
  Activity,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/shared/api/backend";
import { useRunsRegistry, useModelsRegistry, useTrainingCandidates } from "@/shared/api/queries";
import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { ModelVersion, type RegistryRun, type RunsRegistry, type ModelsRegistry } from "@/shared/schemas";
import { QueryState, EmptyData } from "@/shared/components/QueryState";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";
import { SelectControl } from "@/shared/ui/select";

const METRIC_COLUMNS: { key: string; label: string }[] = [
  { key: "mean_waiting_time", label: "Mean wait (s)" },
  { key: "throughput_per_h", label: "Throughput / h" },
  { key: "co2_total_kg", label: "CO₂ (kg)" },
  { key: "teleports_total", label: "Teleports" },
  { key: "stops_per_vehicle", label: "Stops / vehicle" },
];

const TRAINING_COLUMNS: { key: string; label: string }[] = [
  { key: "episodeReward", label: "Training reward" },
];

const STATUS_TONE: Record<string, "neutral" | "accent" | "flow" | "jam"> = {
  running: "accent",
  finished: "flow",
  failed: "jam",
  queued: "neutral",
};

export default function UnifiedModelsRunsPage() {
  const [activeTab, setActiveTab] = useState<"models" | "runs">("models");
  const modelsQuery = useModelsRegistry();
  const runsQuery = useRunsRegistry();
  const candidatesQuery = useTrainingCandidates();

  return (
    <div className="flex flex-col gap-6 w-full pb-16 pt-2 px-4">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-text">
            Models & Runs Registry
          </h1>
          <p className="text-xs sm:text-sm text-text-2 mt-0.5">
            Manage versioned model artifacts, promote baselines, and audit historical experiment runs.
          </p>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-surface-2 border border-border rounded-lg self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setActiveTab("models")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              activeTab === "models"
                ? "bg-accent text-accent-ink shadow-sm"
                : "text-text-2 hover:text-text hover:bg-surface-3"
            }`}
          >
            <Box className="w-3.5 h-3.5" />
            <span>Registered Models</span>
            {modelsQuery.data && (
              <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-black/15 font-mono">
                {Object.keys(modelsQuery.data.models).length}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("runs")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              activeTab === "runs"
                ? "bg-accent text-accent-ink shadow-sm"
                : "text-text-2 hover:text-text hover:bg-surface-3"
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Experiment Runs Ledger</span>
            {runsQuery.data && (
              <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-black/15 font-mono">
                {runsQuery.data.runs.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {activeTab === "models" ? (
        <div className="flex flex-col gap-6">
          <QueryState query={modelsQuery} height={400} empty={<NoModels />}>
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

          {/* Register uncommitted candidate checkpoints */}
          <QueryState query={candidatesQuery} height={200}>
            {(data) => <RegisterCandidate candidates={data.candidates} />}
          </QueryState>
        </div>
      ) : (
        <QueryState query={runsQuery} height={420}>
          {(data: RunsRegistry) => <RunsLedgerView registry={data} />}
        </QueryState>
      )}
    </div>
  );
}

// ==========================================
// MODELS VIEW COMPONENTS
// ==========================================

function NoModels() {
  return (
    <EmptyData
      title="No registered models yet"
      text="Train a policy or promote an existing run checkpoint to register a versioned model asset."
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
      api(
        `models/promote-version/${encodeURIComponent(name)}/${version}`,
        z.object({
          model: z.string(),
          version: ModelVersion,
          evaluationJob: z.object({ id: z.string() }),
        }),
        { method: "POST" }
      ),
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
    <Card className="border border-border bg-surface">
      <CardHeader className="border-b border-border/60 pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2.5 text-base font-bold text-text">
            <span>{name}</span>
            <Badge tone="accent">
              {versions.length} version{versions.length > 1 ? "s" : ""}
            </Badge>
          </CardTitle>
          <span className="text-xs text-muted font-mono">
            Latest: v{versions[0]?.version ?? "—"} · run {versions[0]?.runName ?? versions[0]?.runId ?? "—"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-xs">
          <thead>
            <tr className="border-b border-border text-left text-muted bg-surface-2/40">
              <th className="px-4 py-2 font-semibold">Version</th>
              <th className="px-4 py-2 font-semibold">Source Run</th>
              <th className="px-4 py-2 font-semibold">Network</th>
              <th className="px-4 py-2 font-semibold">Artifact / Integrity</th>
              <th className="px-4 py-2 font-semibold">Registered</th>
              <th className="px-4 py-2 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((entry) => (
              <tr key={entry.version} className="border-b border-border/40 hover:bg-surface-2/30 transition-colors">
                <td className="px-4 py-2.5 font-bold text-accent font-mono">v{entry.version}</td>
                <td className="px-4 py-2.5 text-text font-medium">{entry.runName ?? entry.runId}</td>
                <td className="px-4 py-2.5 text-text-2 font-mono">{entry.network ?? "—"}</td>
                <td className="px-4 py-2.5 text-text-2 font-mono">
                  {entry.available === false
                    ? "Unavailable"
                    : `${entry.algorithm ?? "PPO"} · seed ${entry.trainingSeed ?? "—"} · ${
                        entry.bytes ? `${Math.round(entry.bytes / 1024)} KB` : "weights saved"
                      } · SHA ${entry.sha256?.slice(0, 8) ?? "—"}`}
                </td>
                <td className="px-4 py-2.5 text-muted">{entry.createdAt ?? "—"}</td>
                <td className="px-4 py-2.5 text-right">
                  <div className="flex items-center justify-end gap-2">
                    {entry.promoted ? (
                      <Badge tone="flow" className="flex items-center gap-1">
                        <Star className="size-3 fill-current" /> Active Baseline
                      </Badge>
                    ) : null}
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-xs h-7"
                      disabled={promoteVersion.isPending || entry.available === false}
                      onClick={() => promoteVersion.mutate(entry.version)}
                    >
                      {promoteVersion.isPending
                        ? "Evaluating…"
                        : entry.promoted
                        ? "Re-evaluate"
                        : "Set as Active Baseline"}
                    </Button>
                    <button
                      type="button"
                      aria-label={`Delete ${name} v${entry.version}`}
                      className="text-muted hover:text-jam p-1 transition-colors"
                      disabled={deleteVersion.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete ${name} v${entry.version}? This removes the saved checkpoint from the registry.`
                          )
                        )
                          deleteVersion.mutate(entry.version);
                      }}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function RegisterCandidate({ candidates }: { candidates: any[] }) {
  const [targetName, setTargetName] = useState("");
  const queryClient = useQueryClient();

  const register = useMutation({
    mutationFn: (runId: string) =>
      api(
        `models/register/${encodeURIComponent(targetName.trim())}`,
        z.object({ name: z.string(), version: ModelVersion }),
        {
          method: "POST",
          body: JSON.stringify({ runId }),
        }
      ),
    onSuccess: () => {
      setTargetName("");
      void queryClient.invalidateQueries({ queryKey: ["models-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["training-candidates"] });
    },
  });

  if (candidates.length === 0) return null;

  return (
    <Card className="border border-accent/30 bg-surface-2/20">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Plus className="size-4 text-accent" /> Available Training Runs to Register
        </CardTitle>
        <CardDescription className="text-xs">
          Promote any completed run into a versioned model asset.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input-control w-72 text-xs"
            placeholder="Assign model name (e.g. SF-Mission-PPO)..."
            value={targetName}
            onChange={(e) => setTargetName(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          {candidates.map((cand) => (
            <div
              key={cand.id}
              className="flex items-center justify-between p-2.5 rounded-lg border border-border bg-surface text-xs"
            >
              <div className="flex items-center gap-3">
                <span className="font-semibold text-text">{cand.label || cand.id}</span>
                <span className="text-muted font-mono">{cand.network}</span>
                <span className="text-muted">seed {cand.seed}</span>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 text-accent border-accent/40 hover:bg-accent/10"
                disabled={!targetName.trim() || register.isPending}
                onClick={() => register.mutate(cand.id)}
              >
                Register as Model
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ==========================================
// RUNS LEDGER VIEW COMPONENTS
// ==========================================

function RunsLedgerView({ registry }: { registry: RunsRegistry }) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | "training" | "evaluation">("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openRun, setOpenRun] = useState<RegistryRun | null>(null);
  const queryClient = useQueryClient();

  const deleteRun = useMutation({
    mutationFn: async (runId: string) => {
      const response = await fetch(`/api/data/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error((detail as { detail?: string } | null)?.detail ?? `HTTP ${response.status}`);
      }
    },
    onSuccess: () => {
      setOpenRun(null);
      void queryClient.invalidateQueries({ queryKey: ["data", "live", "runs"] });
    },
  });

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 8) next.add(id);
      return next;
    });
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return registry.runs.filter((run) => {
      if (kind === "training" && run.kind !== "training") return false;
      if (kind === "evaluation" && run.kind !== "evaluation") return false;
      if (!q) return true;
      return (
        run.name?.toLowerCase().includes(q) ||
        run.runId.toLowerCase().includes(q) ||
        run.method?.toLowerCase().includes(q)
      );
    });
  }, [registry.runs, query, kind]);

  const activeColumns = kind === "training" ? TRAINING_COLUMNS : METRIC_COLUMNS;

  return (
    <div className="flex flex-col gap-4">
      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg border border-border bg-surface">
        <div className="flex items-center gap-3">
          <input
            className="input-control w-64 text-xs"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search run name, policy, or id…"
          />
          <SelectControl
            ariaLabel="Run type"
            value={kind}
            options={[
              { value: "all", label: "All runs" },
              { value: "training", label: "Training jobs" },
              { value: "evaluation", label: "Evaluation runs" },
            ]}
            onChange={(value) => setKind(value as any)}
            className="text-xs"
            style={{ minWidth: 160 }}
          />
        </div>

        {selected.size > 0 ? (
          <button
            type="button"
            onClick={() => {
              document.querySelector('#benchmarkSubnav [data-benchmark-tab="compare"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            }}
            className="px-3 py-1.5 rounded-md bg-accent text-accent-ink text-xs font-semibold shadow-sm flex items-center gap-1.5"
          >
            Compare {selected.size} runs
          </button>
        ) : (
          <span className="text-xs text-muted flex items-center gap-1.5">
            <SlidersHorizontal className="size-3.5" /> Tick checkboxes to compare runs
          </span>
        )}
      </div>

      {/* Ledger Table */}
      <Card className="border border-border bg-surface overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-xs">
            <thead>
              <tr className="border-b border-border text-left text-muted bg-surface-2/40">
                <th className="w-8 px-3 py-2" />
                <th className="px-3 py-2 font-semibold">Run ID / Name</th>
                <th className="px-3 py-2 font-semibold">Policy</th>
                <th className="px-3 py-2 font-semibold">Network</th>
                <th className="px-3 py-2 font-semibold">Seed</th>
                <th className="px-3 py-2 font-semibold text-right">Episodes</th>
                {activeColumns.map((col) => (
                  <th key={col.key} className="px-3 py-2 text-right font-semibold">
                    {col.label}
                  </th>
                ))}
                <th className="px-3 py-2 font-semibold">Status</th>
                <th className="w-12 px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((run) => (
                <tr
                  key={run.runId}
                  className={`border-b border-border/40 hover:bg-surface-2/30 transition-colors ${
                    selected.has(run.runId) ? "bg-accent/10" : ""
                  }`}
                >
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={selected.has(run.runId)}
                      onChange={() => toggle(run.runId)}
                      className="check-control cursor-pointer"
                    />
                  </td>
                  <td className="px-3 py-2.5 font-medium text-text">
                    <button
                      type="button"
                      onClick={() => setOpenRun(run)}
                      className="text-left hover:text-accent font-semibold transition-colors"
                    >
                      {run.name || run.runId}
                    </button>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-text-2">{run.method}</td>
                  <td className="px-3 py-2.5 font-mono text-muted">{run.network}</td>
                  <td className="px-3 py-2.5 text-muted">{run.seed ?? "—"}</td>
                  <td className="px-3 py-2.5 text-right font-mono">{run.episodes ?? "—"}</td>
                  {activeColumns.map((col) => (
                    <td key={col.key} className="px-3 py-2.5 text-right font-mono text-text">
                      {typeof (run as any)[col.key] === "number"
                        ? (run as any)[col.key].toFixed(2)
                        : "—"}
                    </td>
                  ))}
                  <td className="px-3 py-2.5">
                    <Badge tone={STATUS_TONE[run.status] || "neutral"}>{run.status}</Badge>
                  </td>
                  <td className="px-2 py-2.5 text-right">
                    <button
                      type="button"
                      aria-label="Delete run"
                      onClick={() => {
                        if (window.confirm(`Delete run ${run.name || run.runId}?`)) {
                          deleteRun.mutate(run.runId);
                        }
                      }}
                      className="text-muted hover:text-jam p-1 transition-colors"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

