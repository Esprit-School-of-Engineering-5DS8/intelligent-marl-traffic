import { useTranslation } from "react-i18next";

import { useEmergencyLog } from "@/shared/api/queries";
import { ChartCard } from "@/shared/charts/ChartCard";
import { EmptyData, QueryState } from "@/shared/components/QueryState";
import { ScenarioFocus, type FocusConfig } from "@/shared/components/ScenarioFocus";
import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { Cell, EmergencyLog } from "@/shared/schemas";
import { PageHeader } from "@/shared/ui/page-header";

export default function EmergencyPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.emergency.title"));
  const config: FocusConfig = {
    scenario: "emergency",
    kpis: [
      "ev_delay",
      "ev_travel_time",
      "ev_stops_at_red_mean",
      "ev_eta_abs_error_mean_s",
      "mean_waiting_time",
      "mean_travel_time",
    ],
    metrics: [
      "ev_delay",
      "ev_travel_time",
      "ev_stops_at_red_mean",
      "ev_eta_abs_error_mean_s",
      "mean_waiting_time",
    ],
    tradeoff: {
      x: "mean_waiting_time",
      y: "ev_delay",
      title: t("emergency.sideEffect"),
      text: t("emergency.sideEffectText"),
    },
    defaultController: "coop_full",
    defaultReference: "ev_rule_mp",
  };
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("pages.emergency.title")}
        description={t("pages.emergency.description")}
      />
      <ScenarioFocus config={config}>{(cell) => <Log cell={cell} />}</ScenarioFocus>
    </div>
  );
}

function Log({ cell }: { cell: Cell }) {
  const { t } = useTranslation();
  const query = useEmergencyLog();
  return (
    <ChartCard title={t("emergency.log")} description={t("emergency.logText")}>
      <QueryState query={query} height={200}>
        {(log) => <LogTable log={log} cell={cell} />}
      </QueryState>
    </ChartCard>
  );
}

const num = (v: unknown) => (typeof v === "number" ? v : null);

function LogTable({ log, cell }: { log: EmergencyLog; cell: Cell }) {
  const { t } = useTranslation();
  const f = useFormat();
  const rows = log.vehicles.filter(
    (v) =>
      v.network === cell.network && v.demand === cell.demand && v.scenario.includes("emergency"),
  );
  if (!rows.length) return <EmptyData title={t("data.pending")} text={t("data.pendingText")} />;
  return (
    <div
      tabIndex={0}
      role="region"
      aria-label={t("emergency.log")}
      className="max-h-[420px] overflow-auto rounded-md border border-border"
    >
      <table className="w-full text-xs">
        <caption className="sr-only">{t("emergency.log")}</caption>
        <thead className="sticky top-0 bg-surface-2 text-text-2">
          <tr>
            {[
              t("filters.controller"),
              t("emergency.vehicle"),
              t("emergency.depart"),
              t("emergency.travel"),
              t("emergency.eta"),
              t("emergency.etaError"),
              t("emergency.stops"),
            ].map((h) => (
              <th key={h} scope="col" className="px-2 py-2 text-start font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border">
              <td className="px-2 py-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="size-2 rounded-full"
                    style={{ background: methodColor(r.method) }}
                  />
                  {f.methodName(r.method)} · s{r.seed}
                </span>
              </td>
              <td className="px-2 py-1.5">{String(r.id ?? "–")}</td>
              <td className="px-2 py-1.5">{f.number(num(r.plannedDepart), 0)}</td>
              <td className="px-2 py-1.5">{f.number(num(r.tripTimeS), 0)}</td>
              <td className="px-2 py-1.5">{f.number(num(r.etaS), 0)}</td>
              <td className="px-2 py-1.5">{f.number(num(r.etaErrorS), 0)}</td>
              <td className="px-2 py-1.5">{f.number(num(r.stopsAtRed), 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
