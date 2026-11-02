import {
  Ambulance,
  BrainCircuit,
  MessagesSquare,
  Scale,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useLlmLoop, useStudy } from "@/shared/api/queries";
import { EvidenceBadge, PlainBox } from "@/shared/components/evidence";
import { KeyPoints, PageHero } from "@/shared/components/page";
import { QueriesState } from "@/shared/components/QueriesState";
import { Section } from "@/shared/components/section";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColorVar } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { Study } from "@/shared/schemas/combined";
import { Segmented } from "@/shared/ui/segmented";

export default function HowItWorksPage() {
  const { t } = useTranslation();
  usePageTitle(t("nav.howItWorks"));
  const queries = { study: useStudy(), loop: useLlmLoop() };
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-10">
      <QueriesState queries={queries} height={480}>
        {({ study, loop }) => (
          <>
            <PageHero
              eyebrow={t("how.eyebrow")}
              title={t("how.title")}
              answer={t("how.answer", { every: study.candidate.decisionS })}
            />
            <Pipeline study={study} windowMin={loop.windowS / 60} />
            <WhoDecides study={study} />
            <KeyPoints
              title={t("how.keyTitle")}
              points={[t("how.key.one"), t("how.key.two"), t("how.key.three")]}
            />
          </>
        )}
      </QueriesState>
    </div>
  );
}

const LAYERS: { key: string; icon: LucideIcon; rhythm: "slow" | "fast" }[] = [
  { key: "llm", icon: MessagesSquare, rhythm: "slow" },
  { key: "policy", icon: BrainCircuit, rhythm: "fast" },
  { key: "bias", icon: Scale, rhythm: "fast" },
  { key: "ambulance", icon: Ambulance, rhythm: "fast" },
  { key: "shield", icon: ShieldCheck, rhythm: "fast" },
];

/** The five layers, top to bottom, with a pulse travelling down: one decision. */
function Pipeline({ study, windowMin }: { study: Study; windowMin: number }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const c = study.candidate;
  const values = {
    beta: f.number(c.beta, 0),
    range: c.evRangeM,
    every: c.decisionS,
    minGreen: c.minGreenS,
    maxRed: c.maxRedS,
    window: f.number(windowMin, 0),
  };
  return (
    <Section id="pipeline" title={t("how.pipeline.title")} description={t("how.pipeline.text")}>
      <ol className="relative flex flex-col gap-3">
        <span
          aria-hidden="true"
          className="absolute start-[1.65rem] top-6 bottom-6 w-px bg-border-strong"
        />
        <motion.span
          aria-hidden="true"
          className="absolute start-[1.4rem] size-3 rounded-full"
          style={{ background: methodColorVar("hybrid_h2") }}
          initial={{ top: "1.5rem", opacity: 0 }}
          animate={{ top: ["1.5rem", "calc(100% - 2.25rem)"], opacity: [0, 1, 1, 0] }}
          transition={{ duration: 3.2, repeat: Infinity, repeatDelay: 0.8, ease: "easeInOut" }}
        />
        {LAYERS.map(({ key, icon: Icon, rhythm }, i) => (
          <motion.li
            key={key}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.1 + i * 0.1, duration: 0.4 }}
            className={cn(
              "relative grid gap-3 rounded-xl border bg-surface p-4 ps-16 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] md:items-center",
              key === "llm" ? "border-dashed" : "border-border",
            )}
            style={key === "llm" ? { borderColor: methodColorVar("hybrid_h2_llm") } : undefined}
          >
            <span className="absolute start-3 top-4 flex size-9 items-center justify-center rounded-lg border border-border-strong bg-surface-2">
              <Icon aria-hidden="true" className="size-5 text-text" />
            </span>
            <div className="flex flex-col gap-1">
              <span className="eyebrow">
                {tx(`how.rhythm.${rhythm}`, values)} · {t("how.pipeline.step", { n: i + 1 })}
              </span>
              <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold text-text">
                {tx(`how.layers.${key}.title`, values)}
                {key === "llm" ? <EvidenceBadge kind="exploratory" /> : null}
              </h3>
            </div>
            <p className="text-sm leading-relaxed text-text-2">
              {tx(`how.layers.${key}.text`, values)}
            </p>
          </motion.li>
        ))}
      </ol>
      <PlainBox>{t("how.pipeline.plain")}</PlainBox>
    </Section>
  );
}

type Mode = "equilibre" | "fluidite" | "agent";

/**
 * "Who decides?": the agent's confidence in its phase against Max-Pressure's phase. The
 * agent's scores are log-probabilities; the bias adds beta to Max-Pressure's phase, so the
 * agent keeps its phase only if p / (1 - p) > e^beta (two phases).
 */
function WhoDecides({ study }: { study: Study }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [confidence, setConfidence] = useState(80);
  const [mode, setMode] = useState<Mode>("equilibre");
  const beta = mode === "equilibre" ? study.candidate.beta : 0;
  const p = confidence / 100;
  const agentScore = Math.log(p);
  const mpScore = Math.log(1 - p) + beta;
  const agentWins = mode !== "fluidite" && agentScore > mpScore;
  const threshold = (100 * Math.exp(beta)) / (1 + Math.exp(beta));
  const lo = Math.min(agentScore, Math.log(1 - p), -5);
  const hi = Math.max(agentScore, mpScore, 1);
  const width = (v: number) => `${(100 * (v - lo)) / (hi - lo)}%`;
  return (
    <Section
      id="who-decides"
      title={t("how.who.title")}
      description={t("how.who.text")}
      badges={<EvidenceBadge kind="descriptive" />}
    >
      <div className="grid gap-6 rounded-2xl border border-border bg-surface p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="flex flex-col gap-5">
          <Segmented
            label={t("how.who.mode")}
            value={mode}
            onChange={setMode}
            options={(["equilibre", "fluidite", "agent"] as const).map((m) => ({
              value: m,
              label: t(`how.modes.${m}`),
            }))}
          />
          <label className="flex flex-col gap-2 text-sm text-text-2">
            <span>
              {t("how.who.slider")} <b className="tabular text-text">{confidence} %</b>
            </span>
            <input
              type="range"
              min={50}
              max={99.9}
              step={0.1}
              value={confidence}
              onChange={(e) => setConfidence(Number(e.target.value))}
              className="accent-[var(--ctl-candidate)]"
            />
          </label>
          <p className="text-sm leading-relaxed text-text-2">
            {mode === "equilibre"
              ? t("how.who.threshold", {
                  beta: f.number(study.candidate.beta, 0),
                  factor: f.number(Math.exp(study.candidate.beta), 1),
                  threshold: f.number(threshold, 1),
                })
              : t(`how.who.modeText.${mode}`)}
          </p>
        </div>
        <div className="flex flex-col gap-4" aria-live="polite">
          <Bar
            label={t("how.who.agentPhase")}
            detail={`ln(${f.number(p, 3)}) = ${f.number(agentScore, 2)}`}
            width={width(agentScore)}
            colour={methodColorVar("coop_full")}
            winner={agentWins}
          />
          <Bar
            label={t("how.who.mpPhase")}
            detail={
              beta > 0
                ? `ln(${f.number(1 - p, 3)}) + ${f.number(beta, 0)} = ${f.number(mpScore, 2)}`
                : `ln(${f.number(1 - p, 3)}) = ${f.number(mpScore, 2)}`
            }
            width={width(mpScore)}
            colour={methodColorVar("mp")}
            winner={!agentWins}
          />
          <p className="rounded-lg bg-surface-2 p-3 text-sm font-medium text-text">
            {agentWins ? t("how.who.agentDecides") : t("how.who.mpDecides")}
          </p>
        </div>
      </div>
    </Section>
  );
}

function Bar({
  label,
  detail,
  width,
  colour,
  winner,
}: {
  label: string;
  detail: string;
  width: string;
  colour: string;
  winner: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className={cn("font-medium", winner ? "text-text" : "text-text-2")}>
          {label}
          {winner ? <span className="ms-2 text-xs text-muted">({t("how.who.chosen")})</span> : null}
        </span>
        <span className="tabular font-mono text-xs text-muted">{detail}</span>
      </div>
      <span className="block h-3 rounded-full bg-surface-3">
        <motion.span
          className="block h-3 rounded-full"
          style={{ background: colour, opacity: winner ? 1 : 0.45 }}
          animate={{ width }}
          transition={{ duration: 0.35 }}
        />
      </span>
    </div>
  );
}
