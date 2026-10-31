import { animate, useReducedMotion } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

/**
 * A number that counts up once when the page opens (about a second), then stays at its
 * final value; with reduced motion, or before the animation starts, the final value shows.
 */
export function AnimatedNumber({
  value,
  format,
  className,
}: {
  value: number;
  format: (v: number) => string;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState<number | null>(null);

  useEffect(() => {
    if (reduce) return;
    const controls = animate(0, value, {
      duration: 1.1,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: setShown,
    });
    return () => controls.stop();
  }, [reduce, value]);

  const visible = reduce || shown === null ? value : shown;
  return <span className={cn("tabular", className)}>{format(visible)}</span>;
}

/**
 * One key number with what it means, its comparison and its evidence. The value is the
 * headline; everything else stays in ink so that the number reads first.
 */
export function StatTile({
  label,
  value,
  unit,
  context,
  badges,
  footer,
  accent,
  className,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  context?: ReactNode;
  badges?: ReactNode;
  footer?: ReactNode;
  /** a thin bar in a controller's colour at the top of the tile */
  accent?: string;
  className?: string;
}) {
  return (
    <section
      aria-label={label}
      className={cn(
        "relative flex flex-col gap-3 overflow-hidden rounded-xl border border-border bg-surface p-5",
        className,
      )}
    >
      {accent ? (
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-0.5"
          style={{ background: accent }}
        />
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="max-w-[28ch] text-sm leading-snug font-medium text-text-2">{label}</h3>
        {badges ? <div className="flex flex-wrap gap-1.5">{badges}</div> : null}
      </div>
      <p className="flex items-baseline gap-1.5 text-4xl font-semibold tracking-tight text-text md:text-5xl">
        {value}
        {unit ? <span className="text-xl font-medium text-text-2">{unit}</span> : null}
      </p>
      {context ? <div className="text-sm leading-relaxed text-text-2">{context}</div> : null}
      {footer ? <div className="mt-auto pt-1">{footer}</div> : null}
    </section>
  );
}
