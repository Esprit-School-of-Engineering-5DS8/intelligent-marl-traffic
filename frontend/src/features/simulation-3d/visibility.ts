import type { Kind } from "@/features/replay/scene";

/** Which road users the 3D scene draws. Shared by both panels so the pair stays comparable. */
export type Visibility = Record<Kind, boolean> & { pedestrian: boolean };

export const ALL_VISIBLE: Visibility = {
  car: true,
  bus: true,
  emergency: true,
  incident: true,
  pedestrian: true,
};
