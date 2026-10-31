import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { EChart } from "@/shared/charts/EChart";
import { baseAxes, escapeHtml, tooltipRow } from "@/shared/charts/style";
import type { ChartTokens } from "@/shared/charts/tokens";
import { ClaimsBlock, EvidenceBadge, PlainBox, SourceNote } from "@/shared/components/evidence";
import { Panel, Section } from "@/shared/components/section";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColor, methodLabel } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import type { Layers, Study, TestRow, Validation } from "@/shared/schemas/combined";
import { Segmented } from "@/shared/ui/segmented";

import { collapse } from "./forest";

type Metric = "travel" | "waiting";
/** the stronger bias tried on the validation seeds (H2 β = 8, rejected) */
const BETA_STRONG = 8;
const LAYERS = ["coop_full_evrule_switch", "hybrid_h2", "hybrid_h3"] as const;

export function AblationTab({
  layers,
  tests,
  validation,
  study,
}: {
  layers: Layers;
  tests: TestRow[];
  validation: Validation;
  study: Study;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const [metric, setMetric] = useState<Metric>("travel");
  const tx = useTx();
  const h2 = (cellNet: string, scen: string, dem: string) =>
    layers.cells
      .find((c) => c.network === cellNet && c.scenario === scen && c.demand === dem)
      ?.layers.find((l) => l.layer === "hybrid_h2")?.values;
  const pedPeak = h2("grid4x4", "pedestrians", "peak");
  const rankOf = (variant: string, value: number) =>
    validation.seeds.map(
      (s) => s.rows.find((r) => r.variant === variant && r.value === value)?.rank ?? null,
    );
  const beta8 = rankOf("hybrid_h2", BETA_STRONG);
  const beta4 = rankOf("hybrid_h2", study.candidate.beta);
  const list = (ranks: (number | null)[]) => ranks.map((r) => r ?? "–").join(", ");
  return (
    <div className="flex flex-col gap-10">
      <Section
        id="layers"
        title={t("final.ablation.layers.title")}
        description={t("final.ablation.layers.text")}
        badges={<EvidenceBadge kind="descriptive" />}
        actions={
          <Segmented
            label={t("final.filters.metric")}
            value={metric}
            onChange={setMetric}
            options={(["travel", "waiting"] as const).map((m) => ({
              value: m,
              label: tx(`final.metrics.${m}`),
            }))}
          />
        }
      >
        <Panel>
          <LayersChart layers={layers} metric={metric} />
        </Panel>
        {pedPeak ? (
          <PlainBox>
            {t("final.ablation.layers.plain", {
              travel: f.number(pedPeak.travel.gainVsCoopFull ?? 0, 1),
              waiting: f.number(pedPeak.waiting.gainVsCoopFull ?? 0, 1),
            })}
          </PlainBox>
        ) : null}
        <SourceNote source={layers.source} />
      </Section>

      <Section
        id="ablation-tests"
        title={t("final.ablation.tests.title")}
        description={t("final.ablation.tests.text")}
        badges={<EvidenceBadge kind="exploratory" />}
      >
        <Panel>
          <AblationFamily tests={tests} beta={study.candidate.beta} />
        </Panel>
        <SourceNote source="combined/tests.json · results/combined/analysis_tests.csv" />
      </Section>

      <Section
        id="validation"
        title={t("final.ablation.validation.title")}
        description={t("final.ablation.validation.text", {
          seeds: validation.seeds.map((s) => s.seed).join(", "),
          n: study.variantsTried,
        })}
        badges={<EvidenceBadge kind="validation" />}
      >
        <Panel className="p-0 md:p-0">
          <ValidationTable validation={validation} study={study} />
        </Panel>
        <ClaimsBlock
          can={[
            t("final.ablation.validation.can.choice", {
              ranks: list(beta4),
              beta: f.number(study.candidate.beta, 0),
            }),
            t("final.ablation.validation.can.beta8", {
              ranks: list(beta8),
              beta: f.number(BETA_STRONG, 0),
            }),
          ]}
          cannot={[
            t("final.ablation.validation.cannot.test"),
            t("final.ablation.validation.cannot.h3"),
          ]}
        />
        <SourceNote source={validation.source} />
      </Section>
    </div>
  );
}

const LAYER_SYMBOL: Record<(typeof LAYERS)[number], string> = {
  coop_full_evrule_switch: "rect",
  hybrid_h2: "circle",
  hybrid_h3: "emptyDiamond",
};

function layerColor(layer: string, tk: ChartTokens): string {
  if (layer === "hybrid_h2") return methodColor("hybrid_h2");
  if (layer === "hybrid_h3") return tk.text;
  return tk.muted;
}

/** Gain of each layer over COOP-FULL alone, per situation (no test: means of the episodes). */
function LayersChart({ layers, metric }: { layers: Layers; metric: Metric }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const names = layers.cells.map((c) => f.cellName(c));
  const byLayer = useMemo(
    () =>
      LAYERS.map((layer) =>
        layers.cells.map(
          (c) => c.layers.find((l) => l.layer === layer)?.values[metric].gainVsCoopFull ?? null,
        ),
      ),
    [layers, metric],
  );
  const all = byLayer.flat().filter((v): v is number => v !== null);
  const lo = Math.floor(Math.min(0, ...all) / 5) * 5;
  const hi = Math.ceil(Math.max(0, ...all) / 5) * 5;
  const build = useCallback(
    (tk: ChartTokens) => {
      const { axis, tooltip, legend } = baseAxes(tk);
      const signed = (v: number) => `${v > 0 ? "+" : ""}${f.number(v, 1)} %`;
      return {
        legend: {
          ...legend,
          top: 0,
          left: 0,
          // each layer's own mark shape in the legend
          data: LAYERS.map((l) => ({
            name: tx(`final.ablation.layerNames.${l}`),
            icon: LAYER_SYMBOL[l],
          })),
          itemWidth: 10,
          itemHeight: 10,
        },
        grid: { left: 8, right: 24, top: 36, bottom: 28, containLabel: true },
        tooltip: {
          ...tooltip,
          trigger: "axis",
          axisPointer: { type: "shadow", shadowStyle: { color: tk.surface2, opacity: 0.6 } },
          formatter: (ps: { dataIndex: number; seriesIndex: number }[]) => {
            const i = ps[0]?.dataIndex ?? 0;
            const cell = layers.cells[i];
            if (!cell) return "";
            const base = cell.layers.find((l) => l.layer === "coop_full")?.values[metric].mean;
            return [
              `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(names[i] ?? "")}</div>`,
              base !== undefined && base !== null
                ? tooltipRow(tk.muted, methodLabel("coop_full"), `${f.number(base, 1)} s`)
                : "",
              ...LAYERS.map((l) => {
                const v = cell.layers.find((x) => x.layer === l)?.values[metric];
                return v && v.gainVsCoopFull !== null && v.mean !== null
                  ? tooltipRow(
                      layerColor(l, tk),
                      tx(`final.ablation.layerNames.${l}`),
                      `${f.number(v.mean, 1)} s (${signed(v.gainVsCoopFull)})`,
                    )
                  : tooltipRow(
                      layerColor(l, tk),
                      tx(`final.ablation.layerNames.${l}`),
                      t("final.ablation.notPlayed"),
                    );
              }),
            ].join("");
          },
        },
        xAxis: {
          type: "value",
          min: lo,
          max: hi,
          name: t("final.ablation.layers.axis"),
          nameLocation: "middle",
          nameGap: 28,
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
        series: LAYERS.map((l, k) => ({
          name: tx(`final.ablation.layerNames.${l}`),
          type: "scatter",
          symbol: LAYER_SYMBOL[l],
          // H3 has the same episodes as the candidate in most situations: its hollow
          // diamond is drawn larger, around the candidate's dot, which stays on top
          symbolSize: l === "hybrid_h3" ? 15 : l === "hybrid_h2" ? 10 : 8,
          itemStyle: {
            color: layerColor(l, tk),
            borderColor: l === "hybrid_h3" ? layerColor(l, tk) : tk.surface,
            borderWidth: l === "hybrid_h3" ? 1.5 : 1,
          },
          data: byLayer[k]!.map((v, i) => (v === null ? null : [v, i])),
          z: l === "hybrid_h2" ? 6 : 3 + k,
          markLine:
            k === 0
              ? {
                  silent: true,
                  symbol: "none",
                  data: [{ xAxis: 0 }],
                  lineStyle: { color: tk.text2, type: "solid", width: 1 },
                  label: { show: false },
                }
              : undefined,
        })),
      };
    },
    [layers, metric, names, byLayer, lo, hi, f, t, tx],
  );
  return (
    <EChart
      build={build}
      height={names.length * 28 + 90}
      label={t("final.ablation.layers.alt", { metric: tx(`final.metrics.${metric}`) })}
    />
  );
}

const FAMILY_VARIANTS = [
  "hybrid_h2",
  "hybrid_h3",
  "hybrid_h1",
  "coop_full_evrule_switch",
  "coop_full_pedrule_switch",
] as const;
const KINDS = ["noninf", "loss", "wide"] as const;
const KIND_STYLE: Record<(typeof KINDS)[number], { bg: string; ink: string }> = {
  noninf: {
    bg: "color-mix(in srgb, var(--ctl-candidate) 45%, var(--surface))",
    ink: "var(--text)",
  },
  loss: { bg: "color-mix(in srgb, var(--critical) 55%, var(--surface))", ink: "var(--text)" },
  wide: { bg: "var(--surface-3)", ink: "var(--text)" },
};

/** Each final variant against the best reference: how many tests it passes. */
function AblationFamily({ tests, beta }: { tests: TestRow[]; beta: number }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const rows = FAMILY_VARIANTS.map((v) => {
    const own = tests.filter(
      (x) =>
        x.variant === v &&
        (v === "hybrid_h2" ? x.family === "hybrid" : x.family === "hybrid-ablation"),
    );
    const kind = (x: TestRow) => {
      const c = collapse(x.verdict);
      return c === "best" ? "noninf" : c;
    };
    return {
      variant: v,
      total: own.length,
      counts: Object.fromEntries(
        KINDS.map((k) => [k, own.filter((x) => kind(x) === k).length]),
      ) as Record<(typeof KINDS)[number], number>,
    };
  });
  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-2">
        {KINDS.map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2.5 rounded-[3px]"
              style={{ background: KIND_STYLE[k].bg }}
            />
            {tx(`final.ablation.kinds.${k}`)}
          </li>
        ))}
      </ul>
      <table className="w-full text-sm">
        <caption className="sr-only">{t("final.ablation.tests.caption")}</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">{t("final.ablation.variant")}</th>
            {KINDS.map((k) => (
              <th key={k} scope="col">
                {tx(`final.ablation.kinds.${k}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.variant} className="border-t border-border first:border-t-0">
              <th
                scope="row"
                className={cn(
                  "w-72 py-3 pe-3 text-start align-top",
                  r.variant === "hybrid_h2" ? "font-semibold text-text" : "font-normal text-text-2",
                )}
              >
                <span className="block">
                  {tx(`final.ablation.variants.${r.variant}.name`, { beta: f.number(beta, 0) })}
                </span>
                <span className="block text-xs font-normal text-muted">
                  {tx(`final.ablation.variants.${r.variant}.text`)} ·{" "}
                  {t("final.ablation.nTests", { n: r.total })}
                </span>
              </th>
              {KINDS.map((k) => (
                <td key={k} className="sr-only">
                  {r.counts[k]} / {r.total}
                </td>
              ))}
              <td aria-hidden="true" className="w-1/2 py-3">
                <span className="flex h-6 w-full overflow-hidden rounded-md bg-surface-2">
                  {KINDS.map((k) =>
                    r.counts[k] ? (
                      <span
                        key={k}
                        className="tabular flex h-6 items-center justify-center text-[11px] font-medium"
                        style={{
                          width: `${(100 * r.counts[k]) / r.total}%`,
                          background: KIND_STYLE[k].bg,
                          color: KIND_STYLE[k].ink,
                          borderInlineEnd: "2px solid var(--surface)",
                        }}
                      >
                        {r.counts[k]}
                      </span>
                    ) : null,
                  )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function variantName(
  row: Validation["seeds"][number]["rows"][number],
  tx: ReturnType<typeof useTx>,
  f: ReturnType<typeof useFormat>,
): string {
  if (row.param === "beta")
    return tx("final.ablation.names.beta", { value: f.number(row.value ?? 0, 0) });
  if (row.param === "q")
    return tx(`final.ablation.names.${row.variant}`, { value: f.number(row.value ?? 0, 0) });
  return tx(`final.ablation.names.${row.variant}`);
}

/** Every variant tried on the validation seeds, with its score per seed. */
function ValidationTable({ validation, study }: { validation: Validation; study: Study }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const first = validation.seeds[0]!;
  const key = (r: { variant: string; value: number | null }) => `${r.variant}:${r.value ?? ""}`;
  return (
    <div
      tabIndex={0}
      role="region"
      aria-label={t("ui.tableOf", { title: t("final.ablation.validation.title") })}
      className="overflow-x-auto"
    >
      <table className="w-full min-w-[720px] text-sm">
        <caption className="sr-only">{t("final.ablation.validation.caption")}</caption>
        <thead className="bg-surface-2 text-xs text-text-2">
          <tr>
            <th scope="col" className="px-4 py-2.5 text-start font-medium">
              {t("final.ablation.variant")}
            </th>
            {validation.seeds.map((s) => (
              <th key={s.seed} scope="col" className="px-4 py-2.5 text-start font-medium">
                {t("final.ablation.validation.seed", { seed: s.seed })}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {first.rows.map((row) => {
            const candidate = row.variant === "hybrid_h2" && row.value === study.candidate.beta;
            return (
              <tr
                key={key(row)}
                className={cn("border-t border-border", candidate && "bg-surface-2")}
              >
                <th
                  scope="row"
                  className={cn(
                    "px-4 py-2 text-start",
                    candidate ? "font-semibold text-text" : "font-normal text-text-2",
                  )}
                >
                  <span className="flex items-center gap-2">
                    {candidate ? (
                      <span
                        aria-hidden="true"
                        className="size-2.5 rounded-[3px]"
                        style={{ background: "var(--ctl-candidate)" }}
                      />
                    ) : null}
                    {variantName(row, tx, f)}
                    {candidate ? (
                      <span className="text-xs font-normal text-muted">
                        ({t("final.ablation.validation.chosen")})
                      </span>
                    ) : null}
                  </span>
                </th>
                {validation.seeds.map((s) => {
                  const r = s.rows.find((x) => key(x) === key(row));
                  return (
                    <td key={s.seed} className="px-4 py-2 text-text-2">
                      {r ? (
                        <span className="flex items-center gap-3">
                          <span className="w-8 font-medium text-text">#{r.rank}</span>
                          <span
                            title={t("final.ablation.validation.score", {
                              better: r.betterOrEqual,
                              uncertain: r.uncertain,
                              worse: r.worse,
                            })}
                          >
                            {t("final.ablation.validation.short", {
                              better: r.betterOrEqual,
                              uncertain: r.uncertain,
                              worse: r.worse,
                            })}
                          </span>
                        </span>
                      ) : (
                        <span className="text-muted">{t("final.ablation.validation.notRun")}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="px-4 py-3 text-xs text-muted">
        {t("final.ablation.validation.legend", { cells: first.rows[0]?.cells ?? 0 })}
      </p>
    </div>
  );
}
