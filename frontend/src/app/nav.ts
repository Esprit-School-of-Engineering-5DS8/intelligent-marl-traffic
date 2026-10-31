import {
  Bot,
  BrainCircuit,
  ChartColumn,
  Cuboid,
  FlaskConical,
  Footprints,
  House,
  LayoutDashboard,
  MapPinned,
  Scale,
  Settings,
  ShieldHalf,
  Siren,
  type LucideIcon,
} from "lucide-react";

export type PageKey =
  | "home"
  | "finalController"
  | "robustness"
  | "overview"
  | "analytics"
  | "liveMap"
  | "simulation3d"
  | "scenarios"
  | "agents"
  | "pedestrians"
  | "emergency"
  | "assistant"
  | "settings";

export interface NavItem {
  key: PageKey;
  path: string;
  icon: LucideIcon;
}

export interface NavGroup {
  key: "synthesis" | "results" | "demo" | "operations" | "tools";
  items: NavItem[];
}

/** One entry per page; the router, the sidebar and the command palette all read this list. */
export const NAV: NavGroup[] = [
  {
    key: "synthesis",
    items: [{ key: "home", path: "/", icon: House }],
  },
  {
    key: "results",
    items: [
      { key: "finalController", path: "/final-controller", icon: Scale },
      { key: "robustness", path: "/robustness", icon: ShieldHalf },
      { key: "overview", path: "/overview", icon: LayoutDashboard },
      { key: "analytics", path: "/analytics", icon: ChartColumn },
    ],
  },
  {
    key: "demo",
    items: [
      { key: "liveMap", path: "/live-map", icon: MapPinned },
      { key: "simulation3d", path: "/simulation-3d", icon: Cuboid },
      { key: "scenarios", path: "/scenarios", icon: FlaskConical },
    ],
  },
  {
    key: "operations",
    items: [
      { key: "emergency", path: "/emergency", icon: Siren },
      { key: "pedestrians", path: "/pedestrians", icon: Footprints },
      { key: "agents", path: "/agents", icon: BrainCircuit },
    ],
  },
  {
    key: "tools",
    items: [
      { key: "assistant", path: "/assistant", icon: Bot },
      { key: "settings", path: "/settings", icon: Settings },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV.flatMap((group) => group.items);
