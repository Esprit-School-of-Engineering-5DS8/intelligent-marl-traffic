import { motion } from "motion/react";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import { collapse, VERDICT_ORDER } from "@/features/final-controller/forest";
import { ControllerName } from "@/shared/components/controller";
import { VerdictBadge } from "@/shared/components/evidence";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColorVar } from "@/shared/domain/methods";
import type { FinalController } from "@/shared/schemas";
import type { TestRow, TestVerdict } from "@/shared/schemas/combined";

/** The worst gap of every controller, from zero: the candidate's is the shortest bar. */
export function WorstGapBars({
  final,
  size = "sm",
}: {
  final: FinalController;
  size?: "sm" | "lg";
}) {
  const f = useFormat();
  const rows = [...final.compromise].sort((a, b) => a.worst - b.worst);
  const max = Math.max(...rows.map((r) => r.worst));
  const lg = size === "lg";
  return (
    <ul className={lg ? "flex flex-col gap-3 text-sm" : "flex flex-col gap-1.5 text-xs"}>
      {rows.map((r) => (
        <li
          key={r.controller}
          className={
            lg
              ? "grid grid-cols-[11rem_1fr_4rem] items-center gap-3"
              : "grid grid-cols-[9.5rem_1fr_3.5rem] items-center gap-2"
          }
        >
          <ControllerName
            controller={r.controller}
            className={
              r.controller === "hybrid_h2"
                ? "truncate font-semibold text-text"
                : "truncate text-text-2"
            }
          />
          <span className={lg ? "h-4 rounded-full bg-surface-3" : "h-2 rounded-full bg-surface-3"}>
            <motion.span
              initial={{ width: 0 }}
              animate={{ width: `${(100 * r.worst) / max}%` }}
              transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
              className={lg ? "block h-4 rounded-full" : "block h-2 rounded-full"}
              style={{ background: methodColorVar(r.controller) }}
            />
          </span>
          <span className="tabular text-end font-medium text-text">{f.number(r.worst, 1)} %</span>
        </li>
      ))}
    </ul>
  );
}

/** One square per ambulance trip (one row per trained model): filled = faster than MP. */
export function TripDots({ faster, total, rows }: { faster: number; total: number; rows: number }) {
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

/** The 95 % interval of a gain on a line that shows 0 and the margin. */
export function IntervalLine({ test, margin }: { test: TestRow; margin: number }) {
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

const SQUARE: Record<TestVerdict, CSSProperties> = {
  best: { background: "var(--good)" },
  noninf: { background: "var(--ctl-candidate)" },
  loss: { background: "var(--critical)" },
  lossBeyond: { background: "var(--critical)" },
  wide: { border: "2px solid var(--wide)" },
  notSup: { border: "2px solid var(--wide)" },
};

/**
 * Every preregistered test as one square, grouped by verdict: the whole evaluation at a
 * glance. Hovering a square names its situation; the legend gives the counts.
 */
export function VerdictWaffle({ tests }: { tests: TestRow[] }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const main = tests.filter((x) => x.family === "hybrid");
  const groups = VERDICT_ORDER.map((v) => ({
    v,
    rows: main.filter((x) => collapse(x.verdict) === v),
  }));
  const label = groups.map((g) => `${tx(`ui.verdicts.${g.v}`)} : ${g.rows.length}`).join(", ");
  return (
    <div className="flex flex-col gap-5">
      <div
        role="img"
        aria-label={t("results.waffleAlt", { total: main.length, detail: label })}
        className="flex flex-wrap gap-4"
      >
        {groups.map((g, gi) =>
          g.rows.length ? (
            <div key={g.v} className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-1.5" style={{ maxWidth: "14rem" }}>
                {g.rows.map((r, i) => (
                  <motion.span
                    key={`${r.network}${r.scenario}${r.demand}${r.metric}`}
                    title={`${f.cellName(r)} · ${tx(`final.metrics.${r.metric}`)} : ${r.gain > 0 ? "+" : ""}${f.number(r.gain, 1)} %`}
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 + gi * 0.25 + i * 0.03, duration: 0.25 }}
                    className="size-6 rounded-[5px]"
                    style={SQUARE[r.verdict]}
                  />
                ))}
              </div>
            </div>
          ) : null,
        )}
      </div>
      <ul className="flex flex-wrap gap-2">
        {groups.map((g) => (
          <li key={g.v} className="flex items-center gap-2">
            <VerdictBadge verdict={g.v} />
            <span className="tabular text-sm font-semibold text-text">{g.rows.length}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
