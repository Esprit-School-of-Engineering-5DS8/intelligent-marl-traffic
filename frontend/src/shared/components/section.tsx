import { motion } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

/** A titled block of a results page, faded in when the page opens. */
export function Section({
  id,
  title,
  description,
  badges,
  actions,
  children,
  className,
}: {
  id?: string;
  title: string;
  description?: ReactNode;
  badges?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <motion.section
      id={id}
      aria-labelledby={headingId}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className={cn("flex scroll-mt-6 flex-col gap-4", className)}
    >
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex max-w-3xl min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id={headingId} className="text-lg font-semibold tracking-tight text-text">
              {title}
            </h2>
            {badges}
          </div>
          {description ? (
            <div className="text-sm leading-relaxed text-text-2">{description}</div>
          ) : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      {children}
    </motion.section>
  );
}

/** A plain panel: the surface every chart and table of the new pages sits on. */
export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-border bg-surface p-4 md:p-5", className)}>
      {children}
    </div>
  );
}
