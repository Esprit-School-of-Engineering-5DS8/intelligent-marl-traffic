import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { ChartCard } from "@/shared/charts/ChartCard";
import type { ChartOption } from "@/shared/charts/echarts";
import { EChart } from "@/shared/charts/EChart";
import { baseAxes } from "@/shared/charts/style";
import type { ChartTokens } from "@/shared/charts/tokens";
import { useFormat } from "@/shared/domain/format";
import { useRtl } from "@/shared/lib/use-rtl";

interface Row {
  time: number;
  requested: number;
  executed: number;
  shield: string;
}

/** Requested and executed phase over time for one intersection; shield corrections marked. */
export function DecisionTimeline({ rows }: { rows: Row[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  const rtl = useRtl();
  const build = useCallback(
    (tk: ChartTokens): ChartOption => {
      const { axis, tooltip, legend } = baseAxes(tk);
      return {
        grid: { left: 8, right: 16, top: 36, bottom: 48, containLabel: true },
        legend: { ...legend, top: 0 },
        tooltip: { ...tooltip, trigger: "axis" },
        xAxis: {
          type: "value",
          name: t("agents.time"),
          nameLocation: "middle",
          nameGap: 26,
          inverse: rtl,
          ...axis,
          axisLabel: { ...axis.axisLabel, formatter: (v: number) => f.clock(v) },
        },
        yAxis: {
          type: "value",
          name: t("agents.phase"),
          minInterval: 1,
          position: rtl ? "right" : "left",
          ...axis,
        },
        dataZoom: [
          { type: "inside" },
          {
            type: "slider",
            height: 18,
            bottom: 8,
            borderColor: tk.border,
            textStyle: { color: tk.muted },
          },
        ],
        series: [
          {
            type: "line",
            name: t("agents.executed"),
            step: "end",
            showSymbol: false,
            data: rows.map((r) => [r.time, r.executed]),
            lineStyle: { color: tk.accent, width: 2 },
            itemStyle: { color: tk.accent },
          },
          {
            type: "scatter",
            name: t("agents.shield"),
            symbolSize: 6,
            data: rows
              .filter((r) => r.shield && r.shield !== "none")
              .map((r) => [r.time, r.requested]),
            itemStyle: { color: tk.dense },
          },
        ],
      };
    },
    [rows, t, f, rtl],
  );
  return (
    <ChartCard title={`${t("agents.executed")} / ${t("agents.shield")}`}>
      <EChart
        build={build}
        height={260}
        label={`${t("agents.executed")} / ${t("agents.shield")}`}
      />
    </ChartCard>
  );
}
