import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { safeStorage } from "@/shared/lib/storage";
import type { Cell } from "@/shared/schemas";

interface FiltersStore {
  /** The scenario every analysis page shows (and the assistant receives as context). */
  cell: Cell;
  controller: string;
  reference: string;
  controllers: string[];
  metric: string;
  setCell: (cell: Cell) => void;
  setController: (controller: string) => void;
  setReference: (reference: string) => void;
  toggleController: (controller: string) => void;
  setControllers: (controllers: string[]) => void;
  setMetric: (metric: string) => void;
}

export const DEFAULT_CELL: Cell = { network: "grid4x4", scenario: "normal", demand: "peak" };

/** Selections shared by the pages, so moving between pages keeps the same scenario. */
export const useFilters = create<FiltersStore>()(
  persist(
    (set) => ({
      cell: DEFAULT_CELL,
      controller: "coop_full",
      reference: "ft",
      controllers: ["ft", "act", "mp", "coop", "coop_full"],
      metric: "mean_waiting_time",
      setCell: (cell) => set({ cell }),
      setController: (controller) => set({ controller }),
      setReference: (reference) => set({ reference }),
      toggleController: (controller) =>
        set((s) => ({
          controllers: s.controllers.includes(controller)
            ? s.controllers.filter((c) => c !== controller)
            : [...s.controllers, controller],
        })),
      setControllers: (controllers) => set({ controllers }),
      setMetric: (metric) => set({ metric }),
    }),
    { name: "kemetra-filters", storage: createJSONStorage(() => safeStorage) },
  ),
);
