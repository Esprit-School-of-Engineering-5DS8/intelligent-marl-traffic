import { ToggleGroup } from "radix-ui";

import { cn } from "@/shared/lib/cn";

/** A one-of-several choice drawn as a row of buttons (arrow keys move, one is pressed). */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  className,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <span className="text-xs font-medium text-muted" aria-hidden="true">
        {label}
      </span>
      <ToggleGroup.Root
        type="single"
        aria-label={label}
        value={value}
        onValueChange={(v) => {
          if (v) onChange(v as T);
        }}
        className="inline-flex flex-wrap items-center gap-0.5 rounded-lg border border-border bg-surface-2 p-0.5"
      >
        {options.map((o) => (
          <ToggleGroup.Item
            key={o.value}
            value={o.value}
            className="h-7 rounded-md px-2.5 text-xs font-medium text-text-2 transition-colors hover:text-text data-[state=on]:bg-surface data-[state=on]:text-text data-[state=on]:shadow-sm"
          >
            {o.label}
          </ToggleGroup.Item>
        ))}
      </ToggleGroup.Root>
    </div>
  );
}
