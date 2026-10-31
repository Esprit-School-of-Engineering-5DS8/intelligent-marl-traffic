import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { EChart } from "@/shared/charts/EChart";
import { baseAxes, escapeHtml, tooltipRow } from "@/shared/charts/style";
import type { ChartTokens } from "@/shared/charts/tokens";
import { ControllerName } from "@/shared/components/controller";
import { VerdictBadge } from "@/shared/components/evidence";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColor, methodLabel } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import type { FinalController } from "@/shared/schemas";
import type { Bilan, TestRow } from "@/shared/schemas/combined";

import { forestRows, type ForestFilters } from "./forest";
import type { Cells } from "@/shared/schemas/combined";

const CRITERIA = ["travel", "waiting", "ambulances", "pedestrians", "sensors"] as const;
/** gaps at or above this share the darkest step (the cell still prints its value) */
const RAMP_CAP = 30;
const STEPS = 7;

/**
 * Gap of each controller to the best of the five, per criterion (smaller = better), and the
 * worst of its five gaps: an HTML table, read cell by cell by a screen reader.
 */
export function CompromiseMatrix({ final }: { final: FinalController }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const [hover, setHover] = useState<string | null>(null);
  const rows = [...final.compromise].sort((a, b) => a.worst - b.worst);
  const best = Object.fromEntries(
    [...CRITERIA, "worst" as const].map((c) => [c, Math.min(...rows.map((r) => r[c]))]),
  );
  const step = (v: number) => Math.round((Math.min(v, RAMP_CAP) / RAMP_CAP) * (STEPS - 1));
  const gap = (v: number) => `${v > 0 ? "+" : ""}${f.number(v, 1)} %`;
  return (
    <div
      tabIndex={0}
      role="region"
      aria-label={t("ui.tableOf", { title: t("final.compromise.title") })}
      className="overflow-x-auto"
    >
      <table className="w-full min-w-[640px] table-fixed border-separate border-spacing-1 text-sm">
        <caption className="sr-only">{t("final.compromise.caption")}</caption>
        <thead>
          <tr>
            <th scope="col" className="w-44 text-start text-xs font-medium text-muted">
              {t("final.compromise.controller")}
            </th>
            {CRITERIA.map((c) => (
              <th
                key={c}
                scope="col"
                className={cn(
                  "px-2 pb-1 text-center text-xs font-medium",
                  hover === c ? "text-text" : "text-muted",
                )}
              >
                {tx(`final.criteria.${c}`)}
              </th>
            ))}
            <th scope="col" className="ps-3 pb-1 text-center text-xs font-semibold text-text">
              {t("final.compromise.worst")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const candidate = r.controller === "hybrid_h2";
            return (
              <tr key={r.controller}>
                <th
                  scope="row"
                  className={cn(
                    "pe-2 text-start text-sm",
                    candidate ? "font-semibold text-text" : "font-normal text-text-2",
                  )}
                >
                  <ControllerName controller={r.controller} />
                </th>
                {CRITERIA.map((c) => {
                  const s = step(r[c]);
                  const isBest = r[c] === best[c];
                  return (
                    <td
                      key={c}
                      onMouseEnter={() => setHover(c)}
                      onMouseLeave={() => setHover(null)}
                      title={`${methodLabel(r.controller)} · ${tx(`final.criteria.${c}`)} : ${gap(r[c])}`}
                      className="tabular h-12 rounded-md text-center align-middle transition-[filter] hover:brightness-110"
                      style={{
                        background: `var(--seq-${s})`,
                        color: s >= 5 ? "var(--seq-ink-strong)" : "var(--seq-ink)",
                      }}
                    >
                      <span className={cn("block", isBest && "font-semibold")}>{gap(r[c])}</span>
                      {isBest ? (
                        <span className="block text-[10px] font-medium">
                          {t("final.compromise.best")}
                        </span>
                      ) : null}
                    </td>
                  );
                })}
                <td
                  className={cn(
                    "tabular h-12 rounded-md border bg-surface text-center align-middle",
                    r.worst === best.worst
                      ? "border-2 border-text font-semibold text-text"
                      : "border-border text-text-2",
                  )}
                >
                  <span className="block">{gap(r.worst)}</span>
                  {r.worst === best.worst ? (
                    <span className="block text-[10px] font-medium">
                      {t("final.compromise.smallest")}
                    </span>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div aria-hidden="true" className="mt-3 flex items-center gap-2 text-[11px] text-muted">
        <span>0 %</span>
        <span className="flex h-2 w-40 overflow-hidden rounded-full">
          {Array.from({ length: STEPS }, (_, i) => (
            <span key={i} className="h-2 flex-1" style={{ background: `var(--seq-${i})` }} />
          ))}
        </span>
        <span>≥ {RAMP_CAP} %</span>
        <span className="ms-2">{t("final.compromise.legend")}</span>
      </div>
    </div>
  );
}

/** Mean delay of the emergency vehicles, with its interval, one small chart per demand. */
export function AmbulanceChart({ final }: { final: FinalController }) {
  const { t } = useTranslation();
  const f = useFormat();
  const demands = ["medium", "peak"] as const;
  const max = Math.max(...final.ambulanceDelays.map((d) => d.high));
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {demands.map((demand) => (
        <AmbulanceDemand
          key={demand}
          rows={final.ambulanceDelays.filter((d) => d.demand === demand)}
          title={f.demandName(demand)}
          max={Math.ceil((max + 15) / 30) * 30}
          label={t("final.ambulances.alt", {
            demand: f.demandName(demand),
            items: final.ambulanceDelays
              .filter((d) => d.demand === demand)
              .map((d) => `${methodLabel(d.controller)} ${f.number(d.mean, 0)} s`)
              .join(", "),
          })}
        />
      ))}
    </div>
  );
}

function AmbulanceDemand({
  rows,
  title,
  max,
  label,
}: {
  rows: FinalController["ambulanceDelays"];
  title: string;
  max: number;
  label: string;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const ordered = [...rows].sort((a, b) => b.mean - a.mean);
  const build = useCallback(
    (tk: ChartTokens) => {
      const { axis, tooltip } = baseAxes(tk);
      return {
        grid: { left: 8, right: 48, top: 8, bottom: 28, containLabel: true },
        tooltip: {
          ...tooltip,
          trigger: "item",
          formatter: (p: { dataIndex: number }) => {
            const r = ordered[p.dataIndex];
            if (!r) return "";
            return [
              `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(methodLabel(r.controller))}</div>`,
              tooltipRow(
                methodColor(r.controller),
                t("final.ambulances.mean"),
                `${f.number(r.mean, 1)} s`,
              ),
              tooltipRow(
                tk.muted,
                t("final.forest.interval"),
                `[${f.number(r.low, 1)} ; ${f.number(r.high, 1)}] s`,
              ),
            ].join("");
          },
        },
        xAxis: {
          type: "value",
          min: 0,
          max,
          interval: 30,
          ...axis,
          axisLabel: { ...axis.axisLabel, formatter: (v: number) => `${v} s` },
        },
        yAxis: {
          type: "category",
          data: ordered.map((r) => methodLabel(r.controller)),
          ...axis,
          axisLine: { show: false },
          splitLine: { show: false },
          axisLabel: {
            ...axis.axisLabel,
            color: tk.text2,
            fontSize: 12,
            fontWeight: 400,
          },
        },
        series: [
          {
            type: "bar",
            barWidth: 14,
            data: ordered.map((r) => ({
              value: r.mean,
              itemStyle: { color: methodColor(r.controller), borderRadius: [0, 4, 4, 0] },
            })),
          },
          {
            type: "custom",
            silent: true,
            encode: { x: [1, 2], y: 0 },
            renderItem: (
              _: unknown,
              api: { value: (i: number) => number; coord: (p: number[]) => number[] },
            ) => {
              const y = api.value(0);
              const [ax = 0, ay = 0] = api.coord([api.value(1), y]);
              const [bx = 0, by = 0] = api.coord([api.value(2), y]);
              const a = [ax, ay] as const;
              const b = [bx, by] as const;
              return {
                type: "group",
                children: [
                  {
                    type: "line",
                    shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] },
                    style: { stroke: tk.text2, lineWidth: 1.5 },
                  },
                  {
                    type: "line",
                    shape: { x1: a[0], y1: a[1] - 4, x2: a[0], y2: a[1] + 4 },
                    style: { stroke: tk.text2, lineWidth: 1.5 },
                  },
                  {
                    type: "line",
                    shape: { x1: b[0], y1: b[1] - 4, x2: b[0], y2: b[1] + 4 },
                    style: { stroke: tk.text2, lineWidth: 1.5 },
                  },
                  // the mean, written after the interval so that nothing covers it
                  {
                    type: "text",
                    style: {
                      text: `${f.number(ordered[y]?.mean ?? 0, 0)} s`,
                      x: b[0] + 8,
                      y: b[1],
                      verticalAlign: "middle",
                      fill: tk.text,
                      font: `600 11px ${tk.font}`,
                    },
                  },
                ],
              };
            },
            data: ordered.map((r, i) => [i, r.low, r.high]),
            z: 3,
          },
        ],
      };
    },
    [ordered, max, f, t],
  );
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-sm font-semibold text-text">{title}</h3>
      <EChart build={build} height={ordered.length * 34 + 44} label={label} />
    </div>
  );
}

const BILAN_KEYS = ["better", "same", "worseSmall", "worseLarge"] as const;
// tints of the status colours, so that the counts printed on them stay legible (ink text)
const BILAN_STYLE: Record<(typeof BILAN_KEYS)[number], string> = {
  better: "color-mix(in srgb, var(--good) 45%, var(--surface))",
  same: "var(--surface-3)",
  worseSmall: "color-mix(in srgb, var(--critical) 25%, var(--surface))",
  worseLarge: "color-mix(in srgb, var(--critical) 60%, var(--surface))",
};

/** For each reference: on how many criteria the candidate is better, not different, worse. */
export function BilanBars({ bilan }: { bilan: Bilan }) {
  const { t } = useTranslation();
  const tx = useTx();
  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-2">
        {BILAN_KEYS.map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2.5 rounded-[3px]"
              style={{ background: BILAN_STYLE[k] }}
            />
            {tx(`final.bilan.${k}`)}
          </li>
        ))}
      </ul>
      <table className="w-full text-sm">
        <caption className="sr-only">{t("final.bilan.caption")}</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">{t("final.compromise.controller")}</th>
            <th scope="col">{t("final.bilan.split")}</th>
            {BILAN_KEYS.map((k) => (
              <th key={k} scope="col">
                {tx(`final.bilan.${k}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bilan.references.map((r) => (
            <tr key={r.reference} className="border-t border-border first:border-t-0">
              <th scope="row" className="w-56 py-2.5 pe-3 text-start font-normal">
                <ControllerName controller={r.reference} detail className="text-text" />
              </th>
              <td className="py-2.5" aria-hidden="true">
                <span className="flex h-6 w-full overflow-hidden rounded-md">
                  {BILAN_KEYS.map((k) =>
                    r[k] ? (
                      <span
                        key={k}
                        className="tabular flex h-6 items-center justify-center text-[11px] font-medium"
                        style={{
                          width: `${(100 * r[k]) / r.criteria}%`,
                          background: BILAN_STYLE[k],
                          color: "var(--text)",
                          borderInlineEnd: "2px solid var(--surface)",
                        }}
                      >
                        {r[k]}
                      </span>
                    ) : null,
                  )}
                </span>
              </td>
              {BILAN_KEYS.map((k) => (
                <td key={k} className="sr-only">
                  {r[k]} / {r.criteria}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The final table: every preregistered test, filtered like the forest plot. */
export function TestsTable({
  tests,
  cells,
  filters,
}: {
  tests: TestRow[];
  cells: Cells["cells"];
  filters: ForestFilters;
}) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const rows = forestRows(tests, cells, filters);
  const signed = (v: number) => `${v > 0 ? "+" : ""}${f.number(v, 1)} %`;
  return (
    <div
      tabIndex={0}
      role="region"
      aria-label={t("final.table.caption")}
      className="max-h-[560px] overflow-auto rounded-lg border border-border"
    >
      <table className="w-full min-w-[760px] text-sm">
        <caption className="sr-only">{t("final.table.caption")}</caption>
        <thead className="sticky top-0 z-10 bg-surface-2 text-xs text-text-2">
          <tr>
            {(
              ["situation", "metric", "reference", "gain", "interval", "pHolm", "verdict"] as const
            ).map((c) => (
              <th
                key={c}
                scope="col"
                className="px-3 py-2 text-start font-medium whitespace-nowrap"
              >
                {tx(`final.table.columns.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((r) => (
            <tr
              key={`${r.network}${r.scenario}${r.demand}${r.metric}`}
              className="border-t border-border hover:bg-surface-2"
            >
              <td className="px-3 py-2 text-text">{f.cellName(r)}</td>
              <td className="px-3 py-2 text-text-2">{tx(`final.metrics.${r.metric}`)}</td>
              <td className="px-3 py-2 text-text-2">
                <ControllerName controller={r.reference} />
              </td>
              <td className="px-3 py-2 font-medium text-text">{signed(r.gain)}</td>
              <td className="px-3 py-2 whitespace-nowrap text-text-2">
                [{signed(r.low)} ; {signed(r.high)}]
              </td>
              <td className="px-3 py-2 text-text-2">{f.number(r.pHolm, 3)}</td>
              <td className="px-3 py-2">
                <VerdictBadge verdict={r.verdict} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
