import { Check } from "lucide-react";
import { useId, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { compareCells } from "@/shared/domain/cells";
import { useFormat } from "@/shared/domain/format";
import { methodColor, sortMethods } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import type { Cell, Meta } from "@/shared/schemas";

const selectClass =
  "h-9 min-w-0 rounded-md border border-border-strong bg-surface-2 px-2 text-sm text-text";

function Select({
  label,
  value,
  options,
  onChange,
  className,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <label htmlFor={id} className="text-xs font-medium text-text-2">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={selectClass}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Network, scenario and demand, limited to the combinations we evaluated: changing the
 * network keeps the scenario and demand when they exist there, otherwise takes the first.
 */
export function CellPicker({
  meta,
  value,
  onChange,
  filter,
}: {
  meta: Meta;
  value: Cell;
  onChange: (cell: Cell) => void;
  filter?: (cell: Cell) => boolean;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const cells = useMemo(
    () => meta.cells.filter((c) => !filter || filter(c)).sort(compareCells),
    [meta, filter],
  );
  const unique = (xs: string[]) => [...new Set(xs)];
  const networks = unique(cells.map((c) => c.network));
  const scenarios = unique(cells.filter((c) => c.network === value.network).map((c) => c.scenario));
  const demands = unique(
    cells
      .filter((c) => c.network === value.network && c.scenario === value.scenario)
      .map((c) => c.demand),
  );

  const pick = (patch: Partial<Cell>) => {
    const want = { ...value, ...patch };
    const match =
      cells.find(
        (c) =>
          c.network === want.network && c.scenario === want.scenario && c.demand === want.demand,
      ) ??
      cells.find((c) => c.network === want.network && c.scenario === want.scenario) ??
      cells.find((c) => c.network === want.network && c.demand === want.demand) ??
      cells.find((c) => c.network === want.network);
    if (match) onChange({ network: match.network, scenario: match.scenario, demand: match.demand });
  };

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Select
        label={t("filters.network")}
        value={value.network}
        options={networks.map((n) => ({ value: n, label: f.networkName(n) }))}
        onChange={(network) => pick({ network })}
      />
      <Select
        label={t("filters.scenario")}
        value={value.scenario}
        options={scenarios.map((s) => ({ value: s, label: f.scenarioName(s) }))}
        onChange={(scenario) => pick({ scenario })}
      />
      <Select
        label={t("filters.demand")}
        value={value.demand}
        options={demands.map((d) => ({ value: d, label: f.demandName(d) }))}
        onChange={(demand) => pick({ demand })}
      />
    </div>
  );
}

export function MethodSelect({
  label,
  value,
  methods,
  onChange,
}: {
  label: string;
  value: string;
  methods: string[];
  onChange: (method: string) => void;
}) {
  const f = useFormat();
  const options = sortMethods(methods).map((m) => ({ value: m, label: f.methodName(m) }));
  if (!methods.includes(value) && value)
    options.unshift({ value, label: `${f.methodName(value)} (–)` });
  return <Select label={label} value={value} options={options} onChange={onChange} />;
}

export function MetricSelect({
  label,
  value,
  metrics,
  onChange,
}: {
  label: string;
  value: string;
  metrics: string[];
  onChange: (metric: string) => void;
}) {
  const f = useFormat();
  return (
    <Select
      label={label}
      value={value}
      options={metrics.map((m) => ({ value: m, label: f.metricName(m) }))}
      onChange={onChange}
    />
  );
}

/** Toggle buttons, one per controller, in the colour of its curves. */
export function MethodChips({
  label,
  methods,
  selected,
  onToggle,
}: {
  label: string;
  methods: string[];
  selected: string[];
  onToggle: (method: string) => void;
}) {
  const f = useFormat();
  return (
    <fieldset className="flex min-w-0 flex-col gap-1">
      <legend className="mb-1 text-xs font-medium text-text-2">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {sortMethods(methods).map((m) => {
          const on = selected.includes(m);
          return (
            <button
              key={m}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(m)}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors",
                on
                  ? "border-border-strong bg-surface-3 text-text"
                  : "border-border text-muted hover:text-text",
              )}
            >
              <span
                aria-hidden="true"
                className="size-2.5 rounded-full"
                style={{
                  background: on ? methodColor(m) : "transparent",
                  border: `2px solid ${methodColor(m)}`,
                }}
              />
              {f.methodName(m)}
              {on ? <Check aria-hidden="true" className="size-3" /> : null}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export { Select };
