import type { NetworkGeometry } from "@/shared/schemas";

export interface MapViewState {
  target: [number, number, number];
  zoom: number;
}

export function fitView(net: NetworkGeometry, width: number, height: number): MapViewState {
  const [[x0, y0], [x1, y1]] = net.bounds;
  const scale = Math.min(width / Math.max(1, x1 - x0), height / Math.max(1, y1 - y0)) * 0.92;
  return { target: [(x0 + x1) / 2, (y0 + y1) / 2, 0], zoom: Math.log2(scale) };
}
