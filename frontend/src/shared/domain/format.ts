import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useSettings } from "@/features/settings/store";
import type { Cell } from "@/shared/schemas";

import { methodLabel } from "./methods";
import { metricInfo, type Unit } from "./metrics";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Translation with a key built at run time (metric, scenario... names). */
export function useTx(): Translate {
  const { t } = useTranslation();
  return t as unknown as Translate;
}

const NO_UNIT: ReadonlySet<Unit> = new Set(["count", "ratio"]);

/** Numbers, units and names in the user's language and units (settings). */
export function useFormat() {
  const { i18n } = useTranslation();
  const tx = useTx();
  const timeUnit = useSettings((s) => s.timeUnit);
  const speedUnit = useSettings((s) => s.speedUnit);
  const language = i18n.language;

  return useMemo(() => {
    // Western digits in Arabic too: the same digits as the charts and the report
    const locale = language === "ar" ? "ar-u-nu-latn" : language;
    const formatters = new Map<string, Intl.NumberFormat>();
    const nf = (digits: number, signed = false) => {
      const key = `${digits}${signed}`;
      let f = formatters.get(key);
      if (!f) {
        f = new Intl.NumberFormat(locale, {
          maximumFractionDigits: digits,
          minimumFractionDigits: 0,
          signDisplay: signed ? "exceptZero" : "auto",
        });
        formatters.set(key, f);
      }
      return f;
    };
    const valid = (v: number | null | undefined): v is number =>
      typeof v === "number" && Number.isFinite(v);
    const autoDigits = (v: number) => (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2);

    const number = (v: number | null | undefined, digits?: number) =>
      valid(v) ? nf(digits ?? autoDigits(v)).format(v) : "–";
    const unitLabel = (unit: Unit) =>
      NO_UNIT.has(unit)
        ? ""
        : unit === "s"
          ? tx(timeUnit === "min" ? "units.min" : "units.s")
          : tx(`units.${unit}`);
    const convert = (v: number, unit: Unit) => (unit === "s" && timeUnit === "min" ? v / 60 : v);
    const metricValue = (v: number | null | undefined, metric: string) => {
      if (!valid(v)) return null;
      return convert(v, metricInfo(metric).unit);
    };
    const metric = (v: number | null | undefined, name: string, digits?: number) => {
      const value = metricValue(v, name);
      if (value === null) return "–";
      const unit = unitLabel(metricInfo(name).unit);
      const text = nf(digits ?? autoDigits(value)).format(value);
      return unit === "%" ? `${text} %` : unit ? `${text} ${unit}` : text;
    };
    const pct = (v: number | null | undefined, digits = 1, signed = true) =>
      valid(v) ? `${nf(digits, signed).format(v)} %` : "–";
    const speed = (metresPerSecond: number) =>
      speedUnit === "kmh"
        ? `${nf(0).format(metresPerSecond * 3.6)} ${tx("units.kmh")}`
        : `${nf(1).format(metresPerSecond)} ${tx("units.ms_speed")}`;
    const clock = (seconds: number) => {
      const s = Math.max(0, Math.round(seconds));
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const r = s % 60;
      const mm = String(m).padStart(2, "0");
      const ss = String(r).padStart(2, "0");
      return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
    };
    const metricName = (m: string) => tx(`metrics.${m}`, { defaultValue: m });
    const metricUnit = (m: string) => unitLabel(metricInfo(m).unit);
    const metricTitle = (m: string) => {
      const unit = metricUnit(m);
      return unit ? `${metricName(m)} (${unit})` : metricName(m);
    };
    const scenarioName = (s: string) => tx(`scenarios.${s}`, { defaultValue: s });
    const demandName = (d: string) => tx(`demands.${d}`, { defaultValue: d });
    const networkName = (n: string) => tx(`networks.${n}`, { defaultValue: n });
    const cellName = (c: Cell) =>
      `${networkName(c.network)} · ${scenarioName(c.scenario)} · ${demandName(c.demand)}`;
    const date = (iso: string) =>
      new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(
        new Date(iso),
      );

    return {
      locale,
      number,
      metric,
      metricValue,
      pct,
      speed,
      clock,
      date,
      unitLabel,
      metricName,
      metricUnit,
      metricTitle,
      methodName: methodLabel,
      scenarioName,
      demandName,
      networkName,
      cellName,
    };
  }, [language, timeUnit, speedUnit, tx]);
}

export type Format = ReturnType<typeof useFormat>;
