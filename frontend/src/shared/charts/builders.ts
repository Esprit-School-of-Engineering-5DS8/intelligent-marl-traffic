import type { ChartOption } from "./echarts";
import { baseAxes } from "./style";
import type { ChartTokens } from "./tokens";

type Fmt = (v: number) => string;

/** Bars with 95 % confidence whiskers, one bar per category. */
export function barsWithCi(
  t: ChartTokens,
  {
    categories,
    values,
    lo,
    hi,
    colors,
    axisName,
    format,
    rtl,
  }: {
    categories: string[];
    values: (number | null)[];
    lo: (number | null)[];
    hi: (number | null)[];
    colors: string[];
    axisName: string;
    format: Fmt;
    rtl: boolean;
  },
): ChartOption {
  const { axis, tooltip } = baseAxes(t);
  return {
    grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      ...tooltip,
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0;
        const v = values[i];
        const l = lo[i];
        const h = hi[i];
        return `<b>${categories[i]}</b><br/>${v === null || v === undefined ? "–" : format(v)}${
          l !== null && l !== undefined && h !== null && h !== undefined
            ? `<br/><span style="opacity:.7">IC 95 % ${format(l)} – ${format(h)}</span>`
            : ""
        }`;
      },
    },
    xAxis: {
      type: "category",
      data: categories,
      inverse: rtl,
      ...axis,
      axisLabel: { ...axis.axisLabel, interval: 0, rotate: categories.length > 6 ? 30 : 0 },
    },
    yAxis: { type: "value", name: axisName, position: rtl ? "right" : "left", ...axis },
    series: [
      {
        type: "bar",
        barMaxWidth: 44,
        data: values.map((v, i) => ({
          value: v,
          itemStyle: { color: colors[i], borderRadius: [3, 3, 0, 0] },
        })),
      },
      {
        type: "custom",
        name: "ci",
        silent: true,
        renderItem: (_params: unknown, api: CustomApi) => {
          const i = api.value(0) as number;
          const low = lo[i];
          const high = hi[i];
          if (low === null || low === undefined || high === null || high === undefined) return null;
          const top = api.coord([i, high]);
          const bottom = api.coord([i, low]);
          const half = 7;
          const style = { stroke: t.text, lineWidth: 1.5 };
          return {
            type: "group",
            children: [
              {
                type: "line",
                shape: { x1: top[0], y1: top[1], x2: bottom[0], y2: bottom[1] },
                style,
              },
              {
                type: "line",
                shape: { x1: top[0] - half, y1: top[1], x2: top[0] + half, y2: top[1] },
                style,
              },
              {
                type: "line",
                shape: { x1: bottom[0] - half, y1: bottom[1], x2: bottom[0] + half, y2: bottom[1] },
                style,
              },
            ],
          };
        },
        data: categories.map((_, i) => [i]),
        z: 3,
      },
    ],
  };
}

interface CustomApi {
  value: (dim: number) => number | string;
  coord: (point: [number, number]) => [number, number];
  size: (value: [number, number]) => [number, number];
}

/** Lines over a shared x axis (minutes, steps...), with an optional shaded window. */
export function lines(
  t: ChartTokens,
  {
    x,
    series,
    xName,
    yName,
    window,
    format,
    rtl,
    dataZoom = false,
  }: {
    x: number[];
    series: {
      name: string;
      color: string;
      data: (number | null)[];
      dashed?: boolean;
      width?: number;
      opacity?: number;
    }[];
    xName: string;
    yName: string;
    window?: [number, number];
    format: Fmt;
    rtl: boolean;
    dataZoom?: boolean;
  },
): ChartOption {
  const { axis, tooltip, legend } = baseAxes(t);
  return {
    grid: { left: 8, right: 16, top: 40, bottom: dataZoom ? 48 : 8, containLabel: true },
    legend: { ...legend, top: 0, type: "scroll" },
    tooltip: {
      ...tooltip,
      trigger: "axis",
      valueFormatter: (v: number) => (v === null || v === undefined ? "–" : format(v)),
    },
    xAxis: {
      type: "category",
      data: x,
      name: xName,
      nameLocation: "middle",
      nameGap: 26,
      boundaryGap: false,
      inverse: rtl,
      ...axis,
    },
    yAxis: { type: "value", name: yName, position: rtl ? "right" : "left", ...axis },
    dataZoom: dataZoom
      ? [
          { type: "inside" },
          {
            type: "slider",
            height: 18,
            bottom: 8,
            borderColor: t.border,
            textStyle: { color: t.muted },
          },
        ]
      : undefined,
    series: series.map((s, i) => ({
      type: "line",
      name: s.name,
      data: s.data,
      showSymbol: false,
      smooth: 0.2,
      connectNulls: true,
      lineStyle: {
        color: s.color,
        width: s.width ?? 2,
        type: s.dashed ? "dashed" : "solid",
        opacity: s.opacity ?? 1,
      },
      itemStyle: { color: s.color },
      emphasis: { focus: "series" },
      markArea:
        i === 0 && window
          ? {
              silent: true,
              itemStyle: { color: t.muted, opacity: 0.08 },
              data: [[{ xAxis: String(window[0]) }, { xAxis: String(window[1]) }]],
            }
          : undefined,
    })),
  };
}

/** Horizontal intervals around a point estimate, one row per item; zero line marked. */
export function forest(
  t: ChartTokens,
  {
    items,
    xName,
    rtl,
    format,
  }: {
    items: {
      label: string;
      value: number;
      lo: number;
      hi: number;
      color: string;
      significant: boolean;
    }[];
    xName: string;
    rtl: boolean;
    format: Fmt;
  },
): ChartOption {
  const { axis, tooltip } = baseAxes(t);
  const labels = items.map((i) => i.label);
  return {
    grid: { left: 8, right: 24, top: 16, bottom: 32, containLabel: true },
    tooltip: {
      ...tooltip,
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const it = items[p.dataIndex];
        return it
          ? `<b>${it.label}</b><br/>${format(it.value)} [${format(it.lo)} ; ${format(it.hi)}]`
          : "";
      },
    },
    xAxis: {
      type: "value",
      name: xName,
      nameLocation: "middle",
      nameGap: 24,
      inverse: rtl,
      ...axis,
    },
    yAxis: {
      type: "category",
      data: labels,
      inverse: true,
      position: rtl ? "right" : "left",
      ...axis,
      axisLabel: { ...axis.axisLabel, width: 190, overflow: "truncate" },
    },
    series: [
      {
        type: "custom",
        renderItem: (_p: unknown, api: CustomApi) => {
          const i = api.value(0) as number;
          const it = items[i];
          if (!it) return null;
          const a = api.coord([it.lo, i]);
          const b = api.coord([it.hi, i]);
          const c = api.coord([it.value, i]);
          return {
            type: "group",
            children: [
              {
                type: "line",
                shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] },
                style: { stroke: it.color, lineWidth: 2 },
              },
              {
                type: "circle",
                shape: { cx: c[0], cy: c[1], r: 5 },
                style: {
                  fill: it.significant ? it.color : t.surface,
                  stroke: it.color,
                  lineWidth: 2,
                },
              },
            ],
          };
        },
        encode: { x: 1, y: 0 },
        data: items.map((it, i) => [i, it.value]),
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: t.muted, type: "dashed" },
          data: [{ xAxis: 0 }],
          label: { show: false },
        },
      },
    ],
  };
}

/** Rows x columns grid of values, diverging around zero (positive = better). */
export function heatmap(
  t: ChartTokens,
  {
    rows,
    columns,
    values,
    format,
    rtl,
  }: {
    rows: string[];
    columns: string[];
    values: [number, number, number | null][];
    format: Fmt;
    rtl: boolean;
  },
): ChartOption {
  const { axis, tooltip } = baseAxes(t);
  const finite = values.map((v) => v[2]).filter((v): v is number => v !== null);
  const extent = Math.max(5, ...finite.map((v) => Math.abs(v)));
  return {
    grid: { left: 8, right: 16, top: 8, bottom: 56, containLabel: true },
    tooltip: {
      ...tooltip,
      formatter: (p: { data: [number, number, number | null] }) =>
        `<b>${rows[p.data[1]]}</b><br/>${columns[p.data[0]]}<br/>${p.data[2] === null ? "–" : format(p.data[2])}`,
    },
    xAxis: {
      type: "category",
      data: columns,
      inverse: rtl,
      ...axis,
      splitLine: { show: false },
      axisLabel: { ...axis.axisLabel, interval: 0, rotate: 35 },
    },
    yAxis: {
      type: "category",
      data: rows,
      position: rtl ? "right" : "left",
      ...axis,
      splitLine: { show: false },
    },
    visualMap: {
      min: -extent,
      max: extent,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemHeight: 120,
      textStyle: { color: t.muted },
      inRange: { color: [t.jam, t.surface2, t.flow] },
      show: false,
    },
    series: [
      {
        type: "heatmap",
        data: values,
        label: {
          show: true,
          color: t.text,
          fontSize: 10,
          formatter: (p: { data: [number, number, number | null] }) =>
            p.data[2] === null ? "" : format(p.data[2]),
        },
        itemStyle: { borderColor: t.surface, borderWidth: 2 },
      },
    ],
  };
}
