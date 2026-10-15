import "@testing-library/jest-dom/vitest";
import "@/shared/i18n";

import { cleanup, configure } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, vi } from "vitest";

import { useUi } from "@/app/ui-store";
import { useSettings } from "@/features/settings/store";

// lazy pages are transformed on first use: give them time
configure({ asyncUtilTimeout: 8000 });

// jsdom has no canvas nor layout: charts render as their text alternative
vi.mock("@/shared/charts/EChart", () => ({
  EChart: ({ label }: { label: string }) =>
    createElement("div", { role: "img", "aria-label": label }),
}));
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

afterEach(() => {
  cleanup();
  useSettings.getState().reset();
  useUi.setState({ sidebarCollapsed: false, assistantOpen: false });
  window.localStorage.clear();
});
