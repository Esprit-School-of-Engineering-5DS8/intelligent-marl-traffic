import type { ChartTokens } from "./tokens";

/**
 * The dashboard's chart theme, shared by every chart: recessive axes and grid, ink-coloured
 * text (never the series colour), one tooltip style. Built from the theme's tokens, so the
 * light and dark themes each get their own steps.
 */
export function baseAxes(t: ChartTokens) {
  const axis = {
    axisLine: { lineStyle: { color: t.borderStrong } },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 11, fontFamily: t.font },
    splitLine: { lineStyle: { color: t.border, opacity: 0.7 } },
    nameTextStyle: { color: t.muted, fontSize: 11, fontFamily: t.font },
  };
  return {
    axis,
    tooltip: {
      backgroundColor: t.surface2,
      borderColor: t.borderStrong,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: t.text, fontSize: 12, fontFamily: t.font },
      extraCssText: "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.18);",
      confine: true,
    },
    legend: {
      textStyle: { color: t.text2, fontSize: 12, fontFamily: t.font },
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 8,
    },
  };
}

/** A row of a tooltip: a colour mark, a name and a value, in the text's own colour. */
export function tooltipRow(color: string, name: string, value: string, dashed = false): string {
  const mark = dashed
    ? `<span style="display:inline-block;width:12px;border-top:2px dashed ${color};margin-inline-end:6px;vertical-align:middle"></span>`
    : `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-inline-end:6px"></span>`;
  return `<div style="display:flex;align-items:center;gap:4px;justify-content:space-between"><span>${mark}${escapeHtml(name)}</span><b style="margin-inline-start:12px;font-variant-numeric:tabular-nums">${escapeHtml(value)}</b></div>`;
}

export function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}
