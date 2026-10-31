import {
  ChartColumn,
  CircleCheckBig,
  CircleDashed,
  CircleOff,
  CircleX,
  Compass,
  Database,
  Diamond,
  FlaskConical,
  Lightbulb,
  OctagonPause,
  ShieldCheck,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib/cn";
import type { TestVerdict } from "@/shared/schemas/combined";

/** How much a number can be trusted: what the jury must know before reading it. */
export type Evidence =
  "prereg" | "descriptive" | "exploratory" | "validation" | "secondary" | "stopped";

const EVIDENCE: Record<Evidence, { icon: LucideIcon; className: string }> = {
  prereg: { icon: ShieldCheck, className: "border-border-strong text-text" },
  descriptive: { icon: ChartColumn, className: "border-border-strong text-text-2" },
  exploratory: { icon: Compass, className: "border-dashed border-border-strong text-text-2" },
  validation: { icon: FlaskConical, className: "border-border-strong text-text-2" },
  secondary: { icon: CircleDashed, className: "border-border text-text-2" },
  stopped: { icon: OctagonPause, className: "border-dashed border-border-strong text-text-2" },
};

/** "pré-enregistré", "exploratoire", "validation"...: a label and an icon, never a colour. */
export function EvidenceBadge({ kind, className }: { kind: Evidence; className?: string }) {
  const { t } = useTranslation();
  const { icon: Icon, className: tone } = EVIDENCE[kind];
  return (
    <span
      title={t(`ui.evidence.${kind}.hint`)}
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border bg-surface px-2.5 text-[11px] font-medium whitespace-nowrap",
        tone,
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      {t(`ui.evidence.${kind}.label`)}
    </span>
  );
}

const VERDICT: Record<TestVerdict, { icon: LucideIcon; className: string }> = {
  best: { icon: CircleCheckBig, className: "bg-good-soft text-good-ink" },
  noninf: { icon: Diamond, className: "bg-surface-3 text-text [&_svg]:text-candidate" },
  loss: { icon: CircleX, className: "bg-critical-soft text-critical-ink" },
  lossBeyond: { icon: TriangleAlert, className: "bg-critical-soft text-critical-ink" },
  wide: { icon: CircleDashed, className: "bg-surface-3 text-text-2" },
  notSup: { icon: CircleOff, className: "bg-surface-3 text-text-2" },
};

/** The verdict of one test, with its icon: the colour is never the only cue. */
export function VerdictBadge({ verdict, className }: { verdict: TestVerdict; className?: string }) {
  const { t } = useTranslation();
  const { icon: Icon, className: tone } = VERDICT[verdict];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3.5",
        tone,
        className,
      )}
    >
      <Icon aria-hidden="true" />
      {t(`ui.verdicts.${verdict}`)}
    </span>
  );
}

/** "Ce qu'on peut affirmer / ce qu'on ne peut pas affirmer", side by side. */
export function ClaimsBlock({
  can,
  cannot,
  className,
}: {
  can: ReactNode[];
  cannot: ReactNode[];
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className={cn("grid gap-4 lg:grid-cols-2", className)}>
      <ClaimList title={t("ui.claims.can")} items={can} kind="can" />
      <ClaimList title={t("ui.claims.cannot")} items={cannot} kind="cannot" />
    </div>
  );
}

function ClaimList({
  title,
  items,
  kind,
}: {
  title: string;
  items: ReactNode[];
  kind: "can" | "cannot";
}) {
  const Icon = kind === "can" ? CircleCheckBig : CircleX;
  return (
    <section
      aria-label={title}
      className={cn(
        "rounded-xl border bg-surface p-5",
        kind === "can" ? "border-border" : "border-dashed border-border-strong",
      )}
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold text-text">
        <Icon
          aria-hidden="true"
          className={cn("size-4", kind === "can" ? "text-good-ink" : "text-critical-ink")}
        />
        {title}
      </h3>
      <ul className="mt-3 flex flex-col gap-2.5 text-sm leading-relaxed text-text-2">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2.5">
            <span
              aria-hidden="true"
              className={cn(
                "mt-2 size-1.5 shrink-0 rounded-full",
                kind === "can" ? "bg-good" : "bg-critical",
              )}
            />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** "En simple": the same result told without statistics, for a non-specialist. */
export function PlainBox({ children, className }: { children: ReactNode; className?: string }) {
  const { t } = useTranslation();
  return (
    <aside
      aria-label={t("ui.plain")}
      className={cn(
        "flex gap-3 rounded-xl border border-border bg-surface-2 p-4 text-sm leading-relaxed text-text-2",
        className,
      )}
    >
      <Lightbulb aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-text" />
      <div>
        <p className="eyebrow mb-1">{t("ui.plain")}</p>
        {children}
      </div>
    </aside>
  );
}

/** Where the numbers of a block come from: the result file and the code that wrote it. */
export function SourceNote({
  source,
  extra,
  className,
}: {
  source: string;
  extra?: ReactNode;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <p className={cn("flex items-start gap-1.5 text-[11px] leading-snug text-muted", className)}>
      <Database aria-hidden="true" className="mt-px size-3 shrink-0" />
      <span>
        <span className="font-medium text-text-2">{t("ui.source")}</span>{" "}
        <span className="font-mono break-all">{source}</span>
        {extra ? <> · {extra}</> : null}
      </span>
    </p>
  );
}
