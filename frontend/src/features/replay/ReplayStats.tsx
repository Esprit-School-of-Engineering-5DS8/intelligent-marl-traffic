import { useTranslation } from "react-i18next";

import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
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
        const stats = sceneStats(sceneAt(replay, side, time));
        const kpis = KPIS.filter((k) => data.kpis[k] !== null && data.kpis[k] !== undefined);
        return (
          <section
            key={side}
            aria-label={f.methodName(data.method)}
            className="rounded-lg border border-border bg-surface p-3"
            style={{ borderTopColor: methodColor(data.method), borderTopWidth: 3 }}
          >
            <h3 className="mb-2 text-sm font-semibold text-text">{f.methodName(data.method)}</h3>
            <dl className="tabular grid grid-cols-4 gap-2 text-xs">
              <Stat label={t("replay.vehicles")} value={f.number(stats.vehicles, 0)} />
              <Stat
                label={t("replay.halted")}
                value={f.number(stats.halted, 0)}
                tone={stats.halted > stats.vehicles * 0.4 ? "text-jam" : undefined}
              />
              <Stat label={t("replay.meanSpeed")} value={f.speed(stats.meanSpeed)} />
              <Stat label={t("replay.persons")} value={f.number(stats.persons, 0)} />
            </dl>
            {kpis.length ? (
              <>
                <p className="mt-3 mb-1 text-[11px] text-muted">{t("replay.kpisOfRun")}</p>
                <dl className="tabular grid grid-cols-2 gap-x-3 gap-y-1 text-xs sm:grid-cols-3">
                  {kpis.map((k) => (
                    <Stat key={k} label={f.metricName(k)} value={f.metric(data.kpis[k], k)} />
                  ))}
                </dl>
              </>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex min-w-0 flex-col">
      <dt className="truncate text-[11px] text-muted">{label}</dt>
      <dd className={tone ?? "text-text"}>{value}</dd>
    </div>
  );
}
