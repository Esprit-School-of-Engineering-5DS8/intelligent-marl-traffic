import {
  Bot,
  BrainCircuit,
  Building2,
  ChartColumn,
  Cuboid,
  FlaskConical,
  Footprints,
  House,
  LayoutDashboard,
  MapPinned,
  MessagesSquare,
  Scale,
  Settings,
  ShieldHalf,
  Siren,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type PageKey =
  | "home"
  | "howItWorks"
  | "finalController"
  | "llm"
  | "robustness"
  | "cities"
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
  key: "presentation" | "exploration" | "tools";
  items: NavItem[];
}

/**
 * One entry per page; the router, the sidebar and the command palette all read this list.
 * "Présentation" is the defence, in the order of the talk: one page per question.
 */
export const NAV: NavGroup[] = [
  {
    key: "presentation",
    items: [
      { key: "home", path: "/", icon: House },
      { key: "howItWorks", path: "/how-it-works", icon: Workflow },
      { key: "finalController", path: "/final-controller", icon: Scale },
      { key: "llm", path: "/llm", icon: MessagesSquare },
      { key: "robustness", path: "/robustness", icon: ShieldHalf },
      { key: "cities", path: "/cities", icon: Building2 },
    ],
  },
  {
    key: "exploration",
    items: [
      { key: "overview", path: "/overview", icon: LayoutDashboard },
      { key: "analytics", path: "/analytics", icon: ChartColumn },
      { key: "liveMap", path: "/live-map", icon: MapPinned },
      { key: "simulation3d", path: "/simulation-3d", icon: Cuboid },
      { key: "scenarios", path: "/scenarios", icon: FlaskConical },
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
