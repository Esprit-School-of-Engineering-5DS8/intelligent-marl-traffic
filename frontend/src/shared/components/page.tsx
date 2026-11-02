import { ChevronDown } from "lucide-react";
import { motion } from "motion/react";
import { useId, useState, type ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

/**
 * The top of a story page: the question it answers, and the answer in one sentence. Every
 * page of the defence follows the same pattern, so the jury always knows where to look.
 */
export function PageHero({
  eyebrow,
  title,
  answer,
  badges,
  children,
}: {
  eyebrow: string;
  title: string;
  answer: ReactNode;
  badges?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="relative overflow-hidden rounded-2xl border border-border bg-surface">
      <div aria-hidden="true" className="bg-grid absolute inset-0 opacity-50" />
      <div aria-hidden="true" className="bg-glow absolute inset-0" />
      <div className="relative flex flex-col gap-4 px-6 py-8 md:px-10 md:py-10">
        <p className="eyebrow">{eyebrow}</p>
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-4xl text-3xl font-semibold tracking-tight text-balance text-text md:text-5xl"
        >
          {title}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-3xl text-base leading-relaxed text-text-2 md:text-lg"
        >
          {answer}
        </motion.p>
        {badges ? <div className="flex flex-wrap gap-2">{badges}</div> : null}
        {children}
      </div>
    </header>
  );
}

/** Three key points, numbered: what to remember from the page. */
export function KeyPoints({ title, points }: { title: string; points: ReactNode[] }) {
  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <h2 className="eyebrow">{title}</h2>
      <ol className="grid gap-3 md:grid-cols-3">
        {points.map((p, i) => (
          <motion.li
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.08, duration: 0.4 }}
            className="flex gap-3 rounded-xl border border-border bg-surface p-4"
          >
            <span
              aria-hidden="true"
              className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-ink"
            >
              {i + 1}
            </span>
            <span className="text-sm leading-relaxed text-text">{p}</span>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}

/**
 * Details folded by default: the page shows the essential, the expert opens the rest. The
 * button says what it opens; the content stays in the page for search and print.
 */
export function Details({
  title,
  hint,
  badges,
  defaultOpen = false,
  children,
}: {
  title: string;
  hint?: string;
  badges?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <section aria-labelledby={`${id}-title`} className="rounded-xl border border-border bg-surface">
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center gap-3 rounded-xl px-5 py-4 text-start hover:bg-surface-2"
        >
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-text">
              <span id={`${id}-title`}>{title}</span>
              {badges}
            </span>
            {hint ? <span className="text-xs text-muted">{hint}</span> : null}
          </span>
          <ChevronDown
            aria-hidden="true"
            className={cn("size-4 shrink-0 text-muted transition-transform", open && "rotate-180")}
          />
        </button>
      </h3>
      <div id={id} hidden={!open} className="border-t border-border px-5 py-5">
        {open ? children : null}
      </div>
    </section>
  );
}

/** A big, single message with its visual: the one thing a section must show. */
export function Spotlight({
  title,
  message,
  visual,
  footer,
  className,
}: {
  title: string;
  message: ReactNode;
  visual: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label={title}
      className={cn(
        "grid gap-6 rounded-2xl border border-border bg-surface p-6 md:p-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:items-center",
        className,
      )}
    >
      <div className="flex flex-col gap-3">
        <h2 className="eyebrow">{title}</h2>
        <div className="text-xl leading-snug font-semibold text-balance text-text md:text-2xl">
          {message}
        </div>
        {footer ? <div className="text-sm leading-relaxed text-text-2">{footer}</div> : null}
      </div>
      <div className="min-w-0">{visual}</div>
    </section>
  );
}

/**
 * The top of an exploration page: what the page shows in one sentence, which data it reads
 * (the first study or replays), how to read it, and where to go next.
 */
export function ExploreHero({
  title,
  answer,
  scope,
  tips,
  actions,
}: {
  title: string;
  answer: ReactNode;
  scope: ReactNode;
  tips: ReactNode[];
  actions?: ReactNode;
}) {
  return (
    <header className="relative overflow-hidden rounded-2xl border border-border bg-surface">
      <div aria-hidden="true" className="bg-grid absolute inset-0 opacity-40" />
      <div className="relative flex flex-col gap-4 px-6 py-6 md:px-8">
        <div className="flex flex-wrap items-center gap-2">
          <p className="eyebrow">{scope}</p>
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex max-w-3xl min-w-0 flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-balance text-text md:text-3xl">
              {title}
            </h1>
            <p className="text-[15px] leading-relaxed text-text-2">{answer}</p>
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
        <ul className="grid gap-2 md:grid-cols-3">
          {tips.map((tip, i) => (
            <li
              key={i}
              className="flex gap-2.5 rounded-lg border border-border bg-surface-2/70 px-3 py-2.5 text-[13px] leading-snug text-text-2"
            >
              <span
                aria-hidden="true"
                className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-border-strong text-[11px] font-semibold text-text"
              >
                {i + 1}
              </span>
              <span>{tip}</span>
            </li>
          ))}
        </ul>
      </div>
    </header>
  );
}
