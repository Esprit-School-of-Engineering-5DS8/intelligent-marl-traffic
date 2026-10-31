import { ChevronRight, SlidersHorizontal, Trash2, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/shared/api/backend";
import { useRunsRegistry } from "@/shared/api/queries";
import { forest, heatmap } from "@/shared/charts/builders";
import { ChartCard } from "@/shared/charts/ChartCard";
import { EChart } from "@/shared/charts/EChart";
import type { ChartTokens } from "@/shared/charts/tokens";
import { useFormat } from "@/shared/domain/format";
import { gainPct } from "@/shared/domain/metrics";
import { methodColor } from "@/shared/domain/methods";
import { ModelVersion, type RegistryRun, type RunsRegistry } from "@/shared/schemas";
import { QueryState, EmptyData } from "@/shared/components/QueryState";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";
import { SelectControl } from "@/shared/ui/select";

/* The registry's flat metric columns (runs.json "columns"), the MLflow-style table. */
const METRIC_COLUMNS: { key: string; label: string }[] = [
  { key: "mean_waiting_time", label: "Mean wait (s)" },
  { key: "throughput_per_h", label: "Throughput / h" },
  { key: "co2_total_kg", label: "CO₂ (kg)" },
  { key: "teleports_total", label: "Teleports" },
  { key: "stops_per_vehicle", label: "Stops / vehicle" },
];

/* A training run has no evaluation metrics yet: show what it does have, not five dashes. */
const TRAINING_COLUMNS: { key: string; label: string }[] = [
  { key: "episodeReward", label: "Training reward" },
];

const STATUS_TONE: Record<string, "neutral" | "accent" | "flow" | "jam"> = {
  running: "accent",
  finished: "flow",
  failed: "jam",
  queued: "neutral",
};

const VIEWS = ["all", "training", "evaluation"] as const;
const VIEW_LABEL: Record<(typeof VIEWS)[number], string> = {
  all: "All runs",
  training: "Training jobs",
  evaluation: "Evaluation runs",
};

export default function RunsPage() {
  const registry = useRunsRegistry();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<(typeof VIEWS)[number]>("all");
  const [includeLegacy, setIncludeLegacy] = useState(false);
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

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Runs"
        description="Every run in the registry, newest first. Historical baseline controllers and archived experiments stay out of the way unless you choose to show them; the benchmark tabs compare exact saved versions."
      />
      <QueryState query={registry} height={420}>
        {(data: RunsRegistry) => {
          // The registry decides what is legacy (`legacy`), so the page never has to guess from
          // a method name: a run the exporter considers current is shown by default, whatever
          // controller trained it.
          const matchesView = (run: RegistryRun) =>
            kind === "all" || (kind === "training" ? run.kind === "training" : run.kind !== "training");
          const visibleRuns = data.runs.filter((run) => {
            if (!includeLegacy && run.legacy) return false;
            if (!matchesView(run)) return false;
            const q = query.trim().toLowerCase();
            return !q || run.name.toLowerCase().includes(q) || run.runId.toLowerCase().includes(q);
          });
          const shownKinds = kind === "all" ? (["training", "evaluation"] as const) : [kind];
          const groups = shownKinds
            .map((section) => ({
              title: section === "training" ? "Training jobs" : "Evaluation runs",
              rows: visibleRuns.filter((run) => (section === "training" ? run.kind === "training" : run.kind !== "training")),
            }))
            .filter((group) => group.rows.length > 0);
          const hiddenLegacy = data.runs.filter((run) => run.legacy && matchesView(run)).length;
          return (
            <>
              <FilterBar
                query={query}
                setQuery={setQuery}
                kind={kind}
                setKind={setKind}
                includeLegacy={includeLegacy}
                setIncludeLegacy={setIncludeLegacy}
                selectedCount={selected.size}
                onCompare={() => {
                  document.getElementById("run-comparison")?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
              />
              {selected.size >= 2 ? (
                <RunComparison runs={visibleRuns.filter((run) => selected.has(run.runId))} />
              ) : null}
              {groups.map((group) => (
                <section key={group.title} className="flex flex-col gap-2">
                  <h2 className="text-sm font-semibold text-text">{group.title} <span className="text-xs font-normal text-muted">({group.rows.length})</span></h2>
                  <RunTable rows={group.rows} columns={group.title === "Training jobs" ? TRAINING_COLUMNS : METRIC_COLUMNS} onOpen={setOpenRun} onDelete={(run) => { const name = run.name || run.runId; window.confirm(`Delete run “${name}” from the registry?`) && deleteRun.mutate(run.runId); }} toggle={(id) => {
                    const next = new Set(selected);
                    if (next.has(id)) next.delete(id);
                    else next.add(id);
                    setSelected(next);
                  }} selected={selected} />
                </section>
              ))}
              {visibleRuns.length === 0 ? <EmptyData text="No run matches this filter." /> : null}
              {deleteRun.isError ? <p role="alert" className="text-xs text-jam">{deleteRun.error instanceof Error ? deleteRun.error.message : "Could not delete run."}</p> : null}
              {visibleRuns.length !== data.runs.length ? <p className="text-xs text-muted">{visibleRuns.length} of {data.runs.length} runs shown{includeLegacy ? " (legacy runs included)" : ` (${hiddenLegacy} legacy run${hiddenLegacy === 1 ? "" : "s"} hidden)`}.</p> : null}
            </>
          );
        }}
      </QueryState>
      {openRun ? <RunDrawer run={openRun} onClose={() => setOpenRun(null)} /> : null}
    </div>
  );
}

function FilterBar({
  query,
  setQuery,
  kind,
  setKind,
  includeLegacy,
  setIncludeLegacy,
  selectedCount,
  onCompare,
}: {
  query: string;
  setQuery: (value: string) => void;
  kind: string;
  setKind: (value: (typeof VIEWS)[number]) => void;
  includeLegacy: boolean;
  setIncludeLegacy: (value: boolean) => void;
  selectedCount: number;
  onCompare: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-surface px-3 py-2">
      <input
        className="input-control w-64 text-sm"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search run name or id…"
      />
      <SelectControl
        ariaLabel="Run type"
        value={kind}
        options={VIEWS.map((opt) => ({ value: opt, label: VIEW_LABEL[opt] }))}
        onChange={(value) => setKind(value as (typeof VIEWS)[number])}
        className="text-sm"
        style={{ minWidth: 160 }}
      />
      <label className="flex items-center gap-2 text-xs text-text-2"><input type="checkbox" className="check-control" checked={includeLegacy} onChange={(event) => setIncludeLegacy(event.target.checked)} /> Show old baseline and archived runs</label>
      {selectedCount > 0 ? (
        <Button size="sm" className="ml-auto" onClick={onCompare}>
          Compare {selectedCount} run{selectedCount > 1 ? "s" : ""}
        </Button>
      ) : (
        <span className="ml-auto flex items-center gap-1.5 text-xs text-muted">
          <SlidersHorizontal className="size-3.5" /> tick rows to build a comparison
        </span>
      )}
    </div>
  );
}

function RunTable({
  rows,
  columns,
  onOpen,
  toggle,
  onDelete,
  selected,
}: {
  rows: RegistryRun[];
  columns: { key: string; label: string }[];
  onOpen: (run: RegistryRun) => void;
  toggle: (id: string) => void;
  onDelete: (run: RegistryRun) => void;
  selected: Set<string>;
}) {
  if (rows.length === 0) return <EmptyData text="No run matches this filter." />;
  return (
    <Card>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full min-w-[900px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted">
              <th className="w-8 px-3 py-2" />
              <th className="px-3 py-2">Run</th>
              <th className="px-3 py-2">Policy</th>
              <th className="px-3 py-2">Network</th>
              <th className="px-3 py-2">Seed</th>
              <th className="px-3 py-2 text-right">Episodes</th>
              {columns.map((col) => (
                <th key={col.key} className="px-3 py-2 text-right tabular">
                  {col.label}
                </th>
              ))}
              <th className="px-3 py-2">Status</th>
              <th className="w-16 px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((run) => (
              <RunRow
                key={run.runId}
                run={run}
                columns={columns}
                onOpen={onOpen}
                toggle={toggle}
                isActive={selected.has(run.runId)}
                onDelete={onDelete}
              />
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function RunRow({
  run,
  columns,
  onOpen,
  toggle,
  isActive,
  onDelete,
}: {
  run: RegistryRun;
  columns: { key: string; label: string }[];
  onOpen: (run: RegistryRun) => void;
  toggle: (id: string) => void;
  isActive: boolean;
  onDelete: (run: RegistryRun) => void;
}) {
  return (
    <tr
      className={`cursor-pointer border-b border-border/60 hover:bg-surface-2 ${isActive ? "bg-accent/10" : ""}`}
      onClick={() => toggle(run.runId)}
    >
      <td className="px-3 py-2" onClick={(event) => event.stopPropagation()}>
        <input type="checkbox" checked={isActive} onChange={() => toggle(run.runId)} className="check-control" />
      </td>
      <td className="px-3 py-2 font-medium text-text">{run.name}</td>
      <td className="px-3 py-2">
        <Badge tone={run.kind === "training" ? "accent" : "neutral"}>{run.method ?? run.kind}</Badge>
      </td>
      <td className="px-3 py-2 text-text-2">{run.network ?? "—"}</td>
      <td className="px-3 py-2 text-text-2 tabular">{run.seed ?? "—"}</td>
      <td className="px-3 py-2 text-right text-text-2 tabular">{run.episodes ?? "—"}</td>
      {columns.map((col) => (
        <td key={col.key} className="px-3 py-2 text-right text-text-2 tabular">
          {run.metrics?.[col.key] != null ? Number(run.metrics[col.key]).toPrecision(4) : "—"}
        </td>
      ))}
      <td className="px-3 py-2">
        <Badge tone={STATUS_TONE[run.status] ?? "neutral"}>{run.status}</Badge>
      </td>
      <td className="px-2 py-2 flex items-center">
        <button
          type="button"
          aria-label="Run details"
          className="text-muted hover:text-text"
          onClick={(event) => {
            event.stopPropagation();
            onOpen(run);
          }}
        >
          <ChevronRight className="size-4" />
        </button>
        <button
          type="button"
          aria-label="Delete run"
          className="text-muted hover:text-jam"
          onClick={(event) => {
            event.stopPropagation();
            onDelete(run);
          }}
        >
          <Trash2 className="size-4" />
        </button>
      </td>
    </tr>
  );
}

function RunDrawer({ run, onClose }: { run: RegistryRun; onClose: () => void }) {
  const queryClient = useQueryClient();
  const polished = useFormat();
  const [modelName, setModelName] = useState("traffic-r1");
  const promote = useMutation({
    mutationFn: () =>
      api<ModelVersion>("models/promote", ModelVersion, {
        method: "POST",
        body: JSON.stringify({ runId: run.runId, name: modelName }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["data", "live", "models"] }),
  });
  const hyper: [string, string][] = Object.entries(run.hyperparameters ?? {}).map(([key, value]) => [
    key,
    typeof value === "number" ? polished.number(value, 4) : String(value),
  ]);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      onClick={onClose}
      role="presentation"
    >
      <aside
        className="h-full w-[460px] overflow-y-auto bg-surface p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-text">{run.name}</h2>
            <p className="font-mono text-xs text-muted">{run.runId}</p>
          </div>
          <button type="button" aria-label="Close details" onClick={onClose} className="text-muted hover:text-text">
            <X className="size-4" />
          </button>
        </div>

        <div className="flex flex-col gap-1 text-sm">
          <DetailRow label="Kind" value={run.kind} />
          {run.legacy ? <DetailRow label="Archive" value={run.legacyReason ?? "Legacy run; hidden by default"} /> : null}
          <DetailRow label="Policy" value={run.method ?? run.model ?? "—"} />
          <DetailRow label="Evaluation seeds" value={run.seeds?.length ? run.seeds.join(", ") : "—"} />
          <DetailRow label="Type" value={run.type} />
          <DetailRow label="Network" value={run.network ?? "—"} />
          <DetailRow label="Scenario" value={run.scenario ?? "—"} />
          <DetailRow label="Demand" value={run.demand ?? "—"} />
          <DetailRow label="Seed" value={run.seed != null ? String(run.seed) : "—"} />
          <DetailRow label="Algorithm" value={run.algorithm ?? "—"} />
          <DetailRow label="Status" value={run.status} />
        </div>

        {hyper.length > 0 ? (
          <>
            <CardHeader className="mt-6 px-0 py-0">
              <CardTitle className="text-sm">Hyperparameters</CardTitle>
            </CardHeader>
            <div className="mt-2 grid grid-cols-2 gap-1 text-sm">
              {hyper.map(([key, value]) => (
                <DetailRow key={key} label={key} value={value} compact />
              ))}
            </div>
          </>
        ) : null}

        {run.metrics && Object.keys(run.metrics).length > 0 ? (
          <>
            <CardHeader className="mt-6 px-0 py-0">
              <CardTitle className="text-sm">Metrics</CardTitle>
              <CardDescription className="text-xs">
                95 % CI where seeds allow it ({run.metricStats && Object.keys(run.metricStats).length ? "paired" : "single"}).
              </CardDescription>
            </CardHeader>
            <div className="mt-2 grid grid-cols-2 gap-1 text-sm">
              {Object.entries(run.metrics)
                .filter(([, value]) => value != null)
                .map(([key, value]) => (
                  <DetailRow key={key} label={key} value={polished.number(Number(value), 3)} compact />
                ))}
            </div>
          </>
        ) : null}

        <CardHeader className="mt-6 px-0 py-0">
          <CardTitle className="text-sm">Artifacts</CardTitle>
        </CardHeader>
        <ul className="mt-2 space-y-1 text-xs text-text-2">
          {Object.entries(run.artifacts ?? {}).length === 0 ? (
            <li>—</li>
          ) : (
            Object.entries(run.artifacts).map(([key, value]) => (
              <li key={key} className="font-mono">
                {key}: {String(value)}
              </li>
            ))
          )}
        </ul>

        <CardHeader className="mt-6 px-0 py-0">
          <CardTitle className="text-sm">Save as model</CardTitle>
        </CardHeader>
        <div className="mt-2 flex gap-2">
          <input
            className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-text"
            value={modelName}
            onChange={(event) => setModelName(event.target.value)}
            aria-label="Model name"
          />
          <Button size="sm" disabled={promote.isPending} onClick={() => promote.mutate()}>
            {promote.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        {promote.isError ? (
          <p className="mt-2 text-xs text-jam">{(promote.error as Error).message}</p>
        ) : null}
        {promote.isSuccess ? (
          <p className="mt-2 text-xs text-flow">
            Saved as {modelName} · v{promote.data.version} — see the Models page.
          </p>
        ) : null}
      </aside>
    </div>
  );
}

function DetailRow({ label, value, compact = false }: { label: string; value: string; compact?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-border/40 py-1">
      <span className={compact ? "text-xs text-muted" : "text-sm text-muted"}>{label}</span>
      <span className={`text-text ${compact ? "text-xs tabular" : "text-sm"}`}>{value}</span>
    </div>
  );
}

/*
 * Rami-style comparison (analytics branch): gain-% forest, a method × cell heatmap and a
 * tests table with CSV export, built on the shared chart kit. Runs roll up to
 * (lab, network · scenario · demand) cells; the gain is signed so positive = better.
 */

interface CellMetric { mean: number; lo: number | null; hi: number | null }
interface RunCellStat { metrics: Record<string, CellMetric>; seeds: number[] }

type Grouped = Map<string, Map<string, RunCellStat>>;

const COMPARABLE_METRICS = [
  "mean_waiting_time",
  "mean_travel_time",
  "throughput_per_h",
  "co2_total_kg",
  "stops_per_vehicle",
  "teleports_total",
];

/** Gain CI by envelope: extreme gains over the corner combinations of run and reference CIs. */
function gainEnvelope(
  metric: string,
  mean: number,
  lo: number | null,
  hi: number | null,
  refMean: number,
  refLo: number | null,
  refHi: number | null,
): { lo: number; hi: number; significant: boolean } {
  const dv = lo !== null && hi !== null ? (hi - lo) / 2 : 0;
  const dr = refLo !== null && refHi !== null ? (refHi - refLo) / 2 : 0;
  const gains = [
    gainPct(metric, mean - dv, refMean - dr) ?? 0,
    gainPct(metric, mean - dv, refMean + dr) ?? 0,
    gainPct(metric, mean + dv, refMean - dr) ?? 0,
    gainPct(metric, mean + dv, refMean + dr) ?? 0,
  ];
  const ciLo = Math.min(...gains);
  const ciHi = Math.max(...gains);
  return { lo: ciLo, hi: ciHi, significant: ciLo > 0 || ciHi < 0 };
}

function RunComparison({ runs }: { runs: RegistryRun[] }) {
  const f = useFormat();
  const rtl = false;
  const [metric, setMetric] = useState<string | null>(null);
  const [reference, setReference] = useState<string | null>(null);
  const [controller, setController] = useState<string | null>(null);

  const cellName = (network: string, scenario: string, demand: string) =>
    `${f.networkName(network)} · ${f.scenarioName(scenario)} · ${f.demandName(demand)}`;

  const { grouped, cells, metrics } = useMemo(() => {
    const grouped: Grouped = new Map();
    const cellLabels = new Map<string, string>();
    const finalMetrics = new Set<string>();
    for (const run of runs) {
      if (!run.network || !run.scenario || !run.demand) continue;
      const cellKey = `${run.network}\u0000${run.scenario}\u0000${run.demand}`;
      cellLabels.set(cellKey, cellName(run.network, run.scenario, run.demand));
      const cellMap = grouped.get(run.name) ?? new Map<string, RunCellStat>();
      grouped.set(run.name, cellMap);
      const entry: RunCellStat = cellMap.get(cellKey) ?? { metrics: {}, seeds: [] };
      for (const key of COMPARABLE_METRICS) {
        const raw = run.metrics[key];
        if (raw == null) continue;
        const value = Number(raw);
        if (!Number.isFinite(value)) continue;
        finalMetrics.add(key);
        const stats = run.metricStats?.[key];
        const lo = typeof stats?.ciLo === "number" ? stats.ciLo : null;
        const hi = typeof stats?.ciHi === "number" ? stats.ciHi : null;
        const prev = entry.metrics[key];
        // existing values or seeds, averaged
        const seed = run.seed ?? 0;
        const seen = entry.seeds.includes(seed);
        entry.seeds = seen ? entry.seeds : [...entry.seeds, seed];
        if (prev) {
          const n = entry.seeds.length || 1;
          entry.metrics[key] = {
            mean: prev.mean + (value - prev.mean) / n,
            lo: prev.lo === null && lo === null ? null : ((prev.lo ?? prev.mean) + (lo ?? value)) / 2,
            hi: prev.hi === null && hi === null ? null : ((prev.hi ?? prev.mean) + (hi ?? value)) / 2,
          };
        } else {
          entry.metrics[key] = { mean: value, lo, hi };
        }
      }
      cellMap.set(cellKey, entry);
    }
    const cells = [...cellLabels.keys()].map((k) => ({ key: k, label: cellLabels.get(k) ?? k }));
    return {
      grouped,
      cells,
      metrics: COMPARABLE_METRICS.filter((m) => finalMetrics.has(m)),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs, f]);

  const methods = [...grouped.keys()];
  const activeMetric = metric && metrics.includes(metric) ? metric : (metrics[0] ?? "mean_waiting_time");
  const activeRef = reference && methods.includes(reference) ? reference : (methods[0] ?? "");
  const activeController =
    controller && methods.includes(controller) && controller !== activeRef
      ? controller
      : (methods.find((m) => m !== activeRef) ?? activeRef);

  const statsOf = (name: string, cellKey: string): { metric: CellMetric | null; seeds: number[] } => {
    const entry = grouped.get(name)?.get(cellKey);
    return { metric: entry?.metrics[activeMetric] ?? null, seeds: entry?.seeds ?? [] };
  };
  const gainOf = (name: string, cellKey: string) => {
    const mine = statsOf(name, cellKey).metric;
    const ref = statsOf(activeRef, cellKey).metric;
    if (!mine || !ref) return null;
    const point = gainPct(activeMetric, mine.mean, ref.mean);
    if (point === null) return null;
    const env = gainEnvelope(
      activeMetric, mine.mean, mine.lo, mine.hi, ref.mean, ref.lo, ref.hi,
    );
    return { point, lo: env.lo, hi: env.hi, significant: env.significant };
  };

  const controllerColor = methodColor(activeController);

  const buildForest = useCallback(
    (tk: ChartTokens) => {
      const items = cells
        .flatMap(({ key, label }) => {
          const gain = gainOf(activeController, key);
          return gain
            ? [{ label, value: gain.point, lo: gain.lo, hi: gain.hi, significant: gain.significant, color: controllerColor }]
            : [];
        })
        .sort((a, b) => a.label.localeCompare(b.label));
      return forest(tk, {
        items,
        xName: "Gain vs " + activeRef + " (%)",
        rtl,
        format: (v) => f.pct(v),
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cells, grouped, activeController, activeRef, activeMetric, controllerColor, f, rtl],
  );

  const buildHeat = useCallback(
    (tk: ChartTokens) =>
      heatmap(tk, {
        rows: methods,
        columns: cells.map((c) => c.label),
        values: methods.flatMap((m, y) =>
          cells.map(({ key }, x): [number, number, number] | [number, number, null] => {
            if (m === activeRef) return [x, y, 0];
            const gain = gainOf(m, key);
            return gain ? [x, y, Number(gain.point.toFixed(1))] : [x, y, null];
          }),
        ),
        format: (v) => f.number(v, 1),
        rtl,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [methods, cells, grouped, activeRef, activeMetric, f, rtl],
  );

  const tableRows = methods
    .flatMap((m) =>
      cells.flatMap(({ key, label }) => {
        const mine = statsOf(m, key);
        const ref = statsOf(activeRef, key);
        if (!mine.metric || !ref.metric) return [];
        const gain = m === activeRef ? { point: 0, lo: 0, hi: 0, significant: false } : gainOf(m, key);
        if (!gain) return [];
        return [
          {
            run: m,
            cell: label,
            metric: f.metricName(activeMetric),
            value: f.metric(mine.metric.mean, activeMetric),
            reference_run: activeRef,
            reference_value: f.metric(ref.metric.mean, activeMetric),
            gain_pct: f.pct(gain.point),
            gain_ci: `${f.pct(gain.lo)} ; ${f.pct(gain.hi)}`,
            seeds: mine.seeds.join(", ") || "–",
            significant: gain.significant,
          },
        ];
      }),
    )
    .sort((a, b) => a.run.localeCompare(b.run) || a.cell.localeCompare(b.cell));

  const forestItems = cells.filter(({ key }) => gainOf(activeController, key) !== null).length;

  if (methods.length < 2 || cells.length === 0) {
    return (
      <section id="run-comparison" className="rounded-md border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold text-text">Run comparison</h2>
        <p className="text-sm text-muted">
          Tick at least two runs that share an evaluation cell (network · scenario · demand) to compare them here.
        </p>
      </section>
    );
  }

  const selector = (label: string, value: string, options: string[], onChange: (v: string) => void) => (
    <div className="flex flex-col gap-1 text-xs text-muted">
      <span>{label}</span>
      <SelectControl
        ariaLabel={label}
        value={value}
        options={options.map((o) => ({ value: o, label: o }))}
        onChange={onChange}
        className="text-sm"
        style={{ minWidth: 160 }}
      />
    </div>
  );

  return (
    <section id="run-comparison" className="flex flex-col gap-4 rounded-md border border-border bg-surface p-4">
      <div className="flex flex-wrap items-end gap-4">
        <h2 className="text-sm font-semibold text-text">Run comparison</h2>
        {selector("Metric", activeMetric, metrics, setMetric)}
        {selector("Reference", activeRef, methods, setReference)}
        {selector("Run", activeController, methods.filter((m) => m !== activeRef), (v) => setController(v))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard
          title={`Forest · ${activeController} vs ${activeRef}`}
          description="Gain % per cell (positive = better than the reference run); whiskers span run and reference CIs where seeds allow them."
          table={cells.map(({ key, label }) => {
            const mine = statsOf(activeController, key).metric;
            const ref = statsOf(activeRef, key).metric;
            const gain = mine && ref ? gainOf(activeController, key) : null;
            return {
              cell: label,
              gain_pct: gain ? f.pct(gain.point) : "–",
              ci: gain && mine && ref ? `${f.pct(gain.lo)} ; ${f.pct(gain.hi)}` : "–",
            };
          })}
        >
          {forestItems ? (
            <EChart build={buildForest} height={Math.max(220, forestItems * 34 + 70)} label="Forest" />
          ) : (
            <EmptyData text="No shared cell between the selected runs." />
          )}
        </ChartCard>
        <ChartCard
          title="Heatmap"
          description="Gain % of every run against the reference, per shared evaluation cell; red = worse, green = better."
          table={cells.map(({ key, label }) =>
            Object.fromEntries([
              ["cell", label],
              ...methods.map((m) => [m, f.pct(m === activeRef ? 0 : gainOf(m, key)?.point ?? null)]),
            ]),
          )}
        >
          <EChart build={buildHeat} height={Math.max(260, methods.length * 40 + 180)} label="Heatmap" />
        </ChartCard>
      </div>
      <ChartCard
        title={`Tests · ${f.metricName(activeMetric)}`}
        description="Point estimates from the registry; a filled point means the gain CI excludes zero."
        table={tableRows}
        csvName={`runs_tests_${activeMetric}.csv`}
      >
        <div
          tabIndex={0}
          role="region"
          aria-label="Tests table"
          className="max-h-[420px] overflow-auto rounded-md border border-border"
        >
          <table className="w-full text-xs">
            <caption className="sr-only">Run comparison tests</caption>
            <thead className="sticky top-0 z-10 bg-surface-2 text-text-2">
              <tr>
                {["Run", "Cell", "Value", "Reference", "Ref value", "Gain %", "Gain CI", "Seeds", ""].map((h, i) => (
                  <th key={i} scope="col" className="px-2 py-2 text-start font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular">
              {tableRows.map((row, i) => (
                <tr key={i} className="border-t border-border hover:bg-surface-2">
                  <td className="px-2 py-1.5">
                    <span className="inline-flex items-center gap-1.5">
                      <span aria-hidden="true" className="size-2 rounded-full" style={{ background: methodColor(row.run) }} />
                      {row.run}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-text-2">{row.cell}</td>
                  <td className="px-2 py-1.5">{row.value}</td>
                  <td className="px-2 py-1.5 text-text-2">{row.reference_run}</td>
                  <td className="px-2 py-1.5 text-text-2">{row.reference_value}</td>
                  <td className={row.gain_pct.startsWith("-") ? "px-2 py-1.5 text-jam" : "px-2 py-1.5 text-flow"}>{row.gain_pct}</td>
                  <td className="px-2 py-1.5 text-muted">{row.gain_ci}</td>
                  <td className="px-2 py-1.5 text-text-2">{row.seeds}</td>
                  <td className="px-2 py-1.5">
                    <Badge tone={row.significant ? "flow" : "neutral"}>
                      {row.significant ? "significant" : "not significant"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </section>
  );
}
