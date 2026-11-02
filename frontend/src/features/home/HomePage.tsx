import {
  ArrowRight,
  BrainCircuit,
  Building2,
  Gauge,
  MessagesSquare,
  Scale,
  ShieldCheck,
  ShieldHalf,
  TrafficCone,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { findTest } from "@/features/combined/claims";
import { IntervalLine, TripDots, WorstGapBars } from "@/features/combined/visuals";
import { useFinalController, useStudy, useTests } from "@/shared/api/queries";
import { EvidenceBadge, SourceNote, VerdictBadge } from "@/shared/components/evidence";
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
            <Journey />
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

const JOURNEY: { to: string; key: string; icon: LucideIcon }[] = [
  { to: "/how-it-works", key: "how", icon: Workflow },
  { to: "/final-controller", key: "results", icon: Scale },
  { to: "/llm", key: "llm", icon: MessagesSquare },
  { to: "/robustness", key: "robustness", icon: ShieldHalf },
  { to: "/cities", key: "cities", icon: Building2 },
];

/** The order of the defence: each step is one page that answers one question. */
function Journey() {
  const { t } = useTranslation();
  const tx = useTx();
  return (
    <Section id="journey" title={t("home.journey.title")} description={t("home.journey.text")}>
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {JOURNEY.map(({ to, key, icon: Icon }, i) => (
          <li key={key}>
            <Link
              to={to}
              className="group flex h-full flex-col gap-3 rounded-xl border border-border bg-surface p-5 transition-colors hover:border-border-strong hover:bg-surface-2"
            >
              <span className="flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-ink">
                  {i + 2}
                </span>
                <Icon aria-hidden="true" className="size-4 text-text" />
              </span>
              <span className="text-base font-semibold text-text">
                {tx(`home.journey.${key}.title`)}
              </span>
              <span className="text-sm leading-relaxed text-text-2">
                {tx(`home.journey.${key}.question`)}
              </span>
              <ArrowRight
                aria-hidden="true"
                className="mt-auto size-4 text-muted transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100"
              />
            </Link>
          </li>
        ))}
      </ol>
    </Section>
  );
}
