import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import type { RouteObject } from "react-router";

import { ErrorPanel } from "./ErrorBoundary";
import { Shell } from "./layout/Shell";
import { NAV, type PageKey } from "./nav";
import { NotFound } from "./NotFound";

// one chunk per page: the first screen only downloads the shell and the page it shows
const PAGES: Record<PageKey, LazyExoticComponent<ComponentType>> = {
  overview: lazy(() => import("@/features/overview/OverviewPage")),
  liveMap: lazy(() => import("@/features/live-map/LiveMapPage")),
  simulation3d: lazy(() => import("@/features/simulation-3d/Simulation3dPage")),
  scenarios: lazy(() => import("@/features/scenarios/ScenariosPage")),
  agents: lazy(() => import("@/features/agents/AgentsPage")),
  pedestrians: lazy(() => import("@/features/pedestrians/PedestriansPage")),
  emergency: lazy(() => import("@/features/emergency/EmergencyPage")),
  analytics: lazy(() => import("@/features/analytics/AnalyticsPage")),
  assistant: lazy(() => import("@/features/assistant/AssistantPage")),
  settings: lazy(() => import("@/features/settings/SettingsPage")),
};

const pageRoutes: RouteObject[] = NAV.flatMap((group) => group.items).map(({ key, path }) => {
  const Page = PAGES[key];
  return path === "/" ? { index: true, element: <Page /> } : { path, element: <Page /> };
});

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Shell />,
    // only reached if the shell itself fails; page errors stay inside the shell
    errorElement: (
      <div className="p-6">
        <ErrorPanel onRetry={() => window.location.reload()} />
      </div>
    ),
    children: [...pageRoutes, { path: "*", element: <NotFound /> }],
  },
];
