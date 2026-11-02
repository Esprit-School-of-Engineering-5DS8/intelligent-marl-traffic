import * as THREE from "three";

import type { NetworkGeometry } from "@/shared/schemas";

/** SUMO (x, y) in metres -> three.js (x, z), y up, network centred on the origin. */
export function projector(net: NetworkGeometry) {
  const [[x0, y0], [x1, y1]] = net.bounds;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  return {
    cx,
    cy,
    width: x1 - x0,
    depth: y1 - y0,
    to: (x: number, y: number): [number, number] => [x - cx, -(y - cy)],
  };
}

type Projector = ReturnType<typeof projector>;

function pushQuad(
  pos: number[],
  col: number[],
  a: [number, number],
  b: [number, number],
  half: number,
  y: number,
  color: THREE.Color,
) {
  const dx = b[0] - a[0];
  const dz = b[1] - a[1];
  const len = Math.hypot(dx, dz) || 1;
  const nx = (-dz / len) * half;
  const nz = (dx / len) * half;
  const v = [
    [a[0] + nx, y, a[1] + nz],
    [a[0] - nx, y, a[1] - nz],
    [b[0] - nx, y, b[1] - nz],
    [b[0] + nx, y, b[1] + nz],
  ] as const;
  for (const i of [0, 1, 2, 0, 2, 3]) {
    pos.push(...v[i]!);
    col.push(color.r, color.g, color.b);
  }
}

/**
 * Roads, sidewalks, lane markings, crossings and junction plates merged into one mesh (one
 * draw call).
 */
export function buildRoads(
  net: NetworkGeometry,
  p: Projector,
  dark: boolean,
): THREE.BufferGeometry {
  const pos: number[] = [];
  const col: number[] = [];
  const road = new THREE.Color(dark ? "#4b5663" : "#8d99a6");
  const internal = new THREE.Color(dark ? "#505c68" : "#949fab");
  const sidewalk = new THREE.Color(dark ? "#8792a0" : "#d9dee4");
  const crossing = new THREE.Color("#e8edf2");
  const junction = new THREE.Color(dark ? "#4a5663" : "#97a2ae");
  const signalised = new THREE.Color(dark ? "#544a8c" : "#a99cf0");

  for (const j of net.junctions) {
    if (j.shape.length < 3) continue;
    const pts = j.shape.map(([x, y]) => new THREE.Vector2(...p.to(x, y)));
    const tris = THREE.ShapeUtils.triangulateShape(pts, []);
    const c = j.signalised ? signalised : junction;
    for (const tri of tris) {
      for (const i of tri) {
        const v = pts[i]!;
        pos.push(v.x, 0.05, v.y);
        col.push(c.r, c.g, c.b);
      }
    }
  }
  const kerb = new THREE.Color(dark ? "#6f7a87" : "#c7ced6");
  const marking = new THREE.Color(dark ? "#d5dce4" : "#f4f6f8");
  for (const lane of net.lanes) {
    if (lane.kind !== "normal" || lane.allows === "pedestrian") continue;
    // a sidewalk band under every roadway: it shows beyond the outer lanes of each street
    const pts = lane.shape.map(([x, y]) => p.to(x, y));
    for (let i = 0; i + 1 < pts.length; i += 1)
      pushQuad(pos, col, pts[i]!, pts[i + 1]!, lane.width / 2 + 2.8, 0.0, kerb);
  }
  for (const lane of net.lanes) {
    if (lane.kind !== "normal" || lane.allows === "pedestrian") continue;
    // dashed line on the left edge of each lane: lane separators and centre lines
    const pts = lane.shape.map(([x, y]) => p.to(x, y));
    let walked = 0;
    for (let i = 0; i + 1 < pts.length; i += 1) {
      const [ax, az] = pts[i]!;
      const [bx, bz] = pts[i + 1]!;
      const len = Math.hypot(bx - ax, bz - az);
      if (len < 0.1) continue;
      // left normal in three.js (x, z) for a direction (dx, dz) is (dz, -dx)
      const ox = ((bz - az) / len) * (lane.width / 2);
      const oz = (-(bx - ax) / len) * (lane.width / 2);
      for (let s = 0; s < len; s += 1) {
        const phase = (walked + s) % 9;
        if (phase >= 4.5 || s + 1 > len - 6) continue; // no marking in the last metres
        const f0 = s / len;
        const f1 = Math.min(1, (s + 1) / len);
        pushQuad(
          pos,
          col,
          [ax + (bx - ax) * f0 + ox, az + (bz - az) * f0 + oz],
          [ax + (bx - ax) * f1 + ox, az + (bz - az) * f1 + oz],
          0.07,
          0.13,
          marking,
        );
      }
      walked += len;
    }
  }
  for (const lane of net.lanes) {
    const pts = lane.shape.map(([x, y]) => p.to(x, y));
    const isCrossing = lane.kind === "crossing";
    const ped = lane.allows === "pedestrian";
    const color = isCrossing
      ? crossing
      : ped
        ? sidewalk
        : lane.kind === "internal"
          ? internal
          : road;
    const y = isCrossing ? 0.15 : ped ? 0.17 : 0.1;
    for (let i = 0; i + 1 < pts.length; i += 1) {
      pushQuad(pos, col, pts[i]!, pts[i + 1]!, lane.width / 2, y, color);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  geometry.computeVertexNormals();
  return geometry;
}
