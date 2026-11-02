import * as THREE from "three";

import type { NetworkGeometry } from "@/shared/schemas";

import type { projector } from "./geometry";

type Projector = ReturnType<typeof projector>;

/** Small seeded generator: the same network always gets the same city. */
export function seeded(text: string): () => number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  let a = h >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface Building {
  x: number;
  z: number;
  width: number;
  depth: number;
  /** variant 0 = low (houses), 1 = mid (blocks of flats), 2 = tall (offices) */
  variant: 0 | 1 | 2;
  scaleY: number;
  tone: number;
}
export interface Tree {
  x: number;
  z: number;
  scale: number;
}

const CELL = 3; // metres per cell of the road raster
const LOT = 18; // metres between two building lots
const FRONTAGE = 34; // buildings line the streets up to this distance; courtyards beyond
const SETBACK = 6; // sidewalk + front yard beyond the edge of the roadway

/**
 * Buildings and trees in the blocks between the streets, as in a European city: the roads,
 * sidewalks and junctions are rasterised; buildings line the streets (taller towards the
 * centre of the network), courtyards and small parks fill the inside of the blocks.
 */
export function buildCity(
  net: NetworkGeometry,
  p: Projector,
): { buildings: Building[]; trees: Tree[] } {
  const margin = 60;
  const w = p.width + 2 * margin;
  const d = p.depth + 2 * margin;
  const nx = Math.ceil(w / CELL);
  const nz = Math.ceil(d / CELL);
  const busy = new Uint8Array(nx * nz);
  const cell = (x: number, z: number): [number, number] => [
    Math.floor((x + w / 2) / CELL),
    Math.floor((z + d / 2) / CELL),
  ];
  const mark = (x: number, z: number, r: number) => {
    const [ci, cj] = cell(x, z);
    const k = Math.ceil(r / CELL);
    for (let i = ci - k; i <= ci + k; i += 1)
      for (let j = cj - k; j <= cj + k; j += 1)
        if (i >= 0 && j >= 0 && i < nx && j < nz) busy[j * nx + i] = 1;
  };
  for (const lane of net.lanes) {
    const pts = lane.shape.map(([x, y]) => p.to(x, y));
    const r = lane.width / 2 + SETBACK;
    for (let s = 0; s + 1 < pts.length; s += 1) {
      const [ax, az] = pts[s]!;
      const [bx, bz] = pts[s + 1]!;
      const steps = Math.max(1, Math.ceil(Math.hypot(bx - ax, bz - az) / CELL));
      for (let k = 0; k <= steps; k += 1)
        mark(ax + ((bx - ax) * k) / steps, az + ((bz - az) * k) / steps, r);
    }
  }
  for (const j of net.junctions) {
    const [x, z] = p.to(j.position[0], j.position[1]);
    const radius = j.shape.length
      ? Math.max(...j.shape.map(([sx, sy]) => Math.hypot(sx - j.position[0], sy - j.position[1])))
      : 8;
    mark(x, z, radius + SETBACK);
  }

  // distance (in cells) from every cell to the nearest street: two passes of a chamfer
  const far = new Float32Array(nx * nz).fill(1e9);
  for (let k = 0; k < far.length; k += 1) if (busy[k]) far[k] = 0;
  const relax = (i: number, j: number, di: number, dj: number, cost: number) => {
    const a = i + di;
    const b = j + dj;
    if (a < 0 || b < 0 || a >= nx || b >= nz) return;
    const v = far[b * nx + a]! + cost;
    if (v < far[j * nx + i]!) far[j * nx + i] = v;
  };
  for (let j = 0; j < nz; j += 1)
    for (let i = 0; i < nx; i += 1) {
      relax(i, j, -1, 0, 1);
      relax(i, j, 0, -1, 1);
      relax(i, j, -1, -1, 1.414);
      relax(i, j, 1, -1, 1.414);
    }
  for (let j = nz - 1; j >= 0; j -= 1)
    for (let i = nx - 1; i >= 0; i -= 1) {
      relax(i, j, 1, 0, 1);
      relax(i, j, 0, 1, 1);
      relax(i, j, 1, 1, 1.414);
      relax(i, j, -1, 1, 1.414);
    }

  const rand = seeded(net.network);
  const buildings: Building[] = [];
  const trees: Tree[] = [];
  const reach = Math.hypot(p.width, p.depth) / 2;
  for (let z = -d / 2 + LOT; z < d / 2 - LOT; z += LOT) {
    for (let x = -w / 2 + LOT; x < w / 2 - LOT; x += LOT) {
      const size = LOT - 3 - rand() * 3;
      const [ci, cj] = cell(x, z);
      if (ci < 0 || cj < 0 || ci >= nx || cj >= nz) continue;
      const street = far[cj * nx + ci]! * CELL; // metres from the street (sidewalk included)
      if (street < size / 2 + 1) continue;
      const centre = 1 - Math.min(1, Math.hypot(x, z) / reach);
      if (street > FRONTAGE) {
        // inside the block: low houses, gardens and trees
        const roll = rand();
        if (roll < 0.4)
          buildings.push({
            x,
            z,
            width: size * (0.55 + rand() * 0.2),
            depth: size * (0.55 + rand() * 0.2),
            variant: 0,
            scaleY: 0.6 + rand() * 0.35,
            tone: Math.floor(rand() * 6),
          });
        else if (roll < 0.8)
          for (let k = 0; k < 1 + Math.floor(rand() * 2); k += 1)
            trees.push({
              x: x + (rand() - 0.5) * size * 0.7,
              z: z + (rand() - 0.5) * size * 0.7,
              scale: 0.8 + rand() * 0.7,
            });
        continue;
      }
      if (rand() < 0.08) {
        // a gap in the frontage: a tree on the sidewalk side
        trees.push({ x, z, scale: 0.9 + rand() * 0.4 });
        continue;
      }
      const tall = rand() < 0.04 + 0.22 * centre;
      const variant: Building["variant"] = tall ? 2 : rand() < 0.45 ? 1 : 0;
      buildings.push({
        x,
        z,
        width: size * (0.85 + rand() * 0.15),
        depth: size * (0.85 + rand() * 0.15),
        variant,
        scaleY: 0.85 + rand() * 0.35,
        tone: Math.floor(rand() * 6),
      });
    }
  }
  return { buildings, trees };
}

/** Floors of each building variant, and the height of one floor. */
export const FLOORS: Record<Building["variant"], number> = { 0: 3, 1: 5, 2: 10 };
export const FLOOR_H = 3.2;

/**
 * A facade texture: rows of windows, lit at random at night. The bottom strip is the roof
 * colour: the top face of every building samples it (see buildingGeometry).
 */
export function facadeTexture(floors: number, dark: boolean, seed: string): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  const cols = 6;
  canvas.width = 128;
  canvas.height = 16 * floors + 8;
  const g = canvas.getContext("2d")!;
  g.fillStyle = dark ? "#465063" : "#f2efe9";
  g.fillRect(0, 0, canvas.width, canvas.height);
  const rand = seeded(seed);
  for (let f = 0; f < floors; f += 1) {
    for (let c = 0; c < cols; c += 1) {
      const lit = dark && rand() < 0.22;
      g.fillStyle = dark ? (lit ? "#ffd9a0" : "#283040") : rand() < 0.15 ? "#9fb3c8" : "#7f93a8";
      g.fillRect(6 + c * 20, f * 16 + 4, 12, 9);
    }
  }
  g.fillStyle = dark ? "#202733" : "#c9c4ba"; // roof
  g.fillRect(0, canvas.height - 8, canvas.width, 8);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

/** A unit box (1 x 1 x 1, base at y = 0) whose roof samples the roof strip of the facade. */
export function buildingGeometry(): THREE.BoxGeometry {
  const box = new THREE.BoxGeometry(1, 1, 1);
  box.translate(0, 0.5, 0);
  const uv = box.getAttribute("uv") as THREE.BufferAttribute;
  // face order: +x, -x, +y (roof), -y, +z, -z; 4 vertices each
  for (let k = 8; k < 12; k += 1) uv.setXY(k, 0.5, 0.01);
  uv.needsUpdate = true;
  return box;
}

/** Building tones (multiplied with the facade): neutral concrete, sand, slate, brick-brown. */
export const BUILDING_TONES = {
  light: ["#ffffff", "#ece4d6", "#dfe5ec", "#e8dccd", "#d7dbe0", "#efe8dc"],
  dark: ["#ffffff", "#e6dfd4", "#cfd8e3", "#ddd2c4", "#c9ced6", "#e9e1d6"],
};
