import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { EChart } from "@/shared/charts/EChart";
import { baseAxes, escapeHtml, tooltipRow } from "@/shared/charts/style";
import type { ChartTokens } from "@/shared/charts/tokens";
import { VerdictBadge } from "@/shared/components/evidence";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodLabel } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import type { Cells, TestRow, TestVerdict } from "@/shared/schemas/combined";
import { Segmented } from "@/shared/ui/segmented";

import {
  collapse,
  forestRows,
  groupOf,
  VERDICT_ORDER,
  verdictColor,
  xBounds,
  type ForestFilters,
  type Group,
} from "./forest";

// one mark shape per verdict, so that the verdict never rests on colour alone
const CROSS = "path://M2,0L5,3L8,0L10,2L7,5L10,8L8,10L5,7L2,10L0,8L3,5L0,2Z";
const SYMBOL: Record<TestVerdict, string> = {
  best: "circle",
  noninf: "diamond",
  loss: CROSS,
  lossBeyond: CROSS,
  wide: "emptyCircle",
  notSup: "emptyCircle",
};

const GROUPS: Group[] = ["main", "district", "robustness", "generalisation"];

/** Filters shared by the forest plot and the final table. */
export function ForestControls({
  filters,
  tests,
  margin,
}: {
  filters: ForestFilters;
  tests: TestRow[];
  margin: number;
}) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const counts = (v: TestVerdict) =>
    tests.filter((x) => x.family === "hybrid" && collapse(x.verdict) === v).length;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <Segmented
          label={t("final.filters.network")}
          value={filters.network}
          onChange={filters.setNetwork}
          options={(["all", "grid4x4", "real_district", "grid8x8"] as const).map((n) => ({
            value: n,
            label: n === "all" ? t("final.filters.all") : f.networkName(n),
          }))}
        />
        <Segmented
          label={t("final.filters.metric")}
          value={filters.metric}
          onChange={filters.setMetric}
          options={(["all", "travel", "waiting"] as const).map((m) => ({
            value: m,
            label: m === "all" ? t("final.filters.all") : tx(`final.metrics.${m}`),
          }))}
        />
      </div>
      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-2">
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="h-3.5 w-0.5 rounded-full bg-critical" />
          {t("final.forest.margin", { margin: f.number(-margin, 0) })}
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="h-3.5 w-px bg-text-2" />
          {t("final.forest.zero")}
        </span>
      </p>
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">{t("final.filters.verdicts")}</legend>
        <span aria-hidden="true" className="text-xs font-medium text-muted">
          {t("final.filters.verdicts")}
        </span>
        {VERDICT_ORDER.map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={filters.verdicts.has(v)}
            onClick={() => filters.toggle(v)}
            className={cn(
              "rounded-md transition-opacity",
              filters.verdicts.has(v) ? "opacity-100" : "opacity-45 grayscale",
            )}
          >
            <VerdictBadge verdict={v} />
            <span className="sr-only"> ({counts(v)})</span>
          </button>
        ))}
      </fieldset>
    </div>
  );
}

/**
 * The 36 preregistered tests: one point (the gain) and its 95 % interval per comparison,
 * with 0 and the margin drawn; one small chart per group of situations, same x scale.
 */
export function ForestPlot({
  tests,
  cells,
  margin,
  filters,
}: {
  tests: TestRow[];
  cells: Cells["cells"];
  margin: number;
  filters: ForestFilters;
}) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const rows = useMemo(
    () =>
      forestRows(tests, cells, {
        network: filters.network,
        metric: filters.metric,
        verdicts: filters.verdicts,
      }),
    [tests, cells, filters.network, filters.metric, filters.verdicts],
  );
  const bounds = xBounds(rows, margin);
  const all = tests.filter((x) => x.family === "hybrid");
  const label = t("final.forest.alt", {
    total: all.length,
    best: all.filter((x) => x.verdict === "best").length,
    noninf: all.filter((x) => x.verdict === "noninf").length,
    loss: all.filter((x) => collapse(x.verdict) === "loss").length,
    wide: all.filter((x) => x.verdict === "wide").length,
  });

  if (!rows.length)
    return <p className="py-8 text-center text-sm text-muted">{t("final.forest.empty")}</p>;
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-5">
      {GROUPS.map((g) => {
        const part = rows.filter((r) => groupOf(r) === g);
        if (!part.length) return null;
        return (
          <div key={g} className="flex flex-col gap-1">
            <h3 className="eyebrow">{tx(`final.groups.${g}`)}</h3>
            <ForestGroup
              rows={part}
              bounds={bounds}
              margin={margin}
              label={t("final.forest.groupAlt", {
                group: tx(`final.groups.${g}`),
                n: part.length,
                best: part.filter((x) => x.verdict === "best").length,
                noninf: part.filter((x) => x.verdict === "noninf").length,
                loss: part.filter((x) => collapse(x.verdict) === "loss").length,
                wide: part.filter((x) => x.verdict === "wide").length,
              })}
            />
          </div>
        );
      })}
      <p className="text-xs text-muted">
        {t("final.forest.reading", { margin: f.number(-margin, 0) })}
      </p>
    </div>
  );
}

function ForestGroup({
  rows,
  bounds,
  margin,
  label,
}: {
  rows: TestRow[];
  bounds: [number, number];
  margin: number;
  label: string;
}) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const signed = useCallback((v: number) => `${v > 0 ? "+" : ""}${f.number(v, 1)} %`, [f]);
  const names = rows.map(
    (r) =>
      `${f.scenarioName(r.scenario)} · ${f.demandName(r.demand)} · ${tx(`final.metrics.${r.metric}`)}`,
  );

  const build = useCallback(
    (tk: ChartTokens) => {
      const { axis, tooltip } = baseAxes(tk);
      return {
        grid: { left: 8, right: 24, top: 8, bottom: 28, containLabel: true },
        tooltip: {
          ...tooltip,
          trigger: "item",
          formatter: (p: { dataIndex: number }) => {
            const r = rows[p.dataIndex];
            if (!r) return "";
            const c = verdictColor(r.verdict, tk);
            return [
              `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(f.cellName(r))}</div>`,
              `<div style="color:${tk.muted};margin-bottom:6px">${escapeHtml(
                tx(`final.metrics.${r.metric}`),
              )} · ${escapeHtml(t("final.forest.vs", { reference: methodLabel(r.reference) }))}</div>`,
              tooltipRow(c, t("final.forest.gain"), signed(r.gain)),
              tooltipRow(
                tk.muted,
                t("final.forest.interval"),
                `[${signed(r.low)} ; ${signed(r.high)}]`,
              ),
              r.variantMean !== null && r.referenceMean !== null
                ? tooltipRow(
                    tk.muted,
                    t("final.forest.means"),
                    `${f.number(r.variantMean, 1)} s / ${f.number(r.referenceMean, 1)} s`,
                  )
                : "",
              tooltipRow(tk.muted, t("final.forest.pHolm"), f.number(r.pHolm, 3)),
              r.pHolmSup !== undefined
                ? tooltipRow(tk.muted, t("final.forest.pHolmSup"), f.number(r.pHolmSup, 3))
                : "",
              `<div style="margin-top:6px;font-weight:600;color:${c}">${escapeHtml(
                tx(`ui.verdicts.${r.verdict}`),
              )}</div>`,
            ].join("");
          },
        },
        xAxis: {
          type: "value",
          min: bounds[0],
          max: bounds[1],
          interval: 10,
          ...axis,
          axisLabel: { ...axis.axisLabel, formatter: (v: number) => `${v} %` },
        },
        yAxis: {
          type: "category",
          inverse: true,
          data: names,
          ...axis,
          axisLine: { show: false },
          splitLine: { show: false },
          axisLabel: { ...axis.axisLabel, color: tk.text2, fontSize: 12 },
        },
        series: [
          {
            type: "custom",
            silent: true,
            encode: { x: [1, 2], y: 0 },
            renderItem: (
              _: unknown,
              api: {
                value: (i: number) => number;
                coord: (p: number[]) => number[];
                visual: (k: string) => string;
              },
            ) => {
              const y = api.value(0);
              const a = api.coord([api.value(1), y]);
              const b = api.coord([api.value(2), y]);
              return {
                type: "line",
                shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] },
                style: { stroke: api.visual("color"), lineWidth: 2.5, lineCap: "round" },
              };
            },
            data: rows.map((r, i) => ({
              value: [i, r.low, r.high],
              itemStyle: { color: verdictColor(r.verdict, tk), opacity: 0.55 },
            })),
            z: 2,
          },
          {
            type: "scatter",
            symbolSize: 11,
            data: rows.map((r, i) => ({
              value: [r.gain, i],
              symbol: SYMBOL[r.verdict],
              itemStyle: {
                color: verdictColor(r.verdict, tk),
                borderColor: tk.surface,
                borderWidth: r.verdict === "wide" ? 0 : 1.5,
              },
            })),
            emphasis: { scale: 1.5 },
            z: 3,
            markLine: {
              silent: true,
              symbol: "none",
              animation: false,
              data: [
                // named in the legend above the charts (labels here would cover the axis)
                {
                  xAxis: 0,
                  lineStyle: { color: tk.text2, width: 1, type: "solid" },
                  label: { show: false },
                },
                {
                  xAxis: -margin,
                  lineStyle: { color: tk.critical, width: 1.5, type: "solid" },
                  label: { show: false },
                },
              ],
            },
          },
        ],
      };
    },
    [rows, names, bounds, margin, f, t, tx, signed],
  );

  return <EChart build={build} height={rows.length * 30 + 44} label={label} />;
}
