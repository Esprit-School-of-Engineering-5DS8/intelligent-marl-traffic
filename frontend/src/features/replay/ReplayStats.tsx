import { useTranslation } from "react-i18next";

import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import type { Replay } from "@/shared/schemas";

import { sceneAt, sceneStats, type Side } from "./scene";
import { usePlayback } from "./store";

const KPIS = [
  "mean_travel_time",
  "mean_waiting_time",
  "ev_delay",
  "ped_mean_waiting_time",
  "co2_total_kg",
];

/** Live counts at the current moment and the full episode's results, per controller. */
export function ReplayStats({ replay, sides }: { replay: Replay; sides: Side[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  // once per simulated second is enough for counts
  const time = usePlayback((s) => Math.floor(s.time));
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {sides.map((side) => {
        const data = replay.sides[side];
        const name = data.label ?? f.methodName(data.method);
        const stats = sceneStats(sceneAt(replay, side, time));
        const kpis = KPIS.filter((k) => data.kpis[k] !== null && data.kpis[k] !== undefined);
        return (
          <section
            key={side}
            aria-label={name}
            className="rounded-lg border border-border bg-surface p-3.5"
            style={{ borderTopColor: methodColor(data.method), borderTopWidth: 3 }}
          >
            <h3 className="mb-2.5 truncate text-sm font-semibold text-text">{name}</h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Kpi label={t("replay.vehicles")} value={f.number(stats.vehicles, 0)} />
              <Kpi
                label={t("replay.halted")}
                value={f.number(stats.halted, 0)}
                tone={stats.halted > stats.vehicles * 0.4 ? "text-jam" : undefined}
              />
              <Kpi label={t("replay.meanSpeed")} value={f.speed(stats.meanSpeed)} />
              <Kpi label={t("replay.persons")} value={f.number(stats.persons, 0)} />
            </div>
            {kpis.length ? (
              <>
                <p className="mt-3 mb-1.5 text-[11px] font-medium tracking-wide text-muted uppercase">
                  {t("replay.kpisOfRun")}
                </p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {kpis.map((k) => (
                    <Kpi key={k} label={f.metricName(k)} value={f.metric(data.kpis[k], k)} />
                  ))}
                </div>
              </>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-md border border-border bg-surface-2 px-2.5 py-2">
      <span className="truncate text-[11px] text-muted" title={label}>
        {label}
      </span>
      <span className={cn("tabular text-base leading-tight font-semibold", tone ?? "text-text")}>
        {value}
      </span>
    </div>
  );
}
