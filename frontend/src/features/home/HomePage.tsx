import {
  ArrowRight,
  Ambulance,
  BrainCircuit,
  Gauge,
  MapPinned,
  Scale,
  ShieldCheck,
  ShieldHalf,
  TrafficCone,
  type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ambulanceDelay, findTest, summarize } from "@/features/combined/claims";
import { useFinalController, useStudy, useTests } from "@/shared/api/queries";
import { ControllerName } from "@/shared/components/controller";
import {
  ClaimsBlock,
  EvidenceBadge,
  PlainBox,
  SourceNote,
  VerdictBadge,
} from "@/shared/components/evidence";
import { QueriesState } from "@/shared/components/QueriesState";
import { Section } from "@/shared/components/section";
import { AnimatedNumber, StatTile } from "@/shared/components/stat";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColorVar } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { FinalController } from "@/shared/schemas";
import type { Study, TestRow } from "@/shared/schemas/combined";
import { Button } from "@/shared/ui/button";
import { Kbd } from "@/shared/ui/kbd";

export default function HomePage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.home.title"));
  const queries = { final: useFinalController(), study: useStudy(), tests: useTests() };
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-10">
      <QueriesState queries={queries} height={520}>
        {({ final, study, tests }) => (
          <>
            <Hero study={study} />
            <KeyNumbers final={final} study={study} tests={tests.tests} />
            <Architecture study={study} />
            <Claims final={final} study={study} tests={tests.tests} />
            <Explore />
          </>
        )}
      </QueriesState>
    </div>
  );
}

function Hero({ study }: { study: Study }) {
  const { t } = useTranslation();
  const f = useFormat();
  const seeds = study.testSeeds;
  const facts: [LucideIcon, string][] = [
    [ShieldCheck, t("home.rigour.prereg", { commit: study.prereg })],
    [
      Gauge,
      t("home.rigour.episodes", {
        n: f.number(study.episodes, 0),
        minutes: study.episodeMinutes,
      }),
    ],
    [TrafficCone, t("home.rigour.seeds", { first: seeds[0], last: seeds[seeds.length - 1] })],
    [BrainCircuit, t("home.rigour.models", { n: study.models })],
    [
      Scale,
      t("home.rigour.tests", {
        n: study.tests,
        margin: f.number(study.marginPct, 0),
      }),
    ],
    [ShieldHalf, t("home.rigour.variants", { n: study.variantsTried })],
  ];
  return (
    <header className="relative overflow-hidden rounded-2xl border border-border bg-surface">
      <div aria-hidden="true" className="bg-grid absolute inset-0 opacity-60" />
      <div aria-hidden="true" className="bg-glow absolute inset-0" />
      <div className="relative flex flex-col gap-6 px-6 py-10 md:px-12 md:py-14">
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5 }}
          className="eyebrow"
        >
          {t("home.eyebrow")}
        </motion.p>
        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-4xl text-4xl font-semibold tracking-tight text-balance text-text md:text-6xl"
        >
          {t("home.title")}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-3xl text-base leading-relaxed text-text-2 md:text-lg"
        >
          {t("home.lead", { beta: f.number(study.candidate.beta, 0) })}
        </motion.p>
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild variant="primary" size="md" className="h-10 px-5">
            <Link to="/final-controller">
              {t("home.cta.results")}
              <ArrowRight aria-hidden="true" className="rtl:-scale-x-100" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="md" className="h-10 px-5">
            <Link to="/robustness">{t("home.cta.robustness")}</Link>
          </Button>
          <span className="flex items-center gap-2 text-xs text-muted">
            <Kbd>Ctrl K</Kbd> {t("home.cta.palette")}
          </span>
        </div>
        <ul
          aria-label={t("home.rigour.label")}
          className="mt-2 grid gap-x-6 gap-y-3 border-t border-border pt-6 sm:grid-cols-2 lg:grid-cols-3"
        >
          {facts.map(([Icon, text]) => (
            <li key={text} className="flex items-start gap-2.5 text-sm text-text-2">
              <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-text" />
              {text}
            </li>
          ))}
        </ul>
      </div>
    </header>
  );
}

function KeyNumbers({
  final,
  study,
  tests,
}: {
  final: FinalController;
  study: Study;
  tests: TestRow[];
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const pct = (v: number) => `${f.number(v, 1)} %`;
  const peak = final.ambulances.peak;
  const sensors = findTest(tests, "grid4x4", "sensor_noise", "peak", "waiting");
  return (
    <Section id="key-numbers" title={t("home.numbers.title")} description={t("home.numbers.text")}>
      <div className="grid gap-4 lg:grid-cols-3">
        <StatTile
          label={t("home.numbers.worst.label")}
          accent={methodColorVar("hybrid_h2")}
          value={<AnimatedNumber value={final.worstGap.candidate} format={pct} />}
          badges={<EvidenceBadge kind="descriptive" />}
          context={t("home.numbers.worst.context", {
            min: pct(final.worstGap.othersMin),
            max: pct(final.worstGap.othersMax),
          })}
          footer={<WorstGapBars final={final} />}
        />
        <StatTile
          label={t("home.numbers.ambulances.label")}
          accent={methodColorVar("hybrid_h2")}
          value={
            <>
              <AnimatedNumber value={peak.faster} format={(v) => f.number(Math.round(v), 0)} />{" "}
              <span className="text-2xl font-medium text-text-2">/ {peak.total}</span>
            </>
          }
          badges={<EvidenceBadge kind="secondary" />}
          context={t("home.numbers.ambulances.context", {
            models: study.models,
            perModel: f.number(peak.total / study.models, 0),
            gain: f.number(peak.medianGainS, 0),
          })}
          footer={<TripDots faster={peak.faster} total={peak.total} rows={study.models} />}
        />
        {sensors ? (
          <StatTile
            label={t("home.numbers.sensors.label")}
            accent={methodColorVar("hybrid_h2")}
            value={
              <AnimatedNumber
                value={sensors.gain}
                format={(v) => `${v > 0 ? "+" : ""}${f.number(v, 1)} %`}
              />
            }
            badges={
              <>
                <EvidenceBadge kind="prereg" />
                <VerdictBadge verdict={sensors.verdict} />
              </>
            }
            context={t("home.numbers.sensors.context", {
              low: f.pct(sensors.low),
              high: f.pct(sensors.high),
              reference: f.methodName(sensors.reference),
            })}
            footer={<IntervalLine test={sensors} margin={study.marginPct} />}
          />
        ) : null}
      </div>
      <SourceNote
        source={`frontend/public/data/final_controller.json · combined/tests.json`}
        extra={t("home.numbers.source", { commit: study.prereg })}
      />
    </Section>
  );
}

/** The worst gap of every controller, from zero: the candidate's is the shortest bar. */
function WorstGapBars({ final }: { final: FinalController }) {
  const f = useFormat();
  const rows = [...final.compromise].sort((a, b) => a.worst - b.worst);
  const max = Math.max(...rows.map((r) => r.worst));
  return (
    <ul className="flex flex-col gap-1.5 text-xs">
      {rows.map((r) => (
        <li key={r.controller} className="grid grid-cols-[9.5rem_1fr_3.5rem] items-center gap-2">
          <ControllerName controller={r.controller} className="truncate text-text-2" />
          <span className="h-2 rounded-full bg-surface-3">
            <motion.span
              initial={{ width: 0 }}
              animate={{ width: `${(100 * r.worst) / max}%` }}
              transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
              className="block h-2 rounded-full"
              style={{ background: methodColorVar(r.controller) }}
            />
          </span>
          <span className="tabular text-end text-text">{f.number(r.worst, 1)} %</span>
        </li>
      ))}
    </ul>
  );
}

/** One square per ambulance trip (one row per trained model): filled = faster than MP. */
function TripDots({ faster, total, rows }: { faster: number; total: number; rows: number }) {
  const perRow = Math.ceil(total / rows);
  return (
    <div
      aria-hidden="true"
      className="grid gap-1"
      style={{ gridTemplateColumns: `repeat(${perRow}, minmax(0, 1fr))` }}
    >
      {Array.from({ length: total }, (_, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, scale: 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.15 + i * 0.012, duration: 0.25 }}
          className="aspect-square rounded-[2px] border"
          style={
            i < faster
              ? { background: methodColorVar("hybrid_h2"), borderColor: "transparent" }
              : { borderColor: "var(--muted)" }
          }
        />
      ))}
    </div>
  );
}

/** The 95 % interval of a gain on a line that shows 0 and the -2 % margin. */
function IntervalLine({ test, margin }: { test: TestRow; margin: number }) {
  const { t } = useTranslation();
  const f = useFormat();
  const lo = Math.min(test.low, -margin) - 2;
  const hi = Math.max(test.high, 0) + 2;
  const x = (v: number) => `${(100 * (v - lo)) / (hi - lo)}%`;
  const colour = test.verdict === "best" ? "var(--good)" : "var(--ctl-candidate)";
  return (
    <div aria-hidden="true" className="relative h-10 text-[10px] text-muted">
      <span className="absolute inset-x-0 top-4 h-px bg-border-strong" />
      <span className="absolute top-1.5 h-6 w-px bg-text-2" style={{ insetInlineStart: x(0) }} />
      <span
        className="absolute top-1.5 h-6 w-px bg-critical"
        style={{ insetInlineStart: x(-margin) }}
      />
      <span
        className="absolute top-[13px] h-1.5 rounded-full"
        style={{
          insetInlineStart: x(test.low),
          width: `calc(${x(test.high)} - ${x(test.low)})`,
          background: colour,
          opacity: 0.45,
        }}
      />
      <span
        className="absolute top-[11px] size-2.5 -translate-x-1/2 rounded-full ring-2 ring-surface rtl:translate-x-1/2"
        style={{ insetInlineStart: x(test.gain), background: colour }}
      />
      <span
        className="absolute -top-1.5 -translate-x-1/2 rtl:translate-x-1/2"
        style={{ insetInlineStart: x(0) }}
      >
        0
      </span>
      <span
        className="absolute top-7 -translate-x-1/2 text-critical-ink rtl:translate-x-1/2"
        style={{ insetInlineStart: x(-margin) }}
      >
        {t("home.numbers.sensors.margin", { margin: f.number(-margin, 0) })}
      </span>
    </div>
  );
}

const LAYERS: { key: string; icon: LucideIcon }[] = [
  { key: "policy", icon: BrainCircuit },
  { key: "bias", icon: Scale },
  { key: "ambulance", icon: Ambulance },
  { key: "shield", icon: ShieldCheck },
];

/** The four layers of a decision, in order: the signal flows from the policy to the light. */
function Architecture({ study }: { study: Study }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const c = study.candidate;
  const values = {
    n: LAYERS.length,
    beta: f.number(c.beta, 0),
    range: c.evRangeM,
    every: c.decisionS,
    minGreen: c.minGreenS,
    maxRed: c.maxRedS,
  };
  return (
    <Section
      id="architecture"
      title={t("home.architecture.title")}
      description={t("home.architecture.text", values)}
      badges={<EvidenceBadge kind="prereg" />}
    >
      <ol className="relative grid gap-3 lg:grid-cols-4 lg:gap-4">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute top-[2.15rem] hidden h-px lg:start-[12%] lg:end-[12%] lg:block"
        >
          <svg className="absolute inset-0 h-px w-full overflow-visible" preserveAspectRatio="none">
            <line
              x1="0"
              y1="0"
              x2="100%"
              y2="0"
              stroke="var(--border-strong)"
              strokeWidth="2"
              strokeDasharray="6 6"
              style={{ animation: "flow-dash 1.2s linear infinite" }}
            />
          </svg>
        </span>
        {LAYERS.map(({ key, icon: Icon }, i) => (
          <motion.li
            key={key}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 + i * 0.12, duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
            className="relative flex flex-col gap-3 rounded-xl border border-border bg-surface p-5"
          >
            <div className="flex items-center gap-3">
              <span className="relative flex size-11 shrink-0 items-center justify-center rounded-lg border border-border-strong bg-surface-2">
                <Icon aria-hidden="true" className="size-5 text-text" />
                <motion.span
                  aria-hidden="true"
                  className="absolute inset-0 rounded-lg border-2"
                  style={{ borderColor: methodColorVar("hybrid_h2") }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: [0, 1, 0] }}
                  transition={{
                    duration: 1.6,
                    delay: 0.6 + i * 0.4,
                    repeat: Infinity,
                    repeatDelay: 1.6,
                  }}
                />
              </span>
              <span className="eyebrow">{t("home.architecture.step", { n: i + 1 })}</span>
            </div>
            <h3 className="text-base font-semibold text-text">
              {tx(`home.architecture.layers.${key}.title`, values)}
            </h3>
            <p className="text-sm leading-relaxed text-text-2">
              {tx(`home.architecture.layers.${key}.text`, values)}
            </p>
          </motion.li>
        ))}
      </ol>
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
        <PlainBox>{t("home.architecture.plain")}</PlainBox>
        <p className="flex items-center gap-2 rounded-xl border border-dashed border-border-strong px-4 py-3 text-sm text-text-2">
          <ControllerName controller="hybrid_h2_llm" />
          <span>{t("home.architecture.llm")}</span>
        </p>
      </div>
    </Section>
  );
}

function Claims({
  final,
  study,
  tests,
}: {
  final: FinalController;
  study: Study;
  tests: TestRow[];
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const s = summarize(tests, study);
  const travel = findTest(tests, "grid4x4", "sensor_noise", "peak", "travel");
  const waiting = findTest(tests, "grid4x4", "sensor_noise", "peak", "waiting");
  const cand = ambulanceDelay(final, "hybrid_h2", "peak");
  const mp = ambulanceDelay(final, "mp", "peak");
  const signed = (v: number) => `${v > 0 ? "+" : ""}${f.number(v, 1)} %`;
  const can = [
    t("home.claims.can.holds", {
      margin: f.number(study.marginPct, 0),
      n: s.holds,
      total: s.total,
      best: s.best,
    }),
    travel && waiting
      ? t("home.claims.can.sensors", { travel: signed(travel.gain), waiting: signed(waiting.gain) })
      : null,
    cand && mp
      ? t("home.claims.can.ambulances", {
          ratio: f.number(mp.mean / cand.mean, 1),
          candidate: f.number(cand.mean, 0),
          mp: f.number(mp.mean, 0),
        })
      : null,
  ].filter((x): x is string => x !== null);
  const cannot = [
    t("home.claims.cannot.everywhere", { n: s.total - s.holds, total: s.total }),
    t("home.claims.cannot.losses", {
      n: s.loss,
      min: f.number(s.lossMin, 1),
      max: f.number(s.lossMax, 1),
    }),
    t("home.claims.cannot.wide", { n: s.wide, real: s.wideRealPeak }),
    t("home.claims.cannot.city"),
  ];
  return (
    <Section id="claims" title={t("home.claims.title")} badges={<EvidenceBadge kind="prereg" />}>
      <ClaimsBlock can={can} cannot={cannot} />
      <PlainBox>{t("home.claims.plain")}</PlainBox>
    </Section>
  );
}

const PAGES: { to: string; key: string; icon: LucideIcon }[] = [
  { to: "/final-controller", key: "final", icon: Scale },
  { to: "/robustness", key: "robustness", icon: ShieldHalf },
  { to: "/live-map", key: "demo", icon: MapPinned },
];

function Explore() {
  const { t } = useTranslation();
  const tx = useTx();
  return (
    <Section id="explore" title={t("home.explore.title")}>
      <ul className="grid gap-4 md:grid-cols-3">
        {PAGES.map(({ to, key, icon: Icon }) => (
          <li key={key}>
            <Link
              to={to}
              className="group flex h-full flex-col gap-2 rounded-xl border border-border bg-surface p-5 transition-colors hover:border-border-strong hover:bg-surface-2"
            >
              <Icon aria-hidden="true" className="size-5 text-text" />
              <span className="flex items-center gap-2 text-base font-semibold text-text">
                {tx(`home.explore.${key}.title`)}
                <ArrowRight
                  aria-hidden="true"
                  className="size-4 transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100"
                />
              </span>
              <span className="text-sm text-text-2">{tx(`home.explore.${key}.text`)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
}
