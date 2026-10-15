import type { ChartTokens } from "./tokens";

/** Axis, grid and tooltip styles shared by the dashboard's charts. */
export function baseAxes(t: ChartTokens) {
  const axis = {
    axisLine: { lineStyle: { color: t.border } },
    axisTick: { lineStyle: { color: t.border } },
    axisLabel: { color: t.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: t.border, opacity: 0.6 } },
    nameTextStyle: { color: t.muted, fontSize: 11 },
  };
  return {
    axis,
    tooltip: {
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 12 },
      confine: true,
    },
    legend: {
      textStyle: { color: t.text2, fontSize: 12 },
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 8,
    },
  };
}
