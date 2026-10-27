import { useEffect } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { sameCell } from "@/shared/domain/cells";
import { safeStorage } from "@/shared/lib/storage";
import type { Cell, Meta } from "@/shared/schemas";

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

export const DEFAULT_CELL: Cell = { network: "real_district", scenario: "normal", demand: "medium" };

/** Selections shared by the pages, so moving between pages keeps the same scenario. */
export const useFilters = create<FiltersStore>()(
  persist(
    (set) => ({
      cell: DEFAULT_CELL,
      controller: "llm_team",
      reference: "mp",
      controllers: ["mp", "llm", "llm_team"],
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
    { name: "cotraffic-filters", version: 1, storage: createJSONStorage(() => safeStorage) },
  ),
);

/** Keep persisted selections valid when the exported experiment changes. */
export function useReconciledFilters(meta: Meta | undefined): void {
  const cell = useFilters((s) => s.cell);
  const controller = useFilters((s) => s.controller);
  const reference = useFilters((s) => s.reference);
  const controllers = useFilters((s) => s.controllers);
  const setCell = useFilters((s) => s.setCell);
  const setController = useFilters((s) => s.setController);
  const setReference = useFilters((s) => s.setReference);
  const setControllers = useFilters((s) => s.setControllers);

  useEffect(() => {
    if (!meta || meta.cells.length === 0) return;
    const match = meta.cells.find((c) => sameCell(c, cell));
    const current = match ?? meta.cells.find((c) => c.scenario === "normal") ?? meta.cells[0];
    if (!sameCell(current, cell)) {
      setCell({ network: current.network, scenario: current.scenario, demand: current.demand });
    }
    const methods = current.methods;
    if (methods.length && !methods.includes(controller)) {
      setController(methods.includes("llm_team") ? "llm_team" : methods[0]);
    }
    if (methods.length && !methods.includes(reference)) {
      setReference(methods.includes("mp") ? "mp" : methods[0]);
    }
    const kept = controllers.filter((method) => methods.includes(method));
    if (methods.length && (kept.length === 0 || kept.length !== controllers.length)) {
      setControllers(kept.length ? kept : methods);
    }
  }, [
    meta,
    cell,
    controller,
    reference,
    controllers,
    setCell,
    setController,
    setReference,
    setControllers,
  ]);
}
