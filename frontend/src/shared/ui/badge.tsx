import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/shared/lib/cn";

/** Traffic tones carry meaning: always pair them with a word or an icon. */
export const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-none px-2 py-0.5 text-xs font-medium [&_svg]:size-3.5",
  {
    variants: {
      tone: {
        neutral: "bg-surface-3 text-text-2",
        accent: "bg-accent-soft text-accent",
        flow: "bg-flow-soft text-flow",
        dense: "bg-dense-soft text-dense",
        jam: "bg-jam-soft text-jam",
        emergency: "bg-emergency-soft text-emergency",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
