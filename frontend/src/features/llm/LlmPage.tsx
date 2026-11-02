import { CheckCircle2, Clock, MessagesSquare, ShieldCheck, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { useLlmLoop, useStudy } from "@/shared/api/queries";
import { ClaimsBlock, EvidenceBadge, SourceNote } from "@/shared/components/evidence";
import { Details, KeyPoints, PageHero, Spotlight } from "@/shared/components/page";
import { QueriesState } from "@/shared/components/QueriesState";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColorVar } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { LlmLoop, Study, StrategyMode } from "@/shared/schemas/combined";

/** The colour of a mode: the controller that runs the network in that mode. */
const MODE_COLOUR: Record<StrategyMode, string> = {
  equilibre: methodColorVar("hybrid_h2"),
  fluidite: methodColorVar("mp"),
  agent: methodColorVar("coop_full"),
};

export default function LlmPage() {
  const { t } = useTranslation();
  usePageTitle(t("nav.llm"));
  const queries = { loop: useLlmLoop(), study: useStudy() };
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-10">
      <QueriesState queries={queries} height={480}>
        {({ loop, study }) => <Content loop={loop} study={study} />}
      </QueriesState>
    </div>
  );
}

function signed(f: ReturnType<typeof useFormat>, v: number | null | undefined) {
  return v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${f.number(v, 1)} %`;
}

function Content({ loop, study }: { loop: LlmLoop; study: Study }) {
  const { t } = useTranslation();
  const f = useFormat();
  const minutes = f.number(loop.windowS / 60, 0);
  const travel = loop.testOverall.travel;
  const waiting = loop.testOverall.waiting;
  const switched = 100 * (1 - (loop.shares.equilibre ?? 0));
  return (
    <>
      <PageHero
        eyebrow={t("llm.eyebrow")}
        title={t("llm.title")}
        answer={t("llm.answer", { minutes, model: loop.model })}
        badges={
          <>
            <EvidenceBadge kind="exploratory" />
            <EvidenceBadge kind={loop.test.length ? "secondary" : "validation"} />
          </>
        }
      />

      <Guardrails loop={loop} />

      <Spotlight
        title={t("llm.timeline.title")}
        message={t("llm.timeline.message", {
          situation: f.cellName(loop.timeline),
          n: loop.timeline.calls.length,
        })}
        footer={t("llm.timeline.footer")}
        visual={<Timeline loop={loop} />}
      />
      <Decisions loop={loop} />

      <Spotlight
        title={t("llm.effect.title")}
        message={
          travel && waiting
            ? t("llm.effect.message", {
                travel: signed(f, travel.gain),
                waiting: signed(f, waiting.gain),
                pairs: travel.pairs,
              })
            : t("llm.effect.pending")
        }
        footer={t("llm.effect.footer", { share: f.number(switched, 0) })}
        visual={<Effect loop={loop} />}
      />

      <ClaimsBlock
        can={[
          t("llm.claims.can.loop", { minutes }),
          t("llm.claims.can.valid", {
            valid: f.number(100 * loop.validRate, 0),
            latency: f.number(loop.latencyP50S, 1),
            calls: loop.calls,
          }),
          t("llm.claims.can.safe"),
        ]}
        cannot={[
          t("llm.claims.cannot.prereg", { commit: study.prereg }),
          t("llm.claims.cannot.ceiling"),
          t("llm.claims.cannot.small"),
          t("llm.claims.cannot.reasons"),
        ]}
      />

      <Details
        title={t("llm.oracle.title")}
        hint={t("llm.oracle.hint")}
        badges={<EvidenceBadge kind="validation" />}
      >
        <OracleTable loop={loop} />
      </Details>
      {loop.test.length ? (
        <Details
          title={t("llm.cells.title")}
          hint={t("llm.cells.hint")}
          badges={<EvidenceBadge kind="exploratory" />}
        >
          <CellsTable rows={loop.test} />
        </Details>
      ) : null}
      {loop.advisor ? (
        <Details title={t("llm.advisor.title")} hint={t("llm.advisor.hint")}>
          <p className="text-sm leading-relaxed text-text-2">
            {t("llm.advisor.text", {
              travel: signed(f, loop.advisor.travel?.gain),
              waiting: signed(f, loop.advisor.waiting?.gain),
              ambulances: signed(f, loop.advisor.ambulances?.gain),
            })}
          </p>
        </Details>
      ) : null}

      <KeyPoints
        title={t("llm.keyTitle")}
        points={[t("llm.key.one", { minutes }), t("llm.key.two"), t("llm.key.three")]}
      />
      <SourceNote source={loop.source} extra={`${loop.model} · ${loop.prompt}`} />
    </>
  );
}

/** What keeps the model from doing harm: four guarantees, one line each. */
function Guardrails({ loop }: { loop: LlmLoop }) {
  const { t } = useTranslation();
  const f = useFormat();
  const items: [LucideIcon, string][] = [
    [MessagesSquare, t("llm.guard.modes")],
    [CheckCircle2, t("llm.guard.format", { valid: f.number(100 * loop.validRate, 0) })],
    [Clock, t("llm.guard.latency", { latency: f.number(loop.latencyP50S, 1) })],
    [ShieldCheck, t("llm.guard.safety")],
  ];
  return (
    <section aria-label={t("llm.guard.title")} className="flex flex-col gap-3">
      <h2 className="eyebrow">{t("llm.guard.title")}</h2>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {items.map(([Icon, text], i) => (
          <motion.li
            key={text}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 + i * 0.07 }}
            className="flex gap-3 rounded-xl border border-border bg-surface p-4 text-sm leading-relaxed text-text-2"
          >
            <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-text" />
            {text}
          </motion.li>
        ))}
      </ul>
    </section>
  );
}

/** The episode as a band: one colour per mode, a tick at each call of the model. */
function Timeline({ loop }: { loop: LlmLoop }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const { calls, end } = loop.timeline;
  // the mode in force between two applied decisions
  const segments: { from: number; to: number; mode: StrategyMode }[] = [];
  let mode: StrategyMode = "equilibre";
  let from = 0;
  for (const c of calls.filter((x) => x.valid)) {
    if (c.mode !== mode) {
      segments.push({ from, to: c.appliesAt, mode });
      mode = c.mode;
      from = c.appliesAt;
    }
  }
  segments.push({ from, to: end, mode });
  const x = (s: number) => `${(100 * s) / end}%`;
  const modes = [...new Set(segments.map((s) => s.mode))];
  return (
    <div className="flex flex-col gap-3">
      <div
        role="img"
        aria-label={t("llm.timeline.alt", {
          detail: segments
            .map((s) => `${tx(`how.modes.${s.mode}`)} ${f.clock(s.from)}–${f.clock(s.to)}`)
            .join(", "),
        })}
        className="relative h-12 overflow-hidden rounded-lg bg-surface-3"
      >
        {segments.map((s, i) => (
          <motion.span
            key={i}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ delay: 0.1 + i * 0.12, duration: 0.4 }}
            className="absolute inset-y-0 origin-left rtl:origin-right"
            style={{
              insetInlineStart: x(s.from),
              width: x(s.to - s.from),
              background: MODE_COLOUR[s.mode],
            }}
          />
        ))}
        {calls.map((c, i) => (
          <span
            key={i}
            aria-hidden="true"
            className="absolute inset-y-0 w-0.5 bg-surface"
            style={{ insetInlineStart: x(c.time) }}
          />
        ))}
      </div>
      <div className="tabular flex items-center justify-between text-[11px] text-muted">
        <span>{f.clock(0)}</span>
        <span>{t("llm.timeline.ticks")}</span>
        <span>{f.clock(end)}</span>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-2">
        {(["equilibre", "fluidite", "agent"] as const)
          .filter((m) => modes.includes(m) || m === "equilibre")
          .map((m) => (
            <li key={m} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="size-2.5 rounded-[3px]"
                style={{ background: MODE_COLOUR[m] }}
              />
              {tx(`how.modes.${m}`)}
            </li>
          ))}
      </ul>
    </div>
  );
}

/** Each call: when, what the model read, what it chose and why (its own sentence). */
function Decisions({ loop }: { loop: LlmLoop }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  return (
    <Details title={t("llm.decisions.title")} hint={t("llm.decisions.hint")} defaultOpen>
      <ol className="flex flex-col gap-2">
        {loop.timeline.calls.map((c, i) => {
          const changed = i > 0 && c.mode !== loop.timeline.calls[i - 1]!.mode;
          return (
            <li
              key={i}
              className={cn(
                "grid gap-2 rounded-lg border p-3 text-sm md:grid-cols-[5rem_11rem_minmax(0,1fr)] md:items-center",
                changed ? "border-border-strong bg-surface-2" : "border-border",
              )}
            >
              <span className="tabular font-mono text-xs text-muted">{f.clock(c.time)}</span>
              <span className="flex items-center gap-2 font-medium text-text">
                <span
                  aria-hidden="true"
                  className="size-2.5 rounded-[3px]"
                  style={{ background: MODE_COLOUR[c.mode] }}
                />
                {tx(`how.modes.${c.mode}`)}
                {changed ? (
                  <span className="text-xs font-normal text-muted">
                    ({t("llm.decisions.switch")})
                  </span>
                ) : null}
              </span>
              <span className="text-text-2">
                « {c.reason} »{" "}
                <span className="text-xs text-muted">
                  {t("llm.decisions.state", {
                    halted: c.halted ?? "–",
                    backlog: c.backlog ?? "–",
                    latency: f.number(c.latency, 1),
                  })}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </Details>
  );
}

/** The paired gains over the candidate alone, with their intervals, on the test seeds. */
function Effect({ loop }: { loop: LlmLoop }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const rows = (["travel", "waiting", "ambulances"] as const)
    .map((k) => ({ k, v: loop.testOverall[k] }))
    .filter((r) => r.v);
  if (!rows.length) return <p className="text-sm text-muted">{t("llm.effect.pending")}</p>;
  const span = Math.max(5, ...rows.flatMap((r) => [Math.abs(r.v!.low), Math.abs(r.v!.high)]));
  const x = (v: number) => `${50 + (50 * v) / span}%`;
  return (
    <ul className="flex flex-col gap-5">
      {rows.map(({ k, v }) => (
        <li key={k} className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between text-sm">
            <span className="font-medium text-text">{tx(`final.criteria.${k}`)}</span>
            <span className="tabular text-text">
              <b>{signed(f, v!.gain)}</b>{" "}
              <span className="text-xs text-muted">
                [{signed(f, v!.low)} ; {signed(f, v!.high)}]
              </span>
            </span>
          </div>
          <div aria-hidden="true" className="relative h-6">
            <span className="absolute inset-x-0 top-3 h-px bg-border-strong" />
            <span
              className="absolute top-0.5 h-5 w-px bg-text-2"
              style={{ insetInlineStart: "50%" }}
            />
            <span
              className="absolute top-2 h-2 rounded-full opacity-50"
              style={{
                insetInlineStart: x(v!.low),
                width: `calc(${x(v!.high)} - ${x(v!.low)})`,
                background: methodColorVar("hybrid_h2_llm"),
              }}
            />
            <span
              className="absolute top-1.5 size-3 -translate-x-1/2 rounded-full ring-2 ring-surface rtl:translate-x-1/2"
              style={{ insetInlineStart: x(v!.gain), background: methodColorVar("hybrid_h2_llm") }}
            />
          </div>
        </li>
      ))}
      <li className="flex justify-between text-[11px] text-muted">
        <span>{t("llm.effect.worse")}</span>
        <span>0</span>
        <span>{t("llm.effect.better")}</span>
      </li>
    </ul>
  );
}

function OracleTable({ loop }: { loop: LlmLoop }) {
  const { t } = useTranslation();
  const f = useFormat();
  const s = (v: number | null | undefined) =>
    v === null || v === undefined ? "–" : `${f.number(v, 1)} s`;
  return (
    <div tabIndex={0} role="region" aria-label={t("llm.oracle.title")} className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <caption className="sr-only">{t("llm.oracle.caption")}</caption>
        <thead className="bg-surface-2 text-xs text-text-2">
          <tr>
            {(["situation", "candidate", "llm", "oracle", "placebo"] as const).map((c) => (
              <th key={c} scope="col" className="px-3 py-2 text-start font-medium">
                {t(`llm.oracle.columns.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {loop.validation.map((r) => (
            <tr key={`${r.network}${r.scenario}${r.demand}`} className="border-t border-border">
              <td className="px-3 py-2 text-text">{f.cellName(r)}</td>
              <td className="px-3 py-2 text-text-2">{s(r.travel?.candidate)}</td>
              <td className="px-3 py-2 font-medium text-text">{s(r.travel?.llm)}</td>
              <td className="px-3 py-2 text-text-2">{s(r.travel?.oracle)}</td>
              <td className="px-3 py-2 text-text-2">{s(r.travel?.placeboBest)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">{t("llm.oracle.note")}</p>
    </div>
  );
}

function CellsTable({ rows }: { rows: LlmLoop["test"] }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  return (
    <div tabIndex={0} role="region" aria-label={t("llm.cells.title")} className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <caption className="sr-only">{t("llm.cells.title")}</caption>
        <thead className="bg-surface-2 text-xs text-text-2">
          <tr>
            <th scope="col" className="px-3 py-2 text-start font-medium">
              {t("llm.oracle.columns.situation")}
            </th>
            <th scope="col" className="px-3 py-2 text-start font-medium">
              {tx("final.criteria.travel")}
            </th>
            <th scope="col" className="px-3 py-2 text-start font-medium">
              {tx("final.criteria.waiting")}
            </th>
            <th scope="col" className="px-3 py-2 text-start font-medium">
              {t("llm.cells.modes")}
            </th>
            <th scope="col" className="px-3 py-2 text-start font-medium">
              {t("llm.cells.seeds")}
            </th>
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((r) => (
            <tr key={`${r.network}${r.scenario}${r.demand}`} className="border-t border-border">
              <td className="px-3 py-2 text-text">{f.cellName(r)}</td>
              <td className="px-3 py-2 text-text-2">{signed(f, r.travel?.gain)}</td>
              <td className="px-3 py-2 text-text-2">{signed(f, r.waiting?.gain)}</td>
              <td className="px-3 py-2 text-text-2">
                {(["equilibre", "fluidite", "agent"] as const)
                  .filter((m) => (r.shares[m] ?? 0) > 0)
                  .map((m) => `${tx(`how.modes.${m}`)} ${f.number(100 * (r.shares[m] ?? 0), 0)} %`)
                  .join(" · ")}
              </td>
              <td className="px-3 py-2 text-text-2">{r.seeds}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
