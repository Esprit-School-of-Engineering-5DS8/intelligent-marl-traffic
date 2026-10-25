import type { ComponentProps } from "react";

import { cn } from "@/shared/lib/cn";

export function Kbd({ className, ...props }: ComponentProps<"kbd">) {
  return (
    <kbd
      className={cn(
        "rounded-none border border-border-strong bg-surface-2 px-1.5 font-mono text-[11px] text-muted",
        className,
      )}
      {...props}
    />
  );
}
