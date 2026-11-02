import { ArrowRight, Bus, Cpu, Network, RadioTower, type LucideIcon } from "lucide-react";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { findTest } from "@/features/combined/claims";
import { useCells, useStudy, useTests } from "@/shared/api/queries";
import { EChart } from "@/shared/charts/EChart";
import { baseAxes, escapeHtml, tooltipRow } from "@/shared/charts/style";
import type { ChartTokens } from "@/shared/charts/tokens";
import {
  ClaimsBlock,
  EvidenceBadge,
  PlainBox,
  SourceNote,
  VerdictBadge,
} from "@/shared/components/evidence";
import { QueriesState } from "@/shared/components/QueriesState";
import { Details } from "@/shared/components/page";
import { Section } from "@/shared/components/section";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColor, methodLabel } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { Cells, Study, TestRow } from "@/shared/schemas/combined";

interface Situation {
  key: "sensors" | "dropout" | "buses" | "generalisation";
  network: string;
  scenario: string;
  demand: string;
  icon: LucideIcon;
}

/** The four preregistered robustness and generalisation situations (frozen plan). */
const SITUATIONS: Situation[] = [
  { key: "sensors", network: "grid4x4", scenario: "sensor_noise", demand: "peak", icon: Cpu },
  {
    key: "dropout",
    network: "grid4x4",
    scenario: "comm_dropout_30",
    demand: "peak",
    icon: RadioTower,
  },
  { key: "buses", network: "grid4x4", scenario: "buses", demand: "medium", icon: Bus },
  { key: "generalisation", network: "grid8x8", scenario: "normal", demand: "peak", icon: Network },
];
const SHOWN = ["hybrid_h2", "mp", "coop_full", "ev_rule_mp", "team_rules"];

export default function RobustnessPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.robustness.title"));
  const queries = { study: useStudy(), cells: useCells(), tests: useTests() };
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-8">
      <header className="flex flex-col gap-3">
        <p className="eyebrow">{t("robustness.eyebrow")}</p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance text-text md:text-4xl">
          {t("pages.robustness.title")}
        </h1>
        <p className="max-w-3xl text-base leading-relaxed text-text-2">{t("robustness.lead")}</p>
        <Link
          to="/final-controller"
          className="flex w-fit items-center gap-1.5 text-sm font-medium text-text underline-offset-4 hover:underline"
        >
          {t("robustness.allTests")}
          <ArrowRight aria-hidden="true" className="size-4 rtl:-scale-x-100" />
        </Link>
      </header>
      <QueriesState queries={queries} height={480}>
        {({ study, cells, tests }) => (
          <>
            <div className="grid gap-6 xl:grid-cols-2">
              {SITUATIONS.map((s) => (
                <SituationCard
                  key={s.key}
                  situation={s}
                  study={study}
                  cells={cells}
                  tests={tests.tests}
                />
              ))}
            </div>
            <Summary study={study} tests={tests.tests} />
            <SourceNote
              source={`${cells.source} · combined/tests.json`}
              extra={t("final.prereg", { commit: study.prereg })}
            />
          </>
        )}
      </QueriesState>
    </div>
  );
}

function situationValues(study: Study, s: Situation, f: ReturnType<typeof useFormat>) {
  const p = study.perturbations;
  const gen = p.generalisation[s.network];
  return {
    std: f.number(p.sensorNoise.countStdVeh, 0),
    failed: p.sensorNoise.failedPct,
    loss: p.commDropout.lossPct,
    period: p.buses.periodMin,
    lights: gen?.lights ?? 0,
    trainedOn: gen ? f.networkName(gen.trainedOn) : "",
    trainedLights: gen?.trainedLights ?? 0,
  };
}

function SituationCard({
  situation: s,
  study,
  cells,
  tests,
}: {
  situation: Situation;
  study: Study;
  cells: Cells;
  tests: TestRow[];
}) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const cell = cells.cells.find(
    (c) => c.network === s.network && c.scenario === s.scenario && c.demand === s.demand,
  );
  const values = situationValues(study, s, f);
  const Icon = s.icon;
  if (!cell) return null;
  const played = cell.controllers.filter((c) => SHOWN.includes(c.controller) && !c.sameAs);
  const same = cell.controllers.filter((c) => SHOWN.includes(c.controller) && c.sameAs);
  const signed = (v: number) => `${v > 0 ? "+" : ""}${f.number(v, 1)} %`;
  return (
    <Section
      id={`situation-${s.key}`}
      title={tx(`robustness.situations.${s.key}.title`, values)}
      description={f.cellName(cell)}
      badges={<EvidenceBadge kind="prereg" />}
      className="rounded-2xl border border-border bg-surface p-5 md:p-6"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-border-strong bg-surface-2">
          <Icon aria-hidden="true" className="size-5 text-text" />
        </span>
        <p className="text-sm leading-relaxed text-text-2">
          {tx(`robustness.situations.${s.key}.what`, values)}
        </p>
      </div>
      <ul className="grid gap-2 sm:grid-cols-2">
        {(["travel", "waiting"] as const).map((m) => {
          const test = findTest(tests, s.network, s.scenario, s.demand, m);
          if (!test) return null;
          return (
            <li
              key={m}
              className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface-2 p-3"
            >
              <span className="text-xs text-muted">
                {tx(`final.criteria.${m}`)} ·{" "}
                {t("final.forest.vs", { reference: methodLabel(test.reference) })}
              </span>
              <span className="flex flex-wrap items-center gap-2">
                <span className="tabular text-xl font-semibold text-text">{signed(test.gain)}</span>
                <VerdictBadge verdict={test.verdict} />
              </span>
              <span className="tabular text-xs text-text-2">
                {t("robustness.interval", { low: signed(test.low), high: signed(test.high) })}
              </span>
            </li>
          );
        })}
      </ul>
      <Details title={t("robustness.means")} hint={t("robustness.meansHint")}>
        <div className="grid gap-3">
          {(["travel", "waiting"] as const).map((m) => (
            <MeansChart key={m} controllers={played} metric={m} title={tx(`final.criteria.${m}`)} />
          ))}
        </div>
      </Details>
      {same.length ? (
        <p className="text-xs text-muted">
          {t("robustness.same", {
            list: same.map((c) => methodLabel(c.controller)).join(", "),
            as: methodLabel(same[0]!.sameAs ?? ""),
          })}
        </p>
      ) : null}
      <PlainBox>{tx(`robustness.situations.${s.key}.plain`, values)}</PlainBox>
    </Section>
  );
}

/** Mean of each controller with its interval, bars from zero (small gaps look small). */
function MeansChart({
  controllers,
  metric,
  title,
}: {
  controllers: Cells["cells"][number]["controllers"];
  metric: "travel" | "waiting";
  title: string;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const rows = controllers
    .map((c) => ({ controller: c.controller, v: c.values[metric] }))
    .filter(
      (r): r is { controller: string; v: NonNullable<typeof r.v> } => !!r.v && r.v.mean !== null,
    );
  const max = Math.max(...rows.map((r) => r.v.high ?? r.v.mean ?? 0));
  const build = useCallback(
    (tk: ChartTokens) => {
      const { axis, tooltip } = baseAxes(tk);
      return {
        grid: { left: 4, right: 52, top: 4, bottom: 22, containLabel: true },
        tooltip: {
          ...tooltip,
          trigger: "item",
          formatter: (p: { dataIndex: number }) => {
            const r = rows[p.dataIndex];
            if (!r) return "";
            return [
              `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(methodLabel(r.controller))}</div>`,
              tooltipRow(
                methodColor(r.controller),
                t("robustness.mean"),
                `${f.number(r.v.mean, 1)} s`,
              ),
              tooltipRow(
                tk.muted,
                t("final.forest.interval"),
                `[${f.number(r.v.low, 1)} ; ${f.number(r.v.high, 1)}] s`,
              ),
              tooltipRow(tk.muted, t("robustness.episodes"), String(r.v.n)),
            ].join("");
          },
        },
        xAxis: {
          type: "value",
          min: 0,
          max: Math.ceil(max / 50) * 50,
          splitNumber: 4,
          ...axis,
          axisLabel: {
            ...axis.axisLabel,
            hideOverlap: true,
            formatter: (v: number) => `${f.number(v, 0)} s`,
          },
        },
        yAxis: {
          type: "category",
          inverse: true,
          data: rows.map((r) => methodLabel(r.controller)),
          ...axis,
          axisLine: { show: false },
          splitLine: { show: false },
          axisLabel: { ...axis.axisLabel, color: tk.text2, fontSize: 11 },
        },
        series: [
          {
            type: "bar",
            barWidth: 12,
            data: rows.map((r) => ({
              value: r.v.mean,
              itemStyle: { color: methodColor(r.controller), borderRadius: [0, 4, 4, 0] },
            })),
            label: {
              show: true,
              position: "right",
              color: tk.text,
              fontSize: 11,
              formatter: (p: { value: number }) => `${f.number(p.value, 1)} s`,
            },
          },
        ],
      };
    },
    [rows, max, f, t],
  );
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-xs font-medium text-text-2">{title}</h3>
      <EChart
        build={build}
        height={rows.length * 30 + 30}
        label={t("robustness.alt", {
          metric: title,
          items: rows
            .map((r) => `${methodLabel(r.controller)} ${f.number(r.v.mean, 1)} s`)
            .join(", "),
        })}
      />
    </div>
  );
}

function Summary({ study, tests }: { study: Study; tests: TestRow[] }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const all = SITUATIONS.flatMap((s) =>
    (["travel", "waiting"] as const)
      .map((m) => ({ s, m, test: findTest(tests, s.network, s.scenario, s.demand, m) }))
      .filter((x): x is { s: Situation; m: "travel" | "waiting"; test: TestRow } => !!x.test),
  );
  const values = (s: Situation) => situationValues(study, s, f);
  const line = (x: (typeof all)[number]) =>
    t("robustness.claim", {
      situation: tx(`robustness.situations.${x.s.key}.title`, values(x.s)),
      metric: tx(`final.metrics.${x.m}`),
      gain: `${x.test.gain > 0 ? "+" : ""}${f.number(x.test.gain, 1)} %`,
      verdict: tx(`ui.verdicts.${x.test.verdict}`).toLocaleLowerCase(f.locale),
    });
  const proven = all.filter((x) => x.test.verdict === "best" || x.test.verdict === "noninf");
  const not = all.filter((x) => !(x.test.verdict === "best" || x.test.verdict === "noninf"));
  return (
    <Section
      id="robustness-claims"
      title={t("robustness.claimsTitle")}
      badges={<EvidenceBadge kind="prereg" />}
    >
      <ClaimsBlock can={proven.map(line)} cannot={not.map(line)} />
    </Section>
  );
}
