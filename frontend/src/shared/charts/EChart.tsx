import { useEffect, useRef } from "react";

import { useResolvedTheme } from "@/app/theme";

import { echarts, type ChartOption } from "./echarts";
import { readTokens, type ChartTokens } from "./tokens";

export type OptionBuilder = (tokens: ChartTokens) => ChartOption;

const reducedMotion = () =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * One ECharts instance. The option is built from the theme's colours, so switching the
 * theme redraws the chart; the canvas follows the size of its box.
 */
export function EChart({
  build,
  height = 320,
  label,
  onClick,
}: {
  build: OptionBuilder;
  height?: number;
  /** Text alternative of the chart for screen readers. */
  label: string;
  onClick?: (params: { name?: string; seriesName?: string; data?: unknown }) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<ReturnType<typeof echarts.init> | null>(null);
  const theme = useResolvedTheme();
  const clickRef = useRef(onClick);

  useEffect(() => {
    clickRef.current = onClick;
  }, [onClick]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const instance = echarts.init(el, undefined, { renderer: "canvas" });
    chart.current = instance;
    instance.on("click", (params) => clickRef.current?.(params as never));
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const tokens = readTokens();
    const option = build(tokens);
    chart.current?.setOption(
      {
        animation: !reducedMotion(),
        textStyle: { fontFamily: tokens.font, color: tokens.text2 },
        aria: { enabled: true },
        ...option,
      },
      { notMerge: true },
    );
  }, [build, theme]);

  return <div ref={box} role="img" aria-label={label} style={{ height }} className="w-full" />;
}
