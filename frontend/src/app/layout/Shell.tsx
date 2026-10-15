import { Suspense, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation } from "react-router";

import { ErrorBoundary } from "@/app/ErrorBoundary";
import { useUi } from "@/app/ui-store";
import { AssistantPanel } from "@/features/assistant/AssistantPanel";
import { PageSkeleton } from "@/shared/ui/skeleton";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

function useAssistantShortcut(): void {
  const setOpen = useUi((s) => s.setAssistantOpen);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useUi.getState().assistantOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);
}

export function Shell() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  useAssistantShortcut();

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
        <main id="main" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto p-6 outline-none">
          {/* keyed on the route: a crash stays on its page and leaving the page clears it */}
          <ErrorBoundary key={pathname}>
            <Suspense fallback={<PageSkeleton label={t("common.loading")} />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      <AssistantPanel />
    </div>
  );
}
