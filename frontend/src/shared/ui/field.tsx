import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

/** Labelled native select: keyboard and screen-reader support come with the platform. */
export function SelectField({
  id,
  label,
  help,
  className,
  children,
  ...props
}: ComponentProps<"select"> & { id: string; label: string; help?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-text">
        {label}
      </label>
      <select
        id={id}
        aria-describedby={help ? `${id}-help` : undefined}
        className={cn("select-control w-full text-sm", className)}
        {...props}
      >
        {children}
      </select>
      {help ? (
        <p id={`${id}-help`} className="text-xs text-muted">
          {help}
        </p>
      ) : null}
    </div>
  );
}
