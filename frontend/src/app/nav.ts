import {
  Bot,
  BrainCircuit,
  ChartColumn,
  Cuboid,
  FlaskConical,
  Footprints,
  LayoutDashboard,
  MapPinned,
  Settings,
  Siren,
  type LucideIcon,
} from "lucide-react";

export type PageKey =
  | "overview"
  | "liveMap"
  | "simulation3d"
  | "scenarios"
  | "agents"
  | "pedestrians"
  | "emergency"
  | "analytics"
  | "assistant"
  | "settings";

export interface NavItem {
  key: PageKey;
  path: string;
  icon: LucideIcon;
}

export interface NavGroup {
  key: "supervision" | "analysis" | "operations" | "system";
  items: NavItem[];
}

/** One entry per page; the router and the sidebar both read this list. */
export const NAV: NavGroup[] = [
  {
    key: "supervision",
    items: [
      { key: "overview", path: "/", icon: LayoutDashboard },
      { key: "liveMap", path: "/live-map", icon: MapPinned },
      { key: "simulation3d", path: "/simulation-3d", icon: Cuboid },
    ],
  },
  {
    key: "analysis",
    items: [
      { key: "agents", path: "/agents", icon: BrainCircuit },
      { key: "analytics", path: "/analytics", icon: ChartColumn },
      { key: "assistant", path: "/assistant", icon: Bot },
    ],
  },
  {
    key: "operations",
    items: [
      { key: "scenarios", path: "/scenarios", icon: FlaskConical },
      { key: "pedestrians", path: "/pedestrians", icon: Footprints },
      { key: "emergency", path: "/emergency", icon: Siren },
    ],
  },
  {
    key: "system",
    items: [{ key: "settings", path: "/settings", icon: Settings }],
  },
];
