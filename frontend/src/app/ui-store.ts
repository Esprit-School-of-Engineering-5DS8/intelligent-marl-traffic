import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { safeStorage } from "@/shared/lib/storage";

interface UiStore {
  sidebarCollapsed: boolean;
  assistantOpen: boolean;
  toggleSidebar: () => void;
  setAssistantOpen: (open: boolean) => void;
}

/** Layout state; only the sidebar width is remembered between visits. */
export const useUi = create<UiStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      assistantOpen: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setAssistantOpen: (assistantOpen) => set({ assistantOpen }),
    }),
    {
      name: "kemetra-ui",
      storage: createJSONStorage(() => safeStorage),
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed }),
    },
  ),
);
