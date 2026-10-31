import { Minus, Plus } from "lucide-react";
import { useEffect, useState, type CSSProperties } from "react";

import { cn } from "@/shared/lib/cn";

/**
 * Number input with the designed +/- stepper. It keeps a local draft so the field can be
 * cleared while typing, then commits a finite number and normalises on blur.
 */
export function NumberField({
  id,
  value,
  onChange,
  min,
  max,
  step = 1,
  className,
  ariaLabel,
  disabled,
  style,
}: {
  id?: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
  ariaLabel?: string;
  disabled?: boolean;
  style?: CSSProperties;
}) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const clamp = (next: number) => {
    let result = next;
    if (min !== undefined) result = Math.max(min, result);
    if (max !== undefined) result = Math.min(max, result);
    return result;
  };

  const commit = (next: number) => {
    const result = clamp(next);
    setDraft(String(result));
    onChange(result);
  };

  const onInput = (raw: string) => {
    setDraft(raw);
    if (raw.trim() === "") return;
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) onChange(parsed);
  };

  return (
    <div className={cn("relative flex min-w-0 items-center", className)} style={style}>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        value={draft}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(event) => onInput(event.target.value)}
        onBlur={() => setDraft(String(value))}
        className="input-control number-control w-full font-mono text-xs"
      />
      <div className="number-stepper">
        <button
          type="button"
          aria-label="Increase value"
          disabled={disabled || (max !== undefined && value >= max)}
          onClick={() => commit(value + step)}
        >
          <Plus aria-hidden="true" className="size-3" />
        </button>
        <button
          type="button"
          aria-label="Decrease value"
          disabled={disabled || (min !== undefined && value <= min)}
          onClick={() => commit(value - step)}
        >
          <Minus aria-hidden="true" className="size-3" />
        </button>
      </div>
    </div>
  );
}
