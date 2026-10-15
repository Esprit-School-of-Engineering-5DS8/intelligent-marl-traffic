import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useComparisons, useMeta, useSummary, useTimeseries } from "@/shared/api/queries";
import { barsWithCi, lines } from "@/shared/charts/builders";
import { ChartCard } from "@/shared/charts/ChartCard";
import { EChart } from "@/shared/charts/EChart";
import type { ChartTokens } from "@/shared/charts/tokens";
import { KpiCard } from "@/shared/components/KpiCard";
import { CellPicker, MethodSelect, MetricSelect } from "@/shared/components/pickers";
import { EmptyData, QueryState } from "@/shared/components/QueryState";
import { useFormat } from "@/shared/domain/format";
import { methodColor, sortMethods } from "@/shared/domain/methods";
import { MAIN_METRICS } from "@/shared/domain/metrics";
import { findComparison, indexSummary } from "@/shared/domain/results";
import { usePageTitle } from "@/shared/lib/use-page-title";
import { useRtl } from "@/shared/lib/use-rtl";
import type { Comparison, Meta, SummaryRow, TimeseriesCell } from "@/shared/schemas";
import { useFilters } from "@/shared/state/filters";
import { Card, CardContent } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

import { Provenance } from "./Provenance";

const BASE_KPIS = [
  "mean_travel_time",
  "mean_waiting_time",
  "person_weighted_delay",
  "co2_total_kg",
  "throughput_per_h",
  "stops_per_vehicle",
];
const SCENARIO_KPIS: Record<string, string[]> = {
  emergency: ["ev_delay", "ev_travel_time"],
  pedestrians: ["ped_mean_waiting_time", "ped_max_waiting_time"],
  buses: ["bus_delay"],
  incident: ["p95_waiting_time"],
};

export default function OverviewPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.overview.title"));
  const meta = useMeta();
  const summary = useSummary();
  const comparisons = useComparisons();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("pages.overview.title")} description={t("pages.overview.description")} />
      <QueryState query={meta} height={80}>
        {(m) => (
          <QueryState query={summary} height={400}>
            {(rows) => <Overview meta={m} rows={rows} comparisons={comparisons.data ?? []} />}
          </QueryState>
        )}
      </QueryState>
    </div>
  );
}

function Overview({
  meta,
  rows,
  comparisons,
}: {
  meta: Meta;
  rows: SummaryRow[];
  comparisons: Comparison[];
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const rtl = useRtl();
  const { cell, controller, reference, metric, setCell, setController, setReference, setMetric } =
    useFilters();
  const index = useMemo(() => indexSummary(rows), [rows]);
  const methods = sortMethods(index.methods(cell));
  const metrics = MAIN_METRICS.filter((m) => index.metrics(cell).includes(m));
  const kpis = [...BASE_KPIS, ...(SCENARIO_KPIS[cell.scenario] ?? [])].filter((m) =>
    index.metrics(cell).includes(m),
  );
  const headline = findComparison(comparisons, cell, controller, reference, "mean_waiting_time");

  return (
    <>
      <Card>
        <CardContent className="grid gap-4 pt-4 lg:grid-cols-[3fr_2fr]">
          <CellPicker meta={meta} value={cell} onChange={setCell} />
          <div className="grid grid-cols-2 gap-3">
            <MethodSelect
              label={t("filters.controller")}
              value={controller}
              methods={methods}
              onChange={setController}
            />
            <MethodSelect
              label={t("filters.reference")}
              value={reference}
              methods={methods}
              onChange={setReference}
            />
          </div>
        </CardContent>
      </Card>

      {headline?.pairedImprovementPct != null ? (
        <p className="text-lg font-medium text-balance text-text" aria-live="polite">
          {t(headline.pairedImprovementPct >= 0 ? "overview.headline" : "overview.headlineWorse", {
            controller: f.methodName(controller),
            reference: f.methodName(reference),
            metric: f.metricName("mean_waiting_time").toLowerCase(),
            value: f.pct(Math.abs(headline.pairedImprovementPct), 1, false),
          })}{" "}
          <span className="text-sm font-normal text-muted">({f.cellName(cell)})</span>
        </p>
      ) : null}

      <section aria-labelledby="kpi-title" className="flex flex-col gap-3">
        <h2 id="kpi-title" className="text-sm font-semibold text-text">
          {t("overview.kpis")} · {f.methodName(controller)}
        </h2>
        {methods.includes(controller) ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {kpis.map((m) => (
              <KpiCard
                key={m}
                metric={m}
                row={index.get(cell, controller, m)}
                referenceRow={index.get(cell, reference, m)}
                comparison={findComparison(comparisons, cell, controller, reference, m)}
                reference={reference}
              />
            ))}
          </div>
        ) : (
          <EmptyData />
        )}
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <ByController
          index={index}
          methods={methods}
          metric={metrics.includes(metric) ? metric : (metrics[0] ?? "mean_waiting_time")}
          metrics={metrics}
          onMetric={setMetric}
          rtl={rtl}
        />
        <OverTime methods={methods} rtl={rtl} />
      </div>

      <Provenance meta={meta} />
    </>
  );
}

function ByController({
  index,
  methods,
  metric,
  metrics,
  onMetric,
  rtl,
}: {
  index: ReturnType<typeof indexSummary>;
  methods: string[];
  metric: string;
  metrics: string[];
  onMetric: (m: string) => void;
  rtl: boolean;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const cell = useFilters((s) => s.cell);
  const data = methods
    .map((m) => ({ m, row: index.get(cell, m, metric) }))
    .filter((d) => d.row && d.row.mean !== null);

  const build = useCallback(
    (tokens: ChartTokens) =>
      barsWithCi(tokens, {
        categories: data.map((d) => f.methodName(d.m)),
        values: data.map((d) => f.metricValue(d.row?.mean, metric)),
        lo: data.map((d) => f.metricValue(d.row?.ciLo, metric)),
        hi: data.map((d) => f.metricValue(d.row?.ciHi, metric)),
        colors: data.map((d) => methodColor(d.m)),
        axisName: f.metricUnit(metric),
        format: (v) => `${f.number(v)} ${f.metricUnit(metric)}`,
        rtl,
      }),
    [data, f, metric, rtl],
  );

  return (
    <ChartCard
      title={t("overview.byController", { metric: f.metricName(metric) })}
      description={t("overview.byControllerText")}
      actions={
        <div className="w-48">
          <MetricSelect
            label={t("filters.metric")}
            value={metric}
            metrics={metrics}
            onChange={onMetric}
          />
        </div>
      }
      table={data.map((d) => ({
        [t("filters.controller")]: f.methodName(d.m),
        [f.metricTitle(metric)]: f.number(f.metricValue(d.row?.mean, metric)),
        [t("kpi.ci")]:
          `${f.number(f.metricValue(d.row?.ciLo, metric))} – ${f.number(f.metricValue(d.row?.ciHi, metric))}`,
        n: d.row?.n,
      }))}
      csvName={`${metric}.csv`}
    >
      {data.length ? (
        <EChart
          build={build}
          label={t("overview.byController", { metric: f.metricName(metric) })}
        />
      ) : (
        <EmptyData />
      )}
    </ChartCard>
  );
}

function OverTime({ methods, rtl }: { methods: string[]; rtl: boolean }) {
  const { t } = useTranslation();
  const cell = useFilters((s) => s.cell);
  const selected = useFilters((s) => s.controllers);
  const query = useTimeseries(cell);
  return (
    <ChartCard title={t("overview.overTime")} description={t("overview.overTimeText")}>
      <QueryState query={query} height={320}>
        {(ts) => (
          <OverTimeChart
            ts={ts}
            methods={methods.filter((m) => selected.includes(m) || methods.length <= 5)}
            rtl={rtl}
          />
        )}
      </QueryState>
    </ChartCard>
  );
}

function OverTimeChart({
  ts,
  methods,
  rtl,
}: {
  ts: TimeseriesCell;
  methods: string[];
  rtl: boolean;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const shown = methods.filter((m) => ts.methods[m]);
  const first = shown[0] ? ts.methods[shown[0]] : undefined;
  const build = useCallback(
    (tokens: ChartTokens) =>
      lines(tokens, {
        x: first?.minute ?? [],
        series: shown.map((m) => ({
          name: f.methodName(m),
          color: methodColor(m),
          data: ts.methods[m]?.halting ?? [],
        })),
        xName: t("overview.minute"),
        yName: t("overview.halting"),
        // evaluation protocol: 15 min warm-up, then the measured hour
        window: [15, 75],
        format: (v) => f.number(v, 0),
        rtl,
        dataZoom: true,
      }),
    [first, shown, ts, f, t, rtl],
  );
  if (!shown.length) return <EmptyData />;
  return <EChart build={build} height={320} label={t("overview.overTime")} />;
}
