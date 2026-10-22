import type { Cell } from "@/shared/schemas";

export const cellKey = (c: Cell) => `${c.network}__${c.scenario}__${c.demand}`;

export function parseCellKey(key: string): Cell | null {
  const [network, scenario, demand] = key.split("__");
  return network && scenario && demand ? { network, scenario, demand } : null;
}

export const sameCell = (a: Cell, b: Cell) =>
  a.network === b.network && a.scenario === b.scenario && a.demand === b.demand;

const DEMAND_ORDER = ["low", "medium", "peak", "rush_profile"];
const NETWORK_ORDER = ["grid4x4", "real_district", "grid8x8"];
const SCENARIO_ORDER = [
  "normal",
  "emergency",
  "pedestrians",
  "incident",
  "buses",
  "sensor_noise",
  "comm_dropout_10",
  "comm_dropout_30",
  "comm_dropout_50",
];

const rank = (order: string[], value: string) => {
  const i = order.indexOf(value);
  return i === -1 ? order.length : i;
};

export function compareCells(a: Cell, b: Cell): number {
  return (
    rank(NETWORK_ORDER, a.network) - rank(NETWORK_ORDER, b.network) ||
    rank(SCENARIO_ORDER, a.scenario) - rank(SCENARIO_ORDER, b.scenario) ||
    rank(DEMAND_ORDER, a.demand) - rank(DEMAND_ORDER, b.demand)
  );
}
