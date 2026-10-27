import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useCatalog } from "@/shared/api/backend";
import {
  isActiveJob,
  useCancelJob,
  useJobStream,
  useJobs,
  useStartCompare,
  type Job,
} from "@/shared/api/jobs";
import { QueryState } from "@/shared/components/QueryState";
import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { SelectControl } from "@/shared/ui/select";

const DEMANDS = ["low", "medium", "peak", "rush_profile"] as const;
const SCENARIOS = ["normal", "emergency", "pedestrians", "buses", "incident", "sensor_noise"] as const;

/** Fresh paired A/B on the live backend: POST /api/compare, SSE progress, paired deltas. */
export default function FreshCompare() {
  const { t } = useTranslation();
  const f = useFormat();
  const catalog = useCatalog();
  const jobs = useJobs();
  const startCompare = useStartCompare();
  const cancelJob = useCancelJob();

  const activeCompare = useMemo(
    () => jobs.data?.find((job) => job.kind === "compare" && isActiveJob(job)) ?? null,
    [jobs.data],
  );
  const finished = useMemo(
    () =>
      jobs.data
        ?.filter((job) => job.kind === "compare" && job.status === "done")
        .slice(0, 4) ?? [],
    [jobs.data],
  );
  const [focusId, setFocusId] = useState<string | null>(null);
  const focus = finished.find((j) => j.id === focusId) ?? null;
  useJobStream(activeCompare?.id ?? focus?.id ?? null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("compare.fresh.title")}</CardTitle>
        <CardDescription>{t("compare.fresh.description")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <QueryState query={catalog} height={120}>
          {(c) => (
            <FreshForm
              catalog={c}
              disabled={Boolean(activeCompare) || startCompare.isPending}
              onSubmit={(request) =>
                startCompare.mutate(request, {
                  onError: () => undefined,
                })
              }
              error={
                startCompare.error instanceof Error ? startCompare.error.message : null
              }
            />
          )}
        </QueryState>

        {startCompare.error || activeCompare ? (
          <JobProgress
            job={activeCompare}
            error={startCompare.error instanceof Error ? startCompare.error.message : null}
            onCancel={activeCompare ? () => cancelJob.mutate(activeCompare.id) : undefined}
          />
        ) : null}

        {finished.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-text-2">{t("compare.fresh.recent")}</span>
            {finished.map((job) => (
              <Button
                key={job.id}
                variant={focusId === job.id ? "default" : "outline"}
                size="sm"
                onClick={() => setFocusId(job.id)}
              >
                {job.request.network} · {f.number(job.request.seeds?.length ?? 1)} seeds
              </Button>
            ))}
          </div>
        )}
        {focus ? <CompareResult jobId={focus.id} result={focus.result} /> : null}
      </CardContent>
    </Card>
  );
}

type Catalog = NonNullable<ReturnType<typeof useCatalog>["data"]>;

function FreshForm({
  catalog,
  disabled,
  onSubmit,
  error,
}: {
  catalog: Catalog;
  disabled: boolean;
  onSubmit: (request: {
    network: string;
    scenario: string;
    demand: string;
    seeds: number[];
    methods: string[];
    quick: boolean;
  }) => void;
  error: string | null;
}) {
  const { t } = useTranslation();
  const networks = catalog.networks.filter((n) => n.runnable);
  const [network, setNetwork] = useState(networks[0]?.network ?? "");
  const [scenario, setScenario] = useState("normal");
  const [demand, setDemand] = useState("medium");
  const [seeds, setSeeds] = useState(2);
  const [quick, setQuick] = useState(true);
  const selected = catalog.networks.find((n) => n.network === network);
  const all = catalog.controllers.map((c) => c.method);
  const methods = all.filter((m) => {
    const cc = selected?.controllers[m];
    return !cc || cc.available;
  });
  const [picked, setPicked] = useState<string[]>([]);
  const valid = [...picked, "mp"].filter(
    (m, i, arr) => arr.indexOf(m) === i && methods.includes(m),
  );
  const pick = (m: string) =>
    setPicked((p) =>
      p.includes(m) ? p.filter((x) => x !== m) : [...p, m].slice(0, 4),
    );

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Field label={t("filters.network")}>
        <SelectControl
          ariaLabel={t("filters.network")}
          value={network}
          options={networks.map((n) => ({ value: n.network, label: n.title }))}
          onChange={setNetwork}
        />
      </Field>
      <Field label={t("filters.scenario")}>
        <SelectControl
          ariaLabel={t("filters.scenario")}
          value={scenario}
          options={SCENARIOS.map((s) => ({
            value: s,
            label: t(`training.scenario_${s}`, { defaultValue: s }),
          }))}
          onChange={setScenario}
        />
      </Field>
      <Field label={t("filters.demand")}>
        <SelectControl
          ariaLabel={t("filters.demand")}
          value={demand}
          options={DEMANDS.map((d) => ({ value: d, label: t(`demands.${d}`) }))}
          onChange={setDemand}
        />
      </Field>
      <Field label={t("compare.fresh.seeds")}>
        <SelectControl
          ariaLabel={t("compare.fresh.seeds")}
          value={String(seeds)}
          options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) }))}
          onChange={(next) => setSeeds(Number(next))}
        />
      </Field>
      <div className="sm:col-span-4 flex flex-wrap items-center gap-2">
        {methods.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => pick(m)}
            className={
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs " +
              (picked.includes(m)
                ? "border-flow bg-flow/10 text-flow"
                : "border-border text-text-2 hover:bg-surface-2")
            }
          >
            <span
              aria-hidden="true"
              className="size-2 rounded-full"
              style={{ background: methodColor(m) }}
            />
            {m}
          </button>
        ))}
        <span className="text-xs text-muted">{t("compare.fresh.chipHint")}</span>
      </div>
      <div className="sm:col-span-4 flex items-center gap-3">
        <label className="inline-flex items-center gap-2 text-xs text-text-2">
          <input type="checkbox" checked={quick} onChange={() => setQuick(!quick)} />
          {t("compare.fresh.quick")}
        </label>
        <Button disabled={disabled || !network} onClick={() => onSubmit({ network, scenario, demand, seeds: Array.from({ length: seeds }, (_, i) => 3 + i), methods: valid, quick })}>
          {t("compare.fresh.run")}
        </Button>
        {error ? <span className="text-xs text-jam">{error}</span> : null}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 text-xs text-text-2">
      <span>{label}</span>
      {children}
    </div>
  );
}

function JobProgress({
  job,
  error,
  onCancel,
}: {
  job: Job | null;
  error: string | null;
  onCancel?: () => void;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const pct = job && job.totalSteps > 0 ? (job.step / job.totalSteps) * 100 : 0;
  return (
    <div className="rounded-md border border-border p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium">
          {t("compare.fresh.progress", {
            step: job?.step ?? 0,
            total: job?.totalSteps ?? 0,
          })}
          {job?.status === "done" ? ` — ${t("kpi.done")}` : ""}
        </span>
        {onCancel && job ? (
          <Button variant="outline" size="sm" onClick={onCancel}>
            <X aria-hidden="true" className="size-3" />
            {t("jobs.cancel")}
          </Button>
        ) : null}
      </div>
      <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
        <div
          className="h-full bg-flow transition-all"
          style={{ width: `${Math.min(100, Math.max(2, pct))}%` }}
        />
      </div>
      {error ? <div className="text-xs text-jam">{error}</div> : null}
      {job?.log.slice(-3).map((line, i) => (
        <div key={i} className="text-xs text-muted tabular">
          {line}
        </div>
      ))}
      {job?.error ? <div className="text-xs text-jam">{job.error}</div> : null}
      {f && job?.status === "failed" ? (
        <div className="text-xs text-jam">{t("compare.fresh.failed")}</div>
      ) : null}
    </div>
  );
}

function CompareResult({ result }: { result: unknown }) {
  const { t } = useTranslation();
  const f = useFormat();
  const r = result as null | {
    verdict?: string;
    warnings?: string[];
    reference?: string;
    comparisons?: Array<{
      metric: string;
      method: string;
      reference: string;
      isReference: boolean;
      mean: number;
      referenceMean: number;
      pairedImprovementPct: number;
      pairedCiLo: number;
      pairedCiHi: number;
      pHolm: number | null;
      significant: boolean;
    }>;
    llm?: Record<string, { validSeeds: number; seeds: number; lastError: string; coveragePct: number }>;
  };
  if (!r?.comparisons) return null;
  const wait = r.comparisons.filter((c) => c.metric === "mean_waiting_time");
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-md border border-flow/40 bg-flow/5 p-3 text-sm">
        {r.verdict ?? null}
      </div>
      {(r.warnings ?? []).map((w, i) => (
        <div key={i} className="text-xs text-amber-600">
          {w}
        </div>
      ))}
      <div className="overflow-auto rounded-md border border-border">
        <table className="w-full text-xs">
          <caption className="sr-only">{t("compare.fresh.title")}</caption>
          <thead className="bg-surface-2 text-text-2">
            <tr>
              {[t("filters.controller"), t("analytics.mean"), t("analytics.gain"), t("kpi.ci"), t("analytics.pHolm"), ""].map(
                (h, i) => (
                  <th key={i} scope="col" className="px-2 py-2 text-start font-medium">
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="tabular">
            {wait.map((c, i) => (
              <tr key={i} className="border-t border-border">
                <td className="px-2 py-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      className="size-2 rounded-full"
                      style={{ background: methodColor(c.method) }}
                    />
                    {f.methodName(c.method)}
                  </span>
                </td>
                <td className="px-2 py-1.5">{f.metric(c.mean, c.metric)}</td>
                <td className={c.isReference ? "px-2 py-1.5 text-muted" : c.pairedImprovementPct > 0 ? "px-2 py-1.5 text-flow" : "px-2 py-1.5 text-jam"}>
                  {c.isReference ? t("analytics.reference") : f.pct(c.pairedImprovementPct)}
                </td>
                <td className="px-2 py-1.5 text-muted">
                  {c.isReference ? "–" : `${f.pct(c.pairedCiLo)} ; ${f.pct(c.pairedCiHi)}`}
                </td>
                <td className="px-2 py-1.5">{c.pHolm == null ? "–" : f.number(c.pHolm, 3)}</td>
                <td className="px-2 py-1.5">
                  <Badge tone={c.significant ? "flow" : "neutral"}>
                    {c.significant ? t("kpi.significant") : t("kpi.notSignificant")}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.llm
        ? Object.entries(r.llm).map(([method, h]) => (
            <div key={method} className="text-xs text-muted">
              {f.methodName(method)}: {h.validSeeds}/{h.seeds} {t("compare.fresh.validSeeds")} ·{" "}
              {t("compare.fresh.coverage")} {h.coveragePct}%
              {h.lastError ? ` · ${h.lastError}` : ""}
            </div>
          ))
        : null}
    </div>
  );
}
