import type { CSSProperties } from "react";

import { cn } from "@/shared/lib/cn";

/**
 * Range slider painted with the KEMETRA tokens. The filled portion is driven by
 * `--range-fill`, which the CSS turns into the accent-to-track gradient.
 */
export function RangeInput({
  value,
  min,
  max,
  step,
  onChange,
  className,
  ariaLabel,
  disabled,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  className?: string;
  ariaLabel?: string;
  disabled?: boolean;
}) {
  const span = max - min;
  const fill = span > 0 ? Math.min(100, Math.max(0, ((value - min) / span) * 100)) : 0;

  return (
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      disabled={disabled}
      aria-label={ariaLabel}
      onChange={(event) => onChange(Number(event.target.value))}
      className={cn("range-control", className)}
      style={{ "--range-fill": `${fill}%` } as CSSProperties}
    />
  );
}
