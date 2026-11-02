import { motion } from "motion/react";
import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useBigCity, useCities } from "@/shared/api/queries";
import { EChart } from "@/shared/charts/EChart";
import { baseAxes } from "@/shared/charts/style";
import type { ChartTokens } from "@/shared/charts/tokens";
import { ControllerName } from "@/shared/components/controller";
import { ClaimsBlock, EvidenceBadge, SourceNote } from "@/shared/components/evidence";
import { Details, PageHero } from "@/shared/components/page";
import { QueriesState } from "@/shared/components/QueriesState";
import { Panel, Section } from "@/shared/components/section";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColor, methodColorVar, methodLabel } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { BigCity, Cities } from "@/shared/schemas/combined";

type City = Cities["cities"][number];
const ORDER = ["ft", "mp", "coop_full", "hybrid_h2", "hybrid_h2_llmstrat"];

export default function CitiesPage() {
  const { t } = useTranslation();
  usePageTitle(t("nav.cities"));
  const queries = { city: useBigCity(), cities: useCities() };
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-10">
      <QueriesState queries={queries} height={480}>
        {({ city, cities }) => (
          <>
            <PageHero
              eyebrow={t("cities.eyebrow")}
              title={t("cities.title")}
              answer={t("cities.answer")}
              badges={<EvidenceBadge kind="exploratory" />}
            />
            {cities.cities.map((c) => (
              <CityCard key={c.network} city={c} />
            ))}
            <ClaimsBlock
              can={[t("cities.claims.can.transfer"), t("cities.claims.can.protocol")]}
              cannot={[
                t("cities.claims.cannot.prereg"),
                t("cities.claims.cannot.ft"),
                t("cities.claims.cannot.network"),
              ]}
            />
            <Details
              title={t("cities.history.title")}
              hint={t("cities.history.hint")}
              badges={<EvidenceBadge kind="stopped" />}
            >
              <BigCityCard city={city} />
            </Details>
            <SourceNote source={cities.source} />
          </>
        )}
      </QueriesState>
    </div>
  );
}

/** "x0,y0,x1,y1,..." as SVG points "x0,y0 x1,y1 ...". */
function points(flat: number[]): string {
  const out: string[] = [];
  for (let k = 0; k + 1 < flat.length; k += 2) out.push(`${flat[k]},${flat[k + 1]}`);
  return out.join(" ");
}

/** The street network, with the lights our agents drive and those SUMO keeps. */
function CityMap({ city }: { city: City }) {
  const { t } = useTranslation();
  const { width, height, edges, lights } = city.map;
  const pad = 40;
  return (
    <svg
      role="img"
      aria-label={t("cities.mapAlt", { lights: city.lights, driven: city.driven })}
      viewBox={`${-pad} ${-pad} ${width + 2 * pad} ${height + 2 * pad}`}
      className="h-auto w-full rounded-xl border border-border bg-surface-2"
    >
      {/* SUMO's y axis points north: flip it */}
      <g transform={`translate(0 ${height}) scale(1 -1)`}>
        {edges.map((e, i) => (
          <polyline
            key={i}
            points={points(e)}
            fill="none"
            stroke="var(--text-2)"
            strokeOpacity={0.55}
            strokeWidth={12}
            strokeLinecap="round"
          />
        ))}
        {lights.map((l, i) => (
          <motion.circle
            key={i}
            cx={l.x}
            cy={l.y}
            r={l.driven ? 22 : 16}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 + i * 0.01 }}
            fill={l.driven ? "var(--ctl-candidate)" : "var(--surface)"}
            stroke={l.driven ? "var(--surface)" : "var(--muted)"}
            strokeWidth={6}
          />
        ))}
      </g>
    </svg>
  );
}

function CityCard({ city }: { city: City }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const normal = ORDER.map((m) =>
    city.results.find((r) => r.controller === m && r.scenario === "normal"),
  ).filter((r): r is City["results"][number] => !!r && r.waiting !== null);
  const max = Math.max(1, ...normal.map((r) => r.waiting ?? 0));
  const by = (m: string) => normal.find((r) => r.controller === m);
  const best = [...normal].sort((a, b) => (a.waiting ?? 0) - (b.waiting ?? 0))[0];
  const cand = by("hybrid_h2");
  const llm = by("hybrid_h2_llmstrat");
  const mp = by("mp");
  return (
    <Section
      id={`city-${city.network}`}
      title={tx(`robustness.city.names.${city.network}`)}
      description={t("cities.facts", {
        lights: city.lights,
        driven: city.driven,
        pct: f.number(city.drivenLightsPct, 0),
        veh: city.vehPerH === null ? "–" : f.number(city.vehPerH, 0),
        scale: f.number(100 * city.scale, 0),
        seeds: city.seeds.length,
      })}
      badges={<EvidenceBadge kind="exploratory" />}
      className="rounded-2xl border border-border bg-surface p-5 md:p-6"
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:items-start">
        <div className="flex flex-col gap-2">
          <CityMap city={city} />
          <p className="flex flex-wrap gap-4 text-xs text-text-2">
            <span className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="size-2.5 rounded-full"
                style={{ background: "var(--ctl-candidate)" }}
              />
              {t("cities.legend.driven")}
            </span>
            <span className="flex items-center gap-1.5">
              <span aria-hidden="true" className="size-2.5 rounded-full border border-muted" />
              {t("cities.legend.kept")}
            </span>
          </p>
        </div>
        <div className="flex flex-col gap-4">
          {best && cand && mp ? (
            <p className="text-lg leading-snug font-semibold text-text">
              {t("cities.verdict", {
                best: methodLabel(best.controller),
                cand: f.number(cand.waiting ?? 0, 0),
                mp: f.number(mp.waiting ?? 0, 0),
                ft: f.number(by("ft")?.waiting ?? 0, 0),
                llm: llm ? f.number(llm.waiting ?? 0, 0) : "–",
              })}
            </p>
          ) : (
            <p className="text-sm text-muted">{t("cities.pending")}</p>
          )}
          <ul className="flex flex-col gap-2.5" aria-label={t("cities.barsAlt")}>
            {normal.map((r) => (
              <li
                key={r.controller}
                className="grid grid-cols-[10.5rem_1fr_7.5rem] items-center gap-3 text-sm"
              >
                <ControllerName controller={r.controller} className="truncate text-text-2" />
                <span className="h-3 rounded-full bg-surface-3">
                  <motion.span
                    initial={{ width: 0 }}
                    animate={{ width: `${(100 * (r.waiting ?? 0)) / max}%` }}
                    transition={{ duration: 0.8 }}
                    className="block h-3 rounded-full"
                    style={{ background: methodColorVar(r.controller) }}
                  />
                </span>
                <span className="tabular text-end text-text">
                  {f.number(r.waiting ?? 0, 0)} s
                  <span className="block text-[11px] text-muted">
                    {t("cities.teleports", { n: f.number(r.teleports ?? 0, 0) })}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">{t("cities.barsNote")}</p>
          {city.llmShares ? (
            <p className="text-sm text-text-2">
              {t("cities.llm", {
                equilibre: f.number(100 * (city.llmShares.equilibre ?? 0), 0),
                fluidite: f.number(100 * (city.llmShares.fluidite ?? 0), 0),
                agent: f.number(100 * (city.llmShares.agent ?? 0), 0),
              })}
            </p>
          ) : null}
        </div>
      </div>
    </Section>
  );
}

/** F-016: the large-city attempts, stopped before any test seed. */
function BigCityCard({ city }: { city: BigCity }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const sweep = city.parisSweep;
  const controllers = useMemo(() => [...new Set(sweep.map((r) => r.controller))], [sweep]);
  const demands = useMemo(
    () => [...new Set(sweep.map((r) => r.vehPerH))].sort((a, b) => a - b),
    [sweep],
  );
  const build = useCallback(
    (tk: ChartTokens) => {
      const { axis, tooltip, legend } = baseAxes(tk);
      return {
        legend: { ...legend, top: 0, right: 0 },
        grid: { left: 8, right: 64, top: 44, bottom: 36, containLabel: true },
        tooltip: { ...tooltip, trigger: "axis" },
        xAxis: {
          type: "category",
          data: demands.map((d) => f.number(d, 0)),
          name: t("robustness.city.axisX"),
          nameLocation: "middle",
          nameGap: 26,
          ...axis,
        },
        yAxis: {
          type: "value",
          min: 0,
          name: t("robustness.city.axisY"),
          ...axis,
          nameTextStyle: { ...axis.nameTextStyle, align: "left" },
          axisLabel: { ...axis.axisLabel, formatter: (v: number) => f.number(v, 0) },
        },
        series: controllers.map((c) => ({
          name: methodLabel(c),
          type: "line",
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2, color: methodColor(c) },
          itemStyle: { color: methodColor(c), borderColor: tk.surface, borderWidth: 2 },
          data: demands.map(
            (d) => sweep.find((r) => r.controller === c && r.vehPerH === d)?.waiting ?? null,
          ),
          endLabel: {
            show: true,
            formatter: methodLabel(c),
            color: tk.text2,
            fontSize: 11,
          },
        })),
      };
    },
    [sweep, controllers, demands, f, t],
  );
  return (
    <Section
      id="big-city"
      title={t("robustness.city.title")}
      description={t("robustness.city.text", { seed: city.seed })}
      badges={
        <>
          <EvidenceBadge kind="stopped" />
          <EvidenceBadge kind="validation" />
        </>
      }
      className="rounded-2xl border border-dashed border-border-strong bg-surface p-5 md:p-6"
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <ul className="flex flex-col gap-3">
          {city.cities.map((c) => (
            <li key={c.network} className="rounded-lg border border-border bg-surface-2 p-4">
              <p className="text-sm font-semibold text-text">
                {tx(`robustness.city.names.${c.network}`)}
              </p>
              <p className="mt-1 text-sm text-text-2">
                {t("robustness.city.lights", {
                  lights: c.lights,
                  driven: c.driven,
                  pctLights: f.number(c.drivenLightsPct, 0),
                  pctLanes: f.number(c.drivenLanesPct, 0),
                })}
              </p>
              <p className="mt-2 text-sm text-text-2">
                {tx(`robustness.city.verdicts.${c.network}`)}
              </p>
            </li>
          ))}
        </ul>
        <Panel>
          <EChart
            build={build}
            height={280}
            label={t("robustness.city.alt", {
              items: controllers
                .map(
                  (c) =>
                    `${methodLabel(c)} : ${sweep
                      .filter((r) => r.controller === c)
                      .map((r) => `${f.number(r.waiting, 0)} s`)
                      .join(", ")}`,
                )
                .join(" ; "),
            })}
          />
          <p className="mt-2 text-xs text-muted">{t("robustness.city.chartNote")}</p>
        </Panel>
      </div>
      <ClaimsBlock
        can={[t("robustness.city.can")]}
        cannot={[t("robustness.city.cannot.result"), t("robustness.city.cannot.why")]}
      />
      <p className="text-sm text-text-2">
        {t("robustness.city.more")} <code className="font-mono text-xs">docs/FAILURES.md</code>{" "}
        (F-016).
      </p>
      <SourceNote source={city.source} />
    </Section>
  );
}
