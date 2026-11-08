import {
  Film,
  Locate,
  MonitorX,
  Play,
  RotateCcw,
  SlidersHorizontal,
  SplitSquareVertical,
  Activity,
  Layers,
  Sparkles,
  BarChart2,
  TrendingUp,
  MapPin,
  Compass,
  ArrowUpRight,
  ArrowDownRight,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import { useState, useMemo, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ReplayControls, ReplayPicker } from "@/features/replay/ReplayControls";
import { ReplayStats } from "@/features/replay/ReplayStats";
import { usePlayback, usePlaybackClock } from "@/features/replay/store";
import { useMeta, useNetwork, useReplay, useComparisons, useSummary } from "@/shared/api/queries";
import {
  useCreateRun,
  useModelCatalog,
  useRuns,
  type ModelCatalogEntry,
} from "@/shared/api/backend";
import { QueryState } from "@/shared/components/QueryState";
import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { NetworkGeometry, Replay, Comparison, SummaryRow } from "@/shared/schemas";
import { Button } from "@/shared/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/shared/ui/card";
import { EmptyState } from "@/shared/ui/empty-state";
import { SelectControl } from "@/shared/ui/select";
import { EChart } from "@/shared/charts/EChart";
import { ChartCard } from "@/shared/charts/ChartCard";
import { forest, heatmap, barsWithCi } from "@/shared/charts/builders";
import type { ChartTokens } from "@/shared/charts/tokens";

import { Scene3D } from "@/features/simulation-3d/Scene3D";
import { Canvas2DSimulation } from "@/features/simulation-3d/Canvas2DSimulation";
import { ALL_VISIBLE, type Visibility } from "@/features/simulation-3d/visibility";

const LEGEND = [
  { key: "car", color: "#38c980" },
  { key: "bus", color: "#f5c451" },
  { key: "emergencyVehicle", color: "#ff4d6d" },
  { key: "incidentVehicle", color: "#d946ef" },
  { key: "pedestrian", color: "#93c5fd" },
] as const;

function kindOf(key: (typeof LEGEND)[number]["key"]): keyof Visibility {
  return key === "emergencyVehicle"
    ? "emergency"
    : key === "incidentVehicle"
    ? "incident"
    : key;
}

/** Every network the backend can record a comparison on (``api/policy.NETWORKS``). */
const COMPARE_NETWORKS = ["sf_mission_2x2", "sf_mission_3x3", "monaco", "tunis"];
const COMPARE_DEMANDS = ["low", "medium", "peak"] as const;

/** The only model types this dashboard offers (same three as Settings → Models). */
const COMPARE_MODEL_TYPES: { id: string; label: string; method: string }[] = [
  { id: "rl", label: "RL", method: "generalist" },
  { id: "hybrid", label: "Hybrid", method: "llm_team" },
  { id: "llm", label: "LLM", method: "llm" },
];

type CompareEvent = "emergency" | "pedestrians" | "incident" | "buses";

/** The event scenarios a comparison can record, not just plain demand. */
import { takeBenchmarkIntent } from "@/shared/benchmark-intent";

const COMPARE_SCENARIOS: { id: string; label: string; events: CompareEvent[] }[] = [
  { id: "normal", label: "Normal traffic", events: [] },
  { id: "emergency", label: "Emergency pre-emption", events: ["emergency"] },
  { id: "pedestrians", label: "Pedestrians", events: ["pedestrians"] },
  { id: "buses", label: "Buses", events: ["buses"] },
  { id: "incident", label: "Incident", events: ["incident"] },
];

/** Registry versions keep their name/version; any other saved weights use their path. */
function modelSpec(model: ModelCatalogEntry): string {
  if (model.modelName && model.version != null) return `model:${model.modelName}@v${model.version}`;
  return `checkpoint:${model.checkpoint}`;
}

/**
 * Free-hand A/B setup: pick any two saved checkpoints (selected runs, raw training
 * runs or registry versions), a network/demand/seed, and record a fresh replay.
 * Nothing here depends on a replay already existing.
 */
function ModelCompareBuilder() {
  const f = useFormat();
  const setReplay = usePlayback((s) => s.setReplay);
  const queryClient = useQueryClient();
  const [network, setNetwork] = useState(COMPARE_NETWORKS[0]);
  const [demand, setDemand] = useState<(typeof COMPARE_DEMANDS)[number]>("peak");
  const [scenario, setScenario] = useState(COMPARE_SCENARIOS[0].id);
  const [seed, setSeed] = useState(3);
  const [left, setLeft] = useState<string | null>(null);
  const [right, setRight] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [openedId, setOpenedId] = useState<string | null>(null);
  // Which controllers can actually run on this network (the policy layer's verdict).
  const [runnable, setRunnable] = useState<Record<string, boolean>>({});

  const catalog = useModelCatalog(network);
  const createRun = useCreateRun();
  // Recording is about the scenario, so the LLM arms answer from the mock backend by
  // default; real provider calls are opt-in because they are slow and rate-limited.
  const [realLlm, setRealLlm] = useState(false);

  const cancelRun = async (runId: string) => {
    await fetch(`/api/runs/${runId}/cancel`, { method: "POST" });
    await runs.refetch();
  };
  const runs = useRuns();
  const models = (catalog.data?.models ?? []).filter((model) => model.available);
  const scenarioEvents = COMPARE_SCENARIOS.find((s) => s.id === scenario)?.events ?? [];

  useEffect(() => {
    let alive = true;
    fetch("/api/policy")
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!alive || !body) return;
        const next: Record<string, boolean> = {};
        for (const entry of body.catalogByNetwork?.[network] ?? []) {
          next[entry.method] = entry.available !== false;
        }
        setRunnable(next);
      })
      .catch(() => {
        if (alive) setRunnable({});
      });
    return () => {
      alive = false;
    };
  }, [network]);

  // The three model types, plus every saved checkpoint as its own comparable entry.
  // A learned type only appears once this network has weights it could load.
  const typeOptions = COMPARE_MODEL_TYPES.filter((type) =>
    type.method === "generalist" ? runnable[type.method] === true : runnable[type.method] !== false,
  ).map((type) => ({ value: type.method, label: `${type.label} · ${type.method}` }));
  const options = [
    ...typeOptions,
    ...models.map((model) => ({
      value: modelSpec(model),
      label: `${model.label} · ${model.agent} · ${model.source}${
        model.timesteps ? ` · ${model.timesteps} steps` : ""
      }`,
    })),
  ];

  // Arriving from Train or Models & Runs: open on the model that was clicked.
  const [wanted, setWanted] = useState<string | null>(null);
  useEffect(() => {
    const intent = takeBenchmarkIntent("compare");
    if (!intent) return;
    if (intent.network && COMPARE_NETWORKS.includes(intent.network)) setNetwork(intent.network);
    if (intent.scenario && COMPARE_SCENARIOS.some((s) => s.id === intent.scenario)) {
      setScenario(intent.scenario);
    }
    if (intent.model) setWanted(intent.model);
  }, []);

  const optionKey = options.map((option) => option.value).join("|");
  useEffect(() => {
    if (!wanted || !optionKey.split("|").includes(wanted)) return;
    // Wait for /api/policy, otherwise a network that does have RL weights would be
    // paired with the hybrid just because the verdict had not arrived yet.
    if (Object.keys(runnable).length === 0) return;
    setLeft(wanted);
    // Give it a sparring partner: trained RL where it exists, otherwise the hybrid.
    setRight((current) => current ?? (runnable.generalist ? "generalist" : "llm_team"));
    setWanted(null);
  }, [wanted, optionKey, runnable]);

  useEffect(() => {
    setLeft(null);
    setRight(null);
  }, [network]);

  const created = runs.data?.find((run) => run.id === createdId);
  useEffect(() => {
    if (created?.status === "done" && created.replayId && openedId !== created.id) {
      setOpenedId(created.id);
      setReplay(created.replayId);
      void queryClient.invalidateQueries({ queryKey: ["data"] });
    }
  }, [created, openedId, setReplay, queryClient]);

  const ready = Boolean(left && right && left !== right);
  const busy =
    createRun.isPending || created?.status === "queued" || created?.status === "running";

  return (
    <Card className="p-4 border border-border bg-surface">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-xs font-medium text-text-2">Network</span>
          <SelectControl
            ariaLabel="Comparison network"
            value={network}
            options={COMPARE_NETWORKS.map((n) => ({ value: n, label: f.networkName(n) }))}
            onChange={setNetwork}
            className="text-sm"
            style={{ minWidth: 170 }}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-xs font-medium text-text-2">Model A</span>
          <SelectControl
            ariaLabel="Model A"
            value={left ?? ""}
            placeholder="Pick a saved model"
            options={options}
            onChange={setLeft}
            disabled={!options.length}
            className="text-sm"
            style={{ minWidth: 260 }}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-xs font-medium text-text-2">Model B</span>
          <SelectControl
            ariaLabel="Model B"
            value={right ?? ""}
            placeholder="Pick a saved model"
            options={options.filter((option) => option.value !== left)}
            onChange={setRight}
            disabled={!options.length}
            className="text-sm"
            style={{ minWidth: 260 }}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-xs font-medium text-text-2">Scenario</span>
          <SelectControl
            ariaLabel="Comparison scenario"
            value={scenario}
            options={COMPARE_SCENARIOS.map((s) => ({ value: s.id, label: s.label }))}
            onChange={setScenario}
            className="text-sm"
            style={{ minWidth: 190 }}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-xs font-medium text-text-2">Demand</span>
          <SelectControl
            ariaLabel="Comparison demand"
            value={demand}
            options={COMPARE_DEMANDS.map((d) => ({ value: d, label: f.demandName(d) }))}
            onChange={(value) => setDemand(value as (typeof COMPARE_DEMANDS)[number])}
            className="text-sm"
            style={{ minWidth: 140 }}
          />
        </div>
        <label className="flex flex-col gap-1 text-xs font-medium text-text-2">
          Seed
          <input
            className="input-control w-20 text-sm"
            type="number"
            min={0}
            max={999}
            value={seed}
            onChange={(event) => setSeed(Number(event.target.value) || 0)}
          />
        </label>
        <label
          className="flex items-center gap-2 pb-2 text-xs text-text-2"
          title="Off: LLM controllers answer from the mock backend. On: every call goes to the configured provider, which is much slower and can be rate-limited."
        >
          <input
            type="checkbox"
            className="check-control"
            checked={realLlm}
            onChange={(event) => setRealLlm(event.target.checked)}
          />
          Real LLM calls
        </label>
        <Button
          disabled={!ready || busy}
          onClick={() => {
            if (!left || !right) return;
            createRun.mutate(
              {
                network,
                demand,
                events: scenarioEvents,
                seed,
                left,
                right,
                llm: realLlm ? "provider" : "mock",
              },
              { onSuccess: (run) => setCreatedId(run.id) },
            );
          }}
        >
          {busy ? "Recording…" : "Record A/B"}
        </Button>
        {busy && createdId ? (
          <button
            type="button"
            onClick={() => void cancelRun(createdId)}
            className="pb-2 text-xs font-semibold text-jam hover:underline"
          >
            Cancel run
          </button>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-muted">
        {options.length
          ? `${options.length} controllers to compare on ${f.networkName(network)} · ${COMPARE_SCENARIOS.find((s) => s.id === scenario)?.label}. Recording writes a new replay and opens it in the player above; LLM controllers answer from the mock backend unless you tick “Real LLM calls”.`
          : `Nothing can run on ${f.networkName(network)} yet: train an RL policy for it, or set the LLM key in Settings → Integrations.`}
      </p>
      {createRun.isError ? (
        <p role="alert" className="mt-1 text-xs text-jam">
          {(createRun.error as Error).message}
        </p>
      ) : null}
      {created?.status === "failed" ? (
        <p role="alert" className="mt-1 text-xs text-jam">
          {created.error ?? "The run failed."}
        </p>
      ) : null}
      {created?.status === "done" ? (
        <p className="mt-1 text-xs text-flow">Replay ready: {created.replayId}</p>
      ) : null}
    </Card>
  );
}

export default function FreshCompare() {
  const { t } = useTranslation();
  usePageTitle("Policy Comparison & Statistical Benchmarks");
  usePlaybackClock();

  const meta = useMeta();
  const replayId = usePlayback((s) => s.replayId);
  const setReplay = usePlayback((s) => s.setReplay);
  const replay = useReplay(replayId);
  const network = useNetwork(replay.data?.network ?? null);
  const comparisons = useComparisons();
  const summary = useSummary();

  const [visible, setVisible] = useState<Visibility>(ALL_VISIBLE);
  const [activeTab, setActiveTab] = useState<"side_by_side" | "deltas">("side_by_side");
  const [renderMode, setRenderMode] = useState<"2d" | "3d">("2d");

  // Keep replay selected automatically if not selected yet
  useEffect(() => {
    if (meta.data?.replays?.length && !replayId) {
      setReplay(meta.data.replays[0].id);
    }
  }, [meta.data, replayId, setReplay]);

  return (
    <div className="flex flex-col gap-6 w-full pb-16 pt-2 px-2 sm:px-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-accent animate-pulse" />
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-text">
              Policy Comparison & Statistical Benchmarks
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-text-2 mt-0.5">
            Evaluate twin simulations side-by-side or inspect statistical forest plots, confidence intervals, and hypothesis tests.
          </p>
        </div>

        {/* View Switchers */}
        <div className="flex flex-wrap items-center gap-3">
          {/* 2D / 3D Toggle (when in side by side) */}
          {activeTab === "side_by_side" && (
            <div className="flex items-center gap-1 p-1 bg-surface-2 border border-border rounded-lg">
              <button
                type="button"
                onClick={() => setRenderMode("2d")}
                className={cn(
                  "px-2.5 py-1 text-xs font-semibold rounded transition-all",
                  renderMode === "2d"
                    ? "bg-accent text-accent-ink shadow-sm"
                    : "text-text-2 hover:text-text"
                )}
              >
                2D Orthographic
              </button>
              <button
                type="button"
                onClick={() => setRenderMode("3d")}
                className={cn(
                  "px-2.5 py-1 text-xs font-semibold rounded transition-all",
                  renderMode === "3d"
                    ? "bg-accent text-accent-ink shadow-sm"
                    : "text-text-2 hover:text-text"
                )}
              >
                3D Perspective
              </button>
            </div>
          )}

          {/* Main Tab Toggle */}
          <div className="flex items-center gap-1.5 p-1 bg-surface-2 border border-border rounded-lg">
            <button
              type="button"
              onClick={() => setActiveTab("side_by_side")}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-semibold transition-all",
                activeTab === "side_by_side"
                  ? "bg-accent text-accent-ink shadow-sm"
                  : "text-text-2 hover:text-text hover:bg-surface-3"
              )}
            >
              <SplitSquareVertical className="w-3.5 h-3.5" />
              <span>Side-by-Side Simulation</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("deltas")}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-semibold transition-all",
                activeTab === "deltas"
                  ? "bg-accent text-accent-ink shadow-sm"
                  : "text-text-2 hover:text-text hover:bg-surface-3"
              )}
            >
              <TrendingUp className="w-3.5 h-3.5" />
              <span>Statistical Deltas & Charts</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {activeTab === "side_by_side" ? (
        <QueryState query={meta} height={80}>
          {(metaData) => {
            if (!metaData.replays.length) {
              // The recorder has to stay reachable: on a network with no replay yet it is
              // the only way to create the first one.
              return (
                <div className="flex flex-col gap-6 w-full">
                  <ModelCompareBuilder />
                  <Card className="p-8 text-center border-dashed border-border flex flex-col items-center justify-center">
                    <Film className="w-10 h-10 text-muted mb-2 opacity-50" />
                    <p className="text-sm font-semibold text-text">No comparative replays yet</p>
                    <p className="text-xs text-muted max-w-lg mt-1">
                      Pick two controllers above and record an A/B run — its replay opens here.
                    </p>
                  </Card>
                </div>
              );
            }

            return (
              <QueryState query={replay} height={300}>
                {(rep) => (
                  <div className="flex flex-col gap-6 w-full">
                    <ModelCompareBuilder />

                    {/* Simulation Controls Toolbar */}
                    <div className="flex flex-wrap items-center justify-between gap-4 p-3.5 rounded-xl border border-border bg-surface shadow-sm">
                      <div className="flex items-center gap-3">
                        <ReplayPicker meta={metaData} />
                      </div>

                      <ReplayControls replay={rep} />

                      {/* Road User Filter Legend */}
                      <div className="flex flex-wrap items-center gap-1.5 text-xs">
                        {LEGEND.map(({ key, color }) => {
                          const kind = kindOf(key);
                          const on = visible[kind];
                          return (
                            <button
                              key={key}
                              type="button"
                              onClick={() => setVisible((v) => ({ ...v, [kind]: !v[kind] }))}
                              className={cn(
                                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all",
                                on
                                  ? "border-border-strong bg-surface text-text shadow-xs"
                                  : "border-border bg-surface-2 text-muted opacity-50"
                              )}
                            >
                              <span
                                className="size-2 rounded-full"
                                style={{ background: on ? color : "transparent", border: `1.5px solid ${color}` }}
                              />
                              <span>{t(`replay.${key}`)}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {/* Side-by-Side Simulation Panels */}
                    <QueryState query={network} height={460}>
                      {(net) => (
                        <div className="flex flex-col gap-6">
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
                            {/* Left Candidate */}
                            <SidePanel
                              net={net}
                              replay={rep}
                              side="left"
                              visible={visible}
                              renderMode={renderMode}
                            />

                            {/* Right Candidate */}
                            <SidePanel
                              net={net}
                              replay={rep}
                              side="right"
                              visible={visible}
                              renderMode={renderMode}
                            />
                          </div>

                          {/* Live Comparative Delta Telemetry */}
                          <Card className="border border-border bg-surface p-4">
                            <div className="flex items-center justify-between border-b border-border/70 pb-3 mb-3">
                              <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-2">
                                <Activity className="w-4 h-4 text-accent" /> Live Comparative Telemetry Delta
                              </span>
                              <span className="text-xs text-muted font-mono">
                                Corridor: {rep.network} · Window: {rep.window}s
                              </span>
                            </div>
                            <ReplayStats replay={rep} sides={["left", "right"]} />
                          </Card>
                        </div>
                      )}
                    </QueryState>
                  </div>
                )}
              </QueryState>
            );
          }}
        </QueryState>
      ) : (
        /* Statistical Analytics & Visual Plots View (Independently rendered) */
        <QueryState query={comparisons} height={400}>
          {(compData) => (
            <QueryState query={summary} height={400}>
              {(summaryData) => (
                <DetailedStatisticalPlots comparisons={compData} summary={summaryData} />
              )}
            </QueryState>
          )}
        </QueryState>
      )}
    </div>
  );
}

function SidePanel({
  net,
  replay,
  side,
  visible,
  renderMode,
}: {
  net: NetworkGeometry;
  replay: Replay;
  side: "left" | "right";
  visible: Visibility;
  renderMode: "2d" | "3d";
}) {
  const f = useFormat();
  const [resetKey, setResetKey] = useState(0);
  const method = replay.sides[side].method;
  const name = replay.sides[side].label ?? f.methodName(method);

  const isLeft = side === "left";
  const badgeColor = isLeft
    ? "border-emerald-500/30 text-emerald-500 bg-emerald-500/10"
    : "border-accent text-accent bg-accent/10";

  return (
    <Card className="overflow-hidden border border-border bg-surface flex flex-col">
      {/* Title Bar */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3 bg-surface-2/40">
        <div className="flex items-center gap-2.5">
          <span
            className="size-3 rounded-full"
            style={{ background: methodColor(method) }}
          />
          <div>
            <h3 className="text-sm font-bold text-text flex items-center gap-2">
              <span>{name}</span>
              <span className={cn("text-[10px] px-2 py-0.5 rounded-full font-mono border", badgeColor)}>
                {isLeft ? "Candidate A" : "Candidate B"}
              </span>
            </h3>
            <span className="text-[10px] font-mono text-muted">
              Policy Method: {method.toUpperCase()}
            </span>
          </div>
        </div>

        {renderMode === "3d" && (
          <Button
            size="sm"
            variant="outline"
            className="text-xs h-7 gap-1 border-border"
            onClick={() => setResetKey((k) => k + 1)}
          >
            <Locate className="w-3.5 h-3.5" />
            <span>Reset Camera</span>
          </Button>
        )}
      </div>

      {/* Render Canvas (2D or 3D) */}
      {renderMode === "2d" ? (
        <Canvas2DSimulation
          net={net}
          replay={replay}
          side={side}
          label={`${isLeft ? "Candidate A" : "Candidate B"} · ${name}`}
        />
      ) : (
        <div className="h-[460px] w-full relative bg-slate-950">
          <Scene3D
            net={net}
            replay={replay}
            sides={[side]}
            resetKey={resetKey}
            visible={visible}
            label={`3D Scene · ${name}`}
          />
        </div>
      )}
    </Card>
  );
}

/** Comprehensive statistical charts and deep empirical benchmarking view */
function DetailedStatisticalPlots({
  comparisons,
  summary,
}: {
  comparisons: Comparison[];
  summary: SummaryRow[];
}) {
  const f = useFormat();

  // Metrics available in comparisons
  const availableMetrics = useMemo(() => {
    return Array.from(new Set(comparisons.map((c) => c.metric)));
  }, [comparisons]);

  const [selectedMetric, setSelectedMetric] = useState(
    availableMetrics.includes("mean_waiting_time")
      ? "mean_waiting_time"
      : availableMetrics[0] ?? "mean_waiting_time"
  );

  const [selectedMethod, setSelectedMethod] = useState("all");

  // Filter and map rows to unified end-to-end models
  const filteredRows = useMemo(() => {
    return comparisons
      .filter((c) => c.metric === selectedMetric)
      .filter((c) => c.method === "llm" || c.method === "coop" || c.method.includes("shortpilot") || c.method.includes("generalist"))
      .map((c) => {
        const isLlm = c.method === "llm";
        return {
          ...c,
          displayCandidate: isLlm ? "Kemetra Full-Stack LLM Agent" : "Kemetra End-to-End Generalist RL",
          displayBaseline: "Traditional Fixed-Time / Sensor Baseline",
        };
      })
      .filter((c) => {
        if (selectedMethod === "all") return true;
        if (selectedMethod === "llm") return c.method === "llm";
        if (selectedMethod === "coop") return c.method !== "llm";
        return true;
      });
  }, [comparisons, selectedMetric, selectedMethod]);

  // Aggregate Key Statistics
  const stats = useMemo(() => {
    if (!filteredRows.length) return null;
    const validDeltas = filteredRows
      .map((r) => r.pairedImprovementPct)
      .filter((v): v is number => v !== null && !isNaN(v));
    const meanDelta = validDeltas.reduce((a, b) => a + b, 0) / (validDeltas.length || 1);
    const sigCount = filteredRows.filter((r) => r.significant).length;
    // The card says Holm-adjusted, so average the adjusted p when the export has it.
    const pValues = filteredRows
      .map((r) => r.pHolm ?? r.pValue)
      .filter((v): v is number => v !== null && !isNaN(v));
    const avgP = pValues.length ? pValues.reduce((a, b) => a + b, 0) / pValues.length : null;
    const bestRow = filteredRows.reduce<(typeof filteredRows)[number] | null>((best, row) => {
      if (row.pairedImprovementPct === null || Number.isNaN(row.pairedImprovementPct)) return best;
      if (!best || (best.pairedImprovementPct ?? -Infinity) < row.pairedImprovementPct) return row;
      return best;
    }, null);

    return {
      meanDelta,
      sigCount,
      totalCount: filteredRows.length,
      deltaCount: validDeltas.length,
      avgP,
      maxGain: validDeltas.length ? Math.max(...validDeltas) : 0,
      minGain: validDeltas.length ? Math.min(...validDeltas) : 0,
      bestRow,
    };
  }, [filteredRows]);

  // Forest Plot Builder: 95% Confidence Intervals
  const buildForestChart = useCallback(
    (tk: ChartTokens) => {
      return forest(tk, {
        items: filteredRows.slice(0, 12).map((r) => ({
          label: `${r.network} · ${r.scenario}`,
          value: r.pairedImprovementPct ?? 0,
          lo: r.pairedCiLo ?? r.pairedImprovementPct ?? 0,
          hi: r.pairedCiHi ?? r.pairedImprovementPct ?? 0,
          color: r.method === "llm" ? "var(--accent)" : "#2a78d6",
          significant: r.significant,
        })),
        xName: `${f.metricName(selectedMetric)} Delta (%)`,
        rtl: false,
        format: (v: number) => f.pct(v),
      });
    },
    [filteredRows, selectedMetric, f]
  );

  // Heatmap Builder: Method vs Scenario gain
  const buildHeatmapChart = useCallback(
    (tk: ChartTokens) => {
      const scenarios = Array.from(new Set(comparisons.map((c) => c.scenario)));
      const methods = ["llm", "coop"];
      const methodLabels = ["Kemetra LLM Agent", "End-to-End Generalist RL"];
      const values: [number, number, number | null][] = [];

      methods.forEach((m, y) => {
        scenarios.forEach((s, x) => {
          const match = comparisons.find(
            (c) => c.method === m && c.scenario === s && c.metric === selectedMetric
          );
          values.push([x, y, match?.pairedImprovementPct ?? null]);
        });
      });

      return heatmap(tk, {
        columns: scenarios,
        rows: methodLabels,
        values,
        format: (v: number) => f.number(v, 1),
        rtl: false,
      });
    },
    [comparisons, selectedMetric, f]
  );

  // Multi-Method Absolute Performance Bars (Summary query)
  const buildSummaryBars = useCallback(
    (tk: ChartTokens) => {
      const metricRows = summary.filter((s) => s.metric === selectedMetric);
      const methods = ["llm", "coop", "ft", "mp"];
      const labels = ["Kemetra LLM", "Generalist RL", "Fixed-Time", "Max-Pressure"];

      const values: (number | null)[] = [];
      const lo: (number | null)[] = [];
      const hi: (number | null)[] = [];
      const colors: string[] = ["var(--accent)", "#2a78d6", "#8f8d88", "#eb6834"];

      methods.forEach((m) => {
        const matching = metricRows.filter((r) => r.method === m);
        if (matching.length) {
          const mean = matching.reduce((acc, curr) => acc + (curr.mean ?? 0), 0) / matching.length;
          const cLo = matching.reduce((acc, curr) => acc + (curr.ciLo ?? 0), 0) / matching.length;
          const cHi = matching.reduce((acc, curr) => acc + (curr.ciHi ?? 0), 0) / matching.length;
          values.push(mean);
          lo.push(cLo);
          hi.push(cHi);
        } else {
          values.push(null);
          lo.push(null);
          hi.push(null);
        }
      });

      return barsWithCi(tk, {
        categories: labels,
        values,
        lo,
        hi,
        colors,
        axisName: f.metricName(selectedMetric),
        format: (v: number) => f.number(v, 1),
        rtl: false,
      });
    },
    [summary, selectedMetric, f]
  );

  return (
    <div className="flex flex-col gap-6 w-full">
      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-3.5 rounded-xl border border-border bg-surface shadow-xs">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-text-2">Target Metric:</span>
            <SelectControl
              ariaLabel="Select metric"
              value={selectedMetric}
              options={availableMetrics.map((m) => ({
                value: m,
                label: f.metricName(m),
              }))}
              onChange={setSelectedMetric}
              className="text-xs font-medium"
              style={{ minWidth: 200 }}
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-text-2">Evaluated Model:</span>
            <SelectControl
              ariaLabel="Select model"
              value={selectedMethod}
              options={[
                { value: "all", label: "All End-to-End Models" },
                { value: "llm", label: "Kemetra Full-Stack LLM Agent" },
                { value: "coop", label: "Kemetra End-to-End Generalist RL" },
              ]}
              onChange={setSelectedMethod}
              className="text-xs font-medium"
              style={{ minWidth: 240 }}
            />
          </div>
        </div>

        <div className="text-xs text-muted">
          Sample size: <strong className="tabular text-text">{filteredRows.length}</strong> pairwise evaluations
        </div>
      </div>

      {/* KPI Delta KPI Highlights */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="p-4 border border-border bg-surface flex flex-col justify-between">
            <span className="text-xs font-semibold text-muted uppercase">Mean Paired Delta</span>
            <div className="flex items-baseline gap-2 my-1">
              <span
                className={cn(
                  "tabular text-2xl font-semibold tracking-tight",
                  stats.meanDelta >= 0 ? "text-flow" : "text-jam"
                )}
              >
                {f.pct(stats.meanDelta)}
              </span>
              <span className="text-[11px] text-text-2">
                vs {f.methodName("ft")} baseline
              </span>
            </div>
            <div className="flex items-center gap-1 text-[11px] text-muted">
              {stats.meanDelta >= 0 ? (
                <ArrowUpRight className="size-3.5 text-flow" />
              ) : (
                <ArrowDownRight className="size-3.5 text-jam" />
              )}
              <span className="tabular">
                Spread: [{f.pct(stats.minGain)}, {f.pct(stats.maxGain)}]
              </span>
            </div>
          </Card>

          <Card className="p-4 border border-border bg-surface flex flex-col justify-between">
            <span className="text-xs font-semibold text-muted uppercase">Statistical Significance</span>
            <div className="flex items-baseline gap-2 my-1">
              <span className="tabular text-2xl font-semibold tracking-tight text-accent">
                {stats.sigCount} / {stats.totalCount}
              </span>
              <span className="text-[11px] text-text-2">
                ({Math.round((stats.sigCount / stats.totalCount) * 100)}% significant)
              </span>
            </div>
            <div className="flex items-center gap-1 text-[11px] text-muted">
              <ShieldCheck className="size-3.5 text-accent" />
              <span>Holm-Bonferroni adjusted (p &lt; 0.05)</span>
            </div>
          </Card>

          <Card className="p-4 border border-border bg-surface flex flex-col justify-between">
            <span className="text-xs font-semibold text-muted uppercase">Mean p-value</span>
            <div className="flex items-baseline gap-2 my-1">
              <span className="tabular text-2xl font-semibold tracking-tight text-text">
                {f.number(stats.avgP, 4)}
              </span>
              <span className="text-[11px] text-text-2">Mann–Whitney U · Holm</span>
            </div>
            <div
              className={cn(
                "flex items-center gap-1 text-[11px]",
                stats.sigCount > 0 ? "text-flow" : "text-muted"
              )}
            >
              <CheckCircle2 className="size-3.5" />
              <span>
                {stats.sigCount > 0
                  ? `${stats.sigCount} of ${stats.totalCount} survive Holm`
                  : "No comparison survives Holm at p < 0.05"}
              </span>
            </div>
          </Card>

          <Card className="p-4 border border-border bg-surface flex flex-col justify-between">
            <span className="text-xs font-semibold text-muted uppercase">Peak Optimization Gain</span>
            <div className="flex items-baseline gap-2 my-1">
              <span
                className={cn(
                  "tabular text-2xl font-semibold tracking-tight",
                  stats.maxGain >= 0 ? "text-flow" : "text-jam"
                )}
              >
                {f.pct(stats.maxGain)}
              </span>
              <span className="text-[11px] text-text-2">maximum delta</span>
            </div>
            <span className="text-[11px] text-muted">
              {stats.bestRow
                ? `Best: ${f.networkName(stats.bestRow.network)} · ${f.scenarioName(stats.bestRow.scenario)}`
                : "No paired delta available"}
            </span>
          </Card>
        </div>
      )}

      {/* Visual Statistical Plots Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        {/* Forest Plot: Confidence Intervals */}
        <ChartCard
          title={`Forest Plot · ${f.metricName(selectedMetric)}`}
          description="95% Paired Confidence Intervals across evaluation network corridors."
        >
          {filteredRows.length > 0 ? (
            <EChart
              build={buildForestChart}
              height={Math.max(280, Math.min(filteredRows.length * 32 + 60, 480))}
              label="Confidence Intervals Forest Plot"
            />
          ) : (
            <div className="h-64 flex items-center justify-center text-xs text-muted">
              No comparisons available for this selection
            </div>
          )}
        </ChartCard>

        {/* Heatmap: Matrix of Performance across scenarios */}
        <ChartCard
          title={`Delta Heatmap · ${f.metricName(selectedMetric)}`}
          description="Comparative percentage improvement across scenarios and controller archetypes."
        >
          <EChart
            build={buildHeatmapChart}
            height={340}
            label="Statistical Gain Heatmap"
          />
        </ChartCard>

        {/* Absolute Performance with Confidence Intervals */}
        <ChartCard
          title={`Absolute Benchmark Mean · ${f.metricName(selectedMetric)}`}
          description="Mean metric values and standard deviation bounds aggregated by control method."
          className="lg:col-span-2"
        >
          <EChart
            build={buildSummaryBars}
            height={320}
            label="Absolute Benchmark Mean Bars"
          />
        </ChartCard>
      </div>

      {/* Comprehensive Raw Benchmark Table */}
      <Card className="border border-border bg-surface p-4">
        <div className="flex items-center justify-between border-b border-border/70 pb-3 mb-3">
          <div>
            <h3 className="text-sm font-bold text-text">Empirical Hypothesis Test Ledger</h3>
            <p className="text-xs text-text-2 mt-0.5">
              Full paired deltas with Cliff's delta effect size and Holm-adjusted significance.
            </p>
          </div>
          <span className="text-xs font-mono text-muted">{filteredRows.length} rows</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="border-b border-border text-muted bg-surface-2/40">
                <th className="py-2.5 px-3 font-semibold">Network Corridor</th>
                <th className="py-2.5 px-3 font-semibold">Scenario</th>
                <th className="py-2.5 px-3 font-semibold">Candidate</th>
                <th className="py-2.5 px-3 font-semibold">Baseline</th>
                <th className="py-2.5 px-3 font-semibold">Improvement %</th>
                <th className="py-2.5 px-3 font-semibold">95% Paired CI</th>
                <th className="py-2.5 px-3 font-semibold">Cliff's Delta</th>
                <th className="py-2.5 px-3 font-semibold">p-value (Holm)</th>
                <th className="py-2.5 px-3 font-semibold text-right">Significance</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((c, i) => (
                <tr key={i} className="border-b border-border/40 hover:bg-surface-2/30 transition-colors">
                  <td className="py-2.5 px-3 tabular text-text-2">{f.networkName(c.network)}</td>
                  <td className="py-2.5 px-3 text-text">{f.scenarioName(c.scenario)}</td>
                  <td className="py-2.5 px-3">
                    <span className="flex items-center gap-1.5">
                      <span
                        className="size-2 rounded-full"
                        style={{ background: c.method === "llm" ? "var(--accent)" : "#2a78d6" }}
                      />
                      <span className="font-medium text-text">
                        {c.displayCandidate || f.methodName(c.method)}
                      </span>
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-muted">
                    {c.displayBaseline || f.methodName(c.reference)}
                  </td>
                  <td
                    className={cn(
                      "py-2.5 px-3 tabular font-semibold",
                      c.pairedImprovementPct === null
                        ? "text-muted"
                        : c.pairedImprovementPct >= 0
                          ? "text-flow"
                          : "text-jam"
                    )}
                  >
                    {f.pct(c.pairedImprovementPct)}
                  </td>
                  <td className="py-2.5 px-3 tabular text-muted">
                    {c.pairedCiLo !== null && c.pairedCiHi !== null
                      ? `[${f.number(c.pairedCiLo, 1)}%, ${f.number(c.pairedCiHi, 1)}%]`
                      : "—"}
                  </td>
                  <td className="py-2.5 px-3 tabular text-muted">
                    {c.cliffsDelta !== null ? f.number(c.cliffsDelta, 3) : "—"}
                    {c.effect ? <span className="text-[10px]"> ({c.effect})</span> : null}
                  </td>
                  <td className="py-2.5 px-3 tabular text-muted">
                    {f.number(c.pHolm ?? c.pValue, 4)}
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    {c.significant ? (
                      <span className="border border-flow/30 bg-flow-soft px-2 py-0.5 text-[10px] font-semibold text-flow">
                        Significant (p &lt; .05)
                      </span>
                    ) : (
                      <span className="border border-border bg-surface-3 px-2 py-0.5 text-[10px] font-semibold text-muted">
                        Not significant
                      </span>
                    )}
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
