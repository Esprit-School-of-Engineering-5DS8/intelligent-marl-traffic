import { Suspense, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation } from "react-router";

import { CommandPalette } from "@/app/command/CommandPalette";
import { ErrorBoundary } from "@/app/ErrorBoundary";
import { useUi } from "@/app/ui-store";
import { AssistantPanel } from "@/features/assistant/AssistantPanel";
import { useLiveSocket } from "@/shared/api/live-socket";
import { PageSkeleton } from "@/shared/ui/skeleton";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/** Ctrl+K (Cmd+K): the command palette, from anywhere, the assistant panel included. */
function usePaletteShortcut(): void {
  const setOpen = useUi((s) => s.setPaletteOpen);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        const ui = useUi.getState();
        if (!ui.paletteOpen) ui.setAssistantOpen(false);
        setOpen(!ui.paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);
}

export function Shell() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  usePaletteShortcut();
  useLiveSocket();

  return (
    <div className="flex h-dvh overflow-hidden bg-bg text-text">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-accent px-3 py-2 text-accent-ink focus:not-sr-only focus:absolute focus:start-3 focus:top-3"
      >
        {t("app.skipToContent")}
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main
          id="main"
          tabIndex={-1}
          className="min-h-0 flex-1 overflow-y-auto px-4 py-6 outline-none md:px-8 md:py-8"
        >
          {/* keyed on the route: a crash stays on its page and leaving the page clears it */}
          <ErrorBoundary key={pathname}>
            <Suspense fallback={<PageSkeleton label={t("common.loading")} />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      <AssistantPanel />
      <CommandPalette />
    </div>
  );
}
