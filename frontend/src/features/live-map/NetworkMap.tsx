import { OrthographicView, type PickingInfo } from "@deck.gl/core";
import { PathLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import DeckGL from "@deck.gl/react";
import { useMemo } from "react";

import { useResolvedTheme } from "@/app/theme";
import {
  footprint,
  sceneAt,
  signalColor,
  signalLinks,
  type Side,
  type VehicleNow,
} from "@/features/replay/scene";
import { usePlayback } from "@/features/replay/store";
import { readTokens } from "@/shared/charts/tokens";
import type { NetworkGeometry, Replay } from "@/shared/schemas";

import type { MapViewState } from "./view";

type RGBA = [number, number, number, number];

function rgb(hex: string, alpha = 255): RGBA {
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((c) => c + c)
          .join("")
      : h;
  const n = parseInt(full.slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, alpha];
}

function palette(theme: "dark" | "light") {
  const t = readTokens();
  const dark = theme === "dark";
  return {
    road: rgb(dark ? "#2a3440" : "#c3ccd6"),
    internal: rgb(dark ? "#26303b" : "#ccd4dc"),
    sidewalk: rgb(dark ? "#4a5663" : "#e8ecf0"),
    crossing: rgb(dark ? "#8a96a3" : "#ffffff"),
    junction: rgb(dark ? "#222b35" : "#cfd7df"),
    junctionSignal: rgb(dark ? "#2b2550" : "#dcd6ff"),
    selected: rgb(t.accent, 200),
    flow: rgb(t.flow),
    dense: rgb(t.dense),
    jam: rgb(t.jam),
    emergency: rgb(t.emergency),
    emergencyAlt: rgb("#ff4d6d"),
    bus: rgb(dark ? "#f5c451" : "#b7791f"),
    incident: rgb("#d946ef"),
    outline: rgb(dark ? "#0a0f14" : "#ffffff"),
    white: rgb("#ffffff"),
    green: rgb("#22c55e"),
    yellow: rgb("#facc15"),
    red: rgb("#ef4444"),
    off: rgb("#64748b"),
    person: rgb(dark ? "#93c5fd" : "#1d4ed8"),
    personWaiting: rgb(dark ? "#fda4af" : "#be123c"),
  };
}

type Palette = ReturnType<typeof palette>;

function vehicleColor(v: VehicleNow, p: Palette, t: number): RGBA {
  if (v.kind === "emergency") return Math.floor(t * 2) % 2 ? p.emergency : p.emergencyAlt;
  if (v.kind === "incident") return p.incident;
  if (v.kind === "bus") return p.bus;
  if (v.speed < 0.5) return p.jam;
  if (v.speed < 5) return p.dense;
  return p.flow;
}

/**
 * The road network with the replayed traffic of one controller: lanes and junctions from
 * the SUMO network, vehicles as oriented footprints coloured by speed, pedestrians, and
 * each signal's state at the stop line. Pan and zoom with the mouse or the keyboard.
 */
export function NetworkMap({
  net,
  replay,
  side,
  viewState,
  onViewState,
  label,
}: {
  net: NetworkGeometry;
  replay: Replay;
  side: Side;
  viewState: MapViewState;
  onViewState: (v: MapViewState) => void;
  label: string;
}) {
  const theme = useResolvedTheme();
  const time = usePlayback((s) => s.time);
  const selected = usePlayback((s) => s.selectedJunction);
  const select = usePlayback((s) => s.selectJunction);
  const colors = useMemo(() => palette(theme), [theme]);
  const links = useMemo(() => signalLinks(net, replay), [net, replay]);
  const lanes = useMemo(() => net.lanes.filter((l) => l.kind !== "crossing"), [net]);
  const crossings = useMemo(() => net.lanes.filter((l) => l.kind === "crossing"), [net]);
  const junctions = useMemo(() => net.junctions.filter((j) => j.shape.length >= 3), [net]);

  const scene = sceneAt(replay, side, time);
  const detailed = viewState.zoom > 1.2;

  const layers = [
    new PolygonLayer({
      id: "junctions",
      data: junctions,
      getPolygon: (j) => j.shape,
      getFillColor: (j) =>
        j.id === selected
          ? colors.selected
          : j.signalised
            ? colors.junctionSignal
            : colors.junction,
      stroked: false,
      pickable: true,
      autoHighlight: true,
      highlightColor: [154, 140, 255, 90],
      updateTriggers: { getFillColor: [selected, colors] },
    }),
    new PathLayer({
      id: "lanes",
      data: lanes,
      getPath: (l) => l.shape,
      getWidth: (l) => l.width,
      widthUnits: "common",
      getColor: (l) =>
        l.allows === "pedestrian"
          ? colors.sidewalk
          : l.kind === "internal"
            ? colors.internal
            : colors.road,
      widthMinPixels: 1.5,
      capRounded: false,
      updateTriggers: { getColor: colors },
    }),
    new PathLayer({
      id: "crossings",
      data: crossings,
      getPath: (l) => l.shape,
      getWidth: (l) => l.width,
      widthUnits: "common",
      getColor: colors.crossing,
      opacity: 0.6,
      updateTriggers: { getColor: colors },
    }),
    new ScatterplotLayer({
      id: "persons",
      data: scene.persons,
      getPosition: (p) => [p.x, p.y],
      getRadius: 0.7,
      radiusUnits: "common",
      radiusMinPixels: 1.5,
      getFillColor: (p) => (p.waiting ? colors.personWaiting : colors.person),
      updateTriggers: { getFillColor: colors },
    }),
    // zoomed out, footprints would be smaller than a pixel: dots with a minimum size instead
    new ScatterplotLayer({
      id: "vehicle-dots",
      visible: !detailed,
      data: scene.vehicles,
      getPosition: (v) => [v.x, v.y],
      getRadius: (v) => (v.kind === "bus" ? 4 : v.kind === "emergency" ? 4 : 2.6),
      radiusUnits: "common",
      radiusMinPixels: 2,
      getFillColor: (v) => vehicleColor(v, colors, time),
      stroked: true,
      getLineColor: (v) => (v.kind === "emergency" ? colors.white : colors.outline),
      lineWidthMinPixels: 0.5,
      updateTriggers: { getFillColor: [time, colors], getLineColor: colors },
    }),
    new PolygonLayer({
      id: "vehicles",
      visible: detailed,
      data: scene.vehicles,
      getPolygon: (v) => footprint(v),
      getFillColor: (v) => vehicleColor(v, colors, time),
      getLineColor: (v) => (v.kind === "emergency" ? colors.white : colors.outline),
      getLineWidth: (v) => (v.kind === "emergency" ? 0.6 : 0.25),
      lineWidthUnits: "common",
      stroked: true,
      updateTriggers: { getFillColor: [time, colors], getLineColor: colors },
    }),
    new ScatterplotLayer({
      id: "signals",
      data: links,
      getPosition: (l) => l.position,
      getRadius: 1.1,
      radiusUnits: "common",
      radiusMinPixels: 1.5,
      stroked: true,
      getLineColor: colors.outline,
      lineWidthMinPixels: 0.5,
      getFillColor: (l) => colors[signalColor(scene.signals[l.slot]?.[l.index])],
      updateTriggers: { getFillColor: [scene.signals, colors] },
    }),
  ];

  return (
    <div role="img" aria-label={label} className="relative h-full w-full">
      <DeckGL
        views={new OrthographicView({ id: "map", flipY: false, controller: true })}
        viewState={viewState}
        onViewStateChange={({ viewState: v }) => onViewState(v as MapViewState)}
        controller={{ dragRotate: false, keyboard: true, doubleClickZoom: true }}
        layers={layers}
        getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
        onClick={(info: PickingInfo) => {
          const j =
            info.layer?.id === "junctions"
              ? (info.object as { id: string; signalised: boolean } | undefined)
              : undefined;
          select(j?.signalised ? j.id : null);
        }}
      />
    </div>
  );
}
