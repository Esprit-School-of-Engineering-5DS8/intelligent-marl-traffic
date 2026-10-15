import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useComparisons, useMeta, useSummary } from "@/shared/api/queries";
import { barsWithCi, tradeoff } from "@/shared/charts/builders";
import { ChartCard } from "@/shared/charts/ChartCard";
import { EChart } from "@/shared/charts/EChart";
import type { ChartTokens } from "@/shared/charts/tokens";
import { compareCells } from "@/shared/domain/cells";
import { useFormat } from "@/shared/domain/format";
import { methodColor, sortMethods } from "@/shared/domain/methods";
import { findComparison, indexSummary } from "@/shared/domain/results";
import { useRtl } from "@/shared/lib/use-rtl";
import type { Cell, Comparison, Meta, SummaryRow } from "@/shared/schemas";
import { Card, CardContent } from "@/shared/ui/card";

import { KpiCard } from "./KpiCard";
import { CellPicker, MethodSelect, MetricSelect } from "./pickers";
import { EmptyData, QueryState } from "./QueryState";

export interface FocusConfig {
  scenario: string;
  kpis: string[];
  metrics: string[];
  tradeoff: { x: string; y: string; title: string; text: string };
  defaultController: string;
  defaultReference: string;
}

/**
 * The results of one kind of scenario (pedestrians, emergency vehicles): its KPIs for a
 * controller against a reference, a metric by controller, and a trade-off between two
 * metrics. `children` receives the selected cell for page-specific charts.
 */
export function ScenarioFocus({
  config,
  children,
}: {
  config: FocusConfig;
  children?: (cell: Cell) => ReactNode;
}) {
  const meta = useMeta();
  const summary = useSummary();
  const comparisons = useComparisons();
  return (
    <QueryState query={meta} height={80}>
      {(m) => (
        <QueryState query={summary} height={400}>
          {(rows) => (
            <Focus meta={m} rows={rows} comparisons={comparisons.data ?? []} config={config}>
              {children}
            </Focus>
          )}
        </QueryState>
      )}
    </QueryState>
  );
}

function Focus({
  meta,
  rows,
  comparisons,
  config,
  children,
}: {
  meta: Meta;
  rows: SummaryRow[];
  comparisons: Comparison[];
  config: FocusConfig;
  children?: (cell: Cell) => ReactNode;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const rtl = useRtl();
  const filter = useCallback((c: Cell) => c.scenario === config.scenario, [config.scenario]);
  const cells = meta.cells.filter(filter).sort(compareCells);
  const [cell, setCell] = useState<Cell | null>(
    cells.find((c) => c.demand === "peak") ?? cells[0] ?? null,
  );
  const [controller, setController] = useState(config.defaultController);
  const [reference, setReference] = useState(config.defaultReference);
  const [metric, setMetric] = useState(config.metrics[0] ?? "");
  const index = useMemo(() => indexSummary(rows), [rows]);

  if (!cell) return <EmptyData />;
  const methods = sortMethods(index.methods(cell));
  const available = index.metrics(cell);
  const metrics = config.metrics.filter((m) => available.includes(m));
  const current = metrics.includes(metric) ? metric : (metrics[0] ?? "");
  const kpis = config.kpis.filter((m) => available.includes(m));

  return (
    <>
      <Card>
        <CardContent className="grid gap-4 pt-4 lg:grid-cols-[3fr_2fr]">
          <CellPicker meta={meta} value={cell} onChange={setCell} filter={filter} />
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

      {kpis.length ? (
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
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <MetricBars
          index={index}
          cell={cell}
          methods={methods}
          metric={current}
          metrics={metrics}
          onMetric={setMetric}
          rtl={rtl}
        />
        <Tradeoff index={index} cell={cell} methods={methods} config={config} rtl={rtl} />
      </div>
      {children?.(cell)}
      <p className="text-xs text-muted">{f.cellName(cell)}</p>
    </>
  );
}

function MetricBars({
  index,
  cell,
  methods,
  metric,
  metrics,
  onMetric,
  rtl,
}: {
  index: ReturnType<typeof indexSummary>;
  cell: Cell;
  methods: string[];
  metric: string;
  metrics: string[];
  onMetric: (m: string) => void;
  rtl: boolean;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const data = methods
    .map((m) => ({ m, row: index.get(cell, m, metric) }))
    .filter((d) => d.row && d.row.mean !== null);
  const build = useCallback(
    (tk: ChartTokens) =>
      barsWithCi(tk, {
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
        <div className="w-52">
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
        n: d.row?.n,
      }))}
      csvName={`${metric}_${cell.network}_${cell.demand}.csv`}
    >
      {data.length ? (
        <EChart build={build} label={f.metricName(metric)} />
      ) : (
        <EmptyData title={t("data.pending")} text={t("data.pendingText")} />
      )}
    </ChartCard>
  );
}

function Tradeoff({
  index,
  cell,
  methods,
  config,
  rtl,
}: {
  index: ReturnType<typeof indexSummary>;
  cell: Cell;
  methods: string[];
  config: FocusConfig;
  rtl: boolean;
}) {
  const f = useFormat();
  const { x, y, title, text } = config.tradeoff;
  const points = methods
    .map((m) => ({ m, x: index.get(cell, m, x)?.mean, y: index.get(cell, m, y)?.mean }))
    .filter(
      (p): p is { m: string; x: number; y: number } =>
        typeof p.x === "number" && typeof p.y === "number",
    )
    .map((p) => ({
      label: f.methodName(p.m),
      x: f.metricValue(p.x, x) ?? p.x,
      y: f.metricValue(p.y, y) ?? p.y,
      color: methodColor(p.m),
    }));
  const build = useCallback(
    (tk: ChartTokens) =>
      tradeoff(tk, {
        points,
        xName: f.metricTitle(x),
        yName: f.metricTitle(y),
        format: (v) => f.number(v),
        rtl,
      }),
    [points, f, x, y, rtl],
  );
  return (
    <ChartCard title={title} description={text}>
      {points.length ? <EChart build={build} label={title} /> : <EmptyData />}
    </ChartCard>
  );
}
