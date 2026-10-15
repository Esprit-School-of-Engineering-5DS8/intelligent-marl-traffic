import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { usePedestrianGreens } from "@/shared/api/queries";
import { lines } from "@/shared/charts/builders";
import { ChartCard } from "@/shared/charts/ChartCard";
import { EChart } from "@/shared/charts/EChart";
import type { ChartTokens } from "@/shared/charts/tokens";
import { EmptyData, QueryState } from "@/shared/components/QueryState";
import { ScenarioFocus, type FocusConfig } from "@/shared/components/ScenarioFocus";
import { cellKey } from "@/shared/domain/cells";
import { useFormat } from "@/shared/domain/format";
import { methodColor, sortMethods } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import { useRtl } from "@/shared/lib/use-rtl";
import type { Cell, PedestrianGreens } from "@/shared/schemas";
import { PageHeader } from "@/shared/ui/page-header";

export default function PedestriansPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.pedestrians.title"));
  const config: FocusConfig = {
    scenario: "pedestrians",
    kpis: [
      "ped_mean_waiting_time",
      "ped_p95_waiting_time",
      "ped_max_waiting_time",
      "ped_crossings_in_green_pct",
      "mean_waiting_time",
      "person_weighted_delay",
    ],
    metrics: [
      "ped_mean_waiting_time",
      "ped_p95_waiting_time",
      "ped_max_waiting_time",
      "ped_crossings_in_green_pct",
      "ped_green_slope_s_per_person",
    ],
    tradeoff: {
      x: "mean_waiting_time",
      y: "ped_mean_waiting_time",
      title: t("pedestrians.tradeoff"),
      text: t("pedestrians.tradeoffText"),
    },
    defaultController: "coop_full",
    defaultReference: "ped_rule_mp",
  };
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("pages.pedestrians.title")}
        description={t("pages.pedestrians.description")}
      />
      <ScenarioFocus config={config}>{(cell) => <Greens cell={cell} />}</ScenarioFocus>
    </div>
  );
}

function Greens({ cell }: { cell: Cell }) {
  const { t } = useTranslation();
  const query = usePedestrianGreens();
  return (
    <ChartCard title={t("pedestrians.greens")} description={t("pedestrians.greensText")}>
      <QueryState query={query} height={300}>
        {(greens) => <GreensChart greens={greens} cell={cell} />}
      </QueryState>
    </ChartCard>
  );
}

function GreensChart({ greens, cell }: { greens: PedestrianGreens; cell: Cell }) {
  const { t } = useTranslation();
  const f = useFormat();
  const rtl = useRtl();
  const data = greens.cells[cellKey(cell)];
  const methods = data ? sortMethods(Object.keys(data)) : [];
  const crowd = [...new Set(methods.flatMap((m) => data?.[m]?.crowd ?? []))].sort((a, b) => a - b);
  const build = useCallback(
    (tk: ChartTokens) =>
      lines(tk, {
        x: crowd,
        series: methods.map((m) => ({
          name: f.methodName(m),
          color: methodColor(m),
          data: crowd.map((c) => {
            const d = data?.[m];
            const i = d ? d.crowd.indexOf(c) : -1;
            return d && i !== -1 ? (d.meanDuration[i] ?? null) : null;
          }),
        })),
        xName: t("pedestrians.crowd"),
        yName: t("pedestrians.duration"),
        format: (v) => `${f.number(v, 1)} s`,
        rtl,
      }),
    [crowd, methods, data, f, t, rtl],
  );
  if (!methods.length) return <EmptyData title={t("data.pending")} text={t("data.pendingText")} />;
  return <EChart build={build} height={300} label={t("pedestrians.greens")} />;
}
