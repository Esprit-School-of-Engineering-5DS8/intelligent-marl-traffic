import "@testing-library/jest-dom/vitest";
import "@/shared/i18n";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { useUi } from "@/app/ui-store";
import { useSettings } from "@/features/settings/store";

afterEach(() => {
  cleanup();
  useSettings.getState().reset();
  useUi.setState({ sidebarCollapsed: false, assistantOpen: false });
  window.localStorage.clear();
});
