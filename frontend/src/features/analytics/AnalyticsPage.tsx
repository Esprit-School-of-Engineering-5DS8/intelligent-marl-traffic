import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useComparisons, useDistribution, useMeta } from "@/shared/api/queries";
import { forest, heatmap, lines } from "@/shared/charts/builders";
import { ChartCard } from "@/shared/charts/ChartCard";
import { EChart } from "@/shared/charts/EChart";
import type { ChartTokens } from "@/shared/charts/tokens";
import {
  CellPicker,
  MethodChips,
  MethodSelect,
  MetricSelect,
  Select,
} from "@/shared/components/pickers";
import { EmptyData, QueryState } from "@/shared/components/QueryState";
import { cellKey, compareCells } from "@/shared/domain/cells";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColor, sortMethods } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import { useRtl } from "@/shared/lib/use-rtl";
import type { Comparison, DistributionCell, Meta } from "@/shared/schemas";
import { useFilters, useReconciledFilters } from "@/shared/state/filters";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

export default function AnalyticsPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.analytics.title"));
  const meta = useMeta();
  const comparisons = useComparisons();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("pages.analytics.title")}
        description={t("pages.analytics.description")}
      />
      <QueryState query={meta} height={80}>
        {(m) => (
          <QueryState query={comparisons} height={420}>
            {(rows) => <Analytics meta={m} rows={rows} />}
          </QueryState>
        )}
      </QueryState>
    </div>
  );
}

function Analytics({ meta, rows }: { meta: Meta; rows: Comparison[] }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const rtl = useRtl();
  const { controller, reference, setController, setReference } = useFilters();
  useReconciledFilters(meta);
  const metrics = [...new Set(rows.map((r) => r.metric))];
  const [metric, setMetric] = useState(
    metrics.includes("mean_waiting_time") ? "mean_waiting_time" : (metrics[0] ?? ""),
  );
  const [network, setNetwork] = useState("all");
  const [family, setFamily] = useState("all");

  const scoped = useMemo(
    () =>
      rows.filter(
        (r) =>
          r.metric === metric &&
          r.reference === reference &&
          (network === "all" || r.network === network) &&
          (family === "all" || r.family === family),
      ),
    [rows, metric, reference, network, family],
  );
  const references = sortMethods(new Set(rows.map((r) => r.reference)));
  const methods = sortMethods(new Set(scoped.map((r) => r.method)));
  const networks = [...new Set(rows.map((r) => r.network))];
  const families = [...new Set(rows.map((r) => r.family))];

  const mine = scoped
    .filter((r) => r.method === controller && r.pairedImprovementPct !== null)
    .sort(compareCells);

  const buildForest = useCallback(
    (tk: ChartTokens) =>
      forest(tk, {
        items: mine.map((r) => ({
          label: f.cellName(r),
          value: r.pairedImprovementPct ?? 0,
          lo: r.pairedCiLo ?? r.pairedImprovementPct ?? 0,
          hi: r.pairedCiHi ?? r.pairedImprovementPct ?? 0,
          color: methodColor(controller),
          significant: r.significant,
        })),
        xName: `${t("analytics.gain")} (%)`,
        rtl,
        format: (v) => f.pct(v),
      }),
    [mine, f, controller, t, rtl],
  );

  const cells = [...new Map(scoped.map((r) => [cellKey(r), r])).values()].sort(compareCells);
  const buildHeat = useCallback(
    (tk: ChartTokens) =>
      heatmap(tk, {
        rows: methods.map((m) => f.methodName(m)),
        columns: cells.map((c) => f.cellName(c)),
        values: methods.flatMap((m, y) =>
          cells.map((c, x): [number, number, number | null] => [
            x,
            y,
            scoped.find((r) => r.method === m && cellKey(r) === cellKey(c))?.pairedImprovementPct ??
              null,
          ]),
        ),
        format: (v) => f.number(v, 0),
        rtl,
      }),
    [methods, cells, scoped, f, rtl],
  );

  return (
    <>
      <Card>
        <CardContent className="grid gap-3 pt-4 sm:grid-cols-2 lg:grid-cols-5">
          <MetricSelect
            label={t("filters.metric")}
            value={metric}
            metrics={metrics}
            onChange={setMetric}
          />
          <MethodSelect
            label={t("filters.controller")}
            value={controller}
            methods={methods}
            onChange={setController}
          />
          <MethodSelect
            label={t("filters.reference")}
            value={reference}
            methods={references}
            onChange={setReference}
          />
          <Select
            label={t("filters.network")}
            value={network}
            options={[
              { value: "all", label: t("filters.all") },
              ...networks.map((n) => ({ value: n, label: f.networkName(n) })),
            ]}
            onChange={setNetwork}
          />
          <Select
            label={t("filters.family")}
            value={family}
            options={[
              { value: "all", label: t("filters.all") },
              ...families.map((x) => ({
                value: x,
                label: tx(`analytics.families.${x}`, { defaultValue: x }),
              })),
            ]}
            onChange={setFamily}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard
          title={`${t("analytics.forest")} · ${f.methodName(controller)} ${t("kpi.vs", { ref: f.methodName(reference) })}`}
          description={t("analytics.forestText")}
          table={mine.map((r) => ({
            [t("analytics.cell")]: f.cellName(r),
            [t("analytics.gain")]: f.pct(r.pairedImprovementPct),
            [t("kpi.ci")]: `${f.pct(r.pairedCiLo)} ; ${f.pct(r.pairedCiHi)}`,
            [t("analytics.pHolm")]: f.number(r.pHolm, 3),
          }))}
        >
          {mine.length ? (
            <EChart
              build={buildForest}
              height={Math.max(220, mine.length * 30 + 60)}
              label={t("analytics.forest")}
            />
          ) : (
            <EmptyData text={t("analytics.noComparisons")} />
          )}
        </ChartCard>

        <ChartCard title={t("analytics.heatmap")} description={t("analytics.heatmapText")}>
          {methods.length && cells.length ? (
            <EChart
              build={buildHeat}
              height={Math.max(260, methods.length * 34 + 140)}
              label={t("analytics.heatmap")}
            />
          ) : (
            <EmptyData />
          )}
        </ChartCard>
      </div>

      <TestsTable rows={scoped} metric={metric} />
      <Distribution meta={meta} />
    </>
  );
}

function TestsTable({ rows, metric }: { rows: Comparison[]; metric: string }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const order = sortMethods(new Set(rows.map((r) => r.method)));
  const sorted = [...rows].sort(
    (a, b) => compareCells(a, b) || order.indexOf(a.method) - order.indexOf(b.method),
  );
  const csv = sorted.map((r) => ({
    network: r.network,
    scenario: r.scenario,
    demand: r.demand,
    controller: r.method,
    reference: r.reference,
    metric: r.metric,
    mean: r.mean,
    reference_mean: r.referenceMean,
    paired_improvement_pct: r.pairedImprovementPct,
    ci_lo: r.pairedCiLo,
    ci_hi: r.pairedCiHi,
    p_holm: r.pHolm,
    effect: r.effect,
    significant: r.significant,
    family: r.family,
  }));
  return (
    <ChartCard
      title={`${t("analytics.table")} · ${f.metricName(metric)}`}
      description={t("analytics.tableText")}
      table={csv}
      csvName={`tests_${metric}.csv`}
    >
      <div
        tabIndex={0}
        role="region"
        aria-label={t("analytics.table")}
        className="max-h-[420px] overflow-auto rounded-md border border-border"
      >
        <table className="w-full text-xs">
          <caption className="sr-only">{t("analytics.table")}</caption>
          <thead className="sticky top-0 z-10 bg-surface-2 text-text-2">
            <tr>
              {[
                t("analytics.cell"),
                t("filters.controller"),
                t("analytics.mean"),
                t("analytics.referenceMean"),
                t("analytics.gain"),
                t("kpi.ci"),
                t("analytics.pHolm"),
                t("analytics.effect"),
                "",
              ].map((h, i) => (
                <th key={i} scope="col" className="px-2 py-2 text-start font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="tabular">
            {sorted.map((r, i) => {
              const gain = r.pairedImprovementPct;
              return (
                <tr key={i} className="border-t border-border hover:bg-surface-2">
                  <td className="px-2 py-1.5 text-text-2">{f.cellName(r)}</td>
                  <td className="px-2 py-1.5">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        aria-hidden="true"
                        className="size-2 rounded-full"
                        style={{ background: methodColor(r.method) }}
                      />
                      {f.methodName(r.method)}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">{f.metric(r.mean, metric)}</td>
                  <td className="px-2 py-1.5 text-text-2">{f.metric(r.referenceMean, metric)}</td>
                  <td
                    className={
                      gain === null
                        ? "px-2 py-1.5"
                        : gain > 0
                          ? "px-2 py-1.5 text-flow"
                          : "px-2 py-1.5 text-jam"
                    }
                  >
                    {f.pct(gain)}
                  </td>
                  <td className="px-2 py-1.5 text-muted">
                    {f.pct(r.pairedCiLo)} ; {f.pct(r.pairedCiHi)}
                  </td>
                  <td className="px-2 py-1.5">{f.number(r.pHolm, 3)}</td>
                  <td className="px-2 py-1.5 text-text-2">
                    {r.effect
                      ? tx(`analytics.effects.${r.effect}`, { defaultValue: r.effect })
                      : "–"}
                  </td>
                  <td className="px-2 py-1.5">
                    <Badge tone={r.significant ? "flow" : "neutral"}>
                      {r.significant ? t("kpi.significant") : t("kpi.notSignificant")}
                    </Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}

function Distribution({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const { cell, setCell, controllers, toggleController } = useFilters();
  const query = useDistribution(cell);
  return (
    <ChartCard title={t("analytics.distribution")} description={t("analytics.distributionText")}>
      <div className="mb-3">
        <CellPicker meta={meta} value={cell} onChange={setCell} />
      </div>
      <QueryState query={query} height={300}>
        {(d) => <DistributionChart dist={d} selected={controllers} onToggle={toggleController} />}
      </QueryState>
    </ChartCard>
  );
}

function DistributionChart({
  dist,
  selected,
  onToggle,
}: {
  dist: DistributionCell;
  selected: string[];
  onToggle: (m: string) => void;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const rtl = useRtl();
  const methods = sortMethods(Object.keys(dist.methods));
  const shown = methods.filter((m) => selected.includes(m));
  const first = dist.methods[methods[0] ?? ""];
  // bins beyond 5 minutes hold few vehicles: cut there for readability
  const limit = first ? first.from.findIndex((x) => x >= 300) : -1;
  const n = limit === -1 ? (first?.from.length ?? 0) : limit;
  const build = useCallback(
    (tk: ChartTokens) =>
      lines(tk, {
        x: (first?.from ?? []).slice(0, n),
        series: shown.map((m) => ({
          name: f.methodName(m),
          color: methodColor(m),
          data: (dist.methods[m]?.vehicles ?? []).slice(0, n),
        })),
        xName: t("analytics.bin"),
        yName: t("analytics.vehicles"),
        format: (v) => f.number(v, 0),
        rtl,
      }),
    [first, n, shown, dist, f, t, rtl],
  );
  return (
    <div className="flex flex-col gap-3">
      <MethodChips
        label={t("filters.controllers")}
        methods={methods}
        selected={selected}
        onToggle={onToggle}
      />
      {shown.length ? (
        <EChart build={build} height={300} label={t("analytics.distribution")} />
      ) : (
        <EmptyData />
      )}
    </div>
  );
}
