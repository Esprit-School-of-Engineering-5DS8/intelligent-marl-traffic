import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

/**
 * Low-poly models built from boxes and cylinders, merged into one geometry each (one draw
 * call per kind with instancing). Parts carry a vertex colour: white parts take the colour
 * of the instance (the body), dark parts (glass, tyres) stay dark whatever the body colour.
 * Every model points along +x (its front), base at y = 0.
 */
function part(
  geometry: THREE.BufferGeometry,
  color: string,
  at: [number, number, number],
  rotate?: [number, number, number],
): THREE.BufferGeometry {
  const g = geometry.index ? geometry.toNonIndexed() : geometry;
  if (rotate) g.rotateX(rotate[0]).rotateY(rotate[1]).rotateZ(rotate[2]);
  g.translate(...at);
  const c = new THREE.Color(color);
  const colors = new Float32Array(g.getAttribute("position").count * 3);
  for (let i = 0; i < colors.length; i += 3) colors.set([c.r, c.g, c.b], i);
  g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  g.deleteAttribute("uv");
  return g;
}

const BODY = "#ffffff"; // takes the instance colour
const GLASS = "#1b232d";
const TYRE = "#0d0f12";

function wheels(
  length: number,
  width: number,
  radius: number,
  axle: number,
): THREE.BufferGeometry[] {
  const out: THREE.BufferGeometry[] = [];
  for (const x of [axle * length, -axle * length])
    for (const z of [width / 2 - 0.12, -(width / 2 - 0.12)])
      out.push(
        part(
          new THREE.CylinderGeometry(radius, radius, 0.26, 12),
          TYRE,
          [x, radius, z],
          [Math.PI / 2, 0, 0],
        ),
      );
  return out;
}

export function carGeometry(length: number, width: number): THREE.BufferGeometry {
  return mergeGeometries([
    part(new THREE.BoxGeometry(length, 0.62, width), BODY, [0, 0.62, 0]),
    part(new THREE.BoxGeometry(length * 0.52, 0.5, width * 0.9), GLASS, [-length * 0.06, 1.18, 0]),
    part(new THREE.BoxGeometry(length * 0.48, 0.06, width * 0.86), BODY, [-length * 0.06, 1.45, 0]),
    ...wheels(length, width, 0.33, 0.32),
  ])!;
}

export function busGeometry(length: number, width: number): THREE.BufferGeometry {
  return mergeGeometries([
    part(new THREE.BoxGeometry(length, 2.5, width), BODY, [0, 1.65, 0]),
    part(new THREE.BoxGeometry(length * 0.94, 0.85, width * 1.02), GLASS, [-length * 0.01, 2.2, 0]),
    part(new THREE.BoxGeometry(0.06, 1.1, width * 0.86), GLASS, [length / 2 + 0.01, 2.05, 0]),
    ...wheels(length, width, 0.48, 0.34),
  ])!;
}

/** White van with a blue stripe; its beacon is a separate, flashing mesh. */
export function ambulanceGeometry(length: number, width: number): THREE.BufferGeometry {
  const box = length * 0.64;
  return mergeGeometries([
    part(new THREE.BoxGeometry(box, 2.05, width), BODY, [-length * 0.18, 1.42, 0]),
    part(new THREE.BoxGeometry(length * 0.36, 1.35, width * 0.96), BODY, [length * 0.32, 1.08, 0]),
    part(new THREE.BoxGeometry(length * 0.2, 0.55, width * 0.98), GLASS, [length * 0.36, 1.45, 0]),
    part(new THREE.BoxGeometry(box * 1.01, 0.32, width * 1.02), "#1d4ed8", [
      -length * 0.18,
      1.25,
      0,
    ]),
    ...wheels(length, width, 0.38, 0.32),
  ])!;
}

export function beaconGeometry(): THREE.BufferGeometry {
  return new THREE.BoxGeometry(0.5, 0.22, 1.2);
}

/** A tail-light bar, shown behind stopped vehicles (brake lights). */
export function brakeGeometry(width: number): THREE.BufferGeometry {
  return new THREE.BoxGeometry(0.12, 0.2, width * 0.8);
}

export function personBodyGeometry(): THREE.BufferGeometry {
  return mergeGeometries([
    part(new THREE.CylinderGeometry(0.2, 0.24, 0.85, 10), BODY, [0, 1.12, 0]),
    part(new THREE.CylinderGeometry(0.14, 0.12, 0.75, 8), "#2b3340", [0, 0.38, 0]),
  ])!;
}

export function personHeadGeometry(): THREE.BufferGeometry {
  const head = new THREE.SphereGeometry(0.17, 12, 8);
  head.translate(0, 1.72, 0);
  return head;
}

export const POLE_H = 4.2;

/** Pole and housing of a signal head; the three lamps are separate instanced meshes. */
export function signalGeometry(): THREE.BufferGeometry {
  return mergeGeometries([
    part(new THREE.CylinderGeometry(0.09, 0.11, POLE_H, 8), "#3a4350", [0, POLE_H / 2, 0]),
    part(new THREE.BoxGeometry(0.42, 1.3, 0.42), "#14181e", [0, POLE_H + 0.45, 0]),
    part(new THREE.BoxGeometry(0.5, 0.06, 0.5), "#14181e", [0, POLE_H + 1.13, 0]),
  ])!;
}

/** Height of each lamp above the ground: red on top, green at the bottom. */
export const LAMP_Y = { red: POLE_H + 0.86, yellow: POLE_H + 0.45, green: POLE_H + 0.04 };

export function treeGeometry(): { trunk: THREE.BufferGeometry; crown: THREE.BufferGeometry } {
  const trunk = new THREE.CylinderGeometry(0.22, 0.3, 2.6, 6);
  trunk.translate(0, 1.3, 0);
  const crown = new THREE.IcosahedronGeometry(2.3, 0);
  crown.translate(0, 4.2, 0);
  return { trunk, crown };
}

/**
 * Solid body colours of the cars: never green, red or yellow (the colours of the signals),
 * never the violet of the buses nor the white of the ambulances.
 */
export const CAR_COLORS = [
  "#c3c9d1", // silver
  "#5b6573", // graphite
  "#22272e", // black
  "#1f3c88", // navy blue
  "#3f78b5", // steel blue
  "#7ea6d6", // sky blue
  "#cdbb98", // champagne
  "#6e4f3a", // brown
].map((c) => new THREE.Color(c));
export const BUS_COLOR = new THREE.Color("#7c3aed");
export const AMBULANCE_COLOR = new THREE.Color("#ffffff");
export const INCIDENT_COLOR = new THREE.Color("#3a3f47");
export const CLOTHES = [
  "#3b5b92",
  "#6b7280",
  "#8d6e63",
  "#334155",
  "#9d4edd",
  "#2563eb",
  "#e5e7eb",
  "#57534e",
].map((c) => new THREE.Color(c));
