import type { NetworkGeometry, Replay, ReplayFrame } from "@/shared/schemas";

export type Side = "left" | "right";
export const KINDS = ["car", "bus", "emergency", "incident"] as const;
export type Kind = (typeof KINDS)[number];

export interface VehicleNow {
  id: number;
  kind: Kind;
  x: number;
  y: number;
  /** SUMO heading in degrees: 0 = north, clockwise. */
  angle: number;
  speed: number;
}
export interface PersonNow {
  x: number;
  y: number;
  waiting: boolean;
}
export interface SceneNow {
  t: number;
  vehicles: VehicleNow[];
  persons: PersonNow[];
  signals: string[];
}

/** Vehicle sizes in metres (length, width): SUMO places a vehicle at its front bumper. */
export const SIZE: Record<Kind, [number, number]> = {
  car: [4.6, 1.8],
  bus: [12, 2.5],
  emergency: [6.2, 2.1],
  incident: [4.6, 1.8],
};

interface Decoded {
  t: number;
  /** id -> offset in the flat vehicle array */
  index: Map<number, number>;
  frame: ReplayFrame;
}

const cache = new WeakMap<ReplayFrame[], Decoded[]>();

function decode(frames: ReplayFrame[]): Decoded[] {
  let decoded = cache.get(frames);
  if (!decoded) {
    decoded = frames.map((frame) => {
      const index = new Map<number, number>();
      for (let o = 0; o + 5 < frame.v.length; o += 6) index.set(frame.v[o]!, o);
      return { t: frame.t, index, frame };
    });
    cache.set(frames, decoded);
  }
  return decoded;
}

function lerpAngle(a: number, b: number, f: number): number {
  const d = ((b - a + 540) % 360) - 180;
  return a + d * f;
}

/**
 * The scene at time `t` (seconds from the start of the window), interpolated between the
 * two recorded frames around it so that playback stays smooth at any speed.
 */
export function sceneAt(replay: Replay, side: Side, t: number): SceneNow {
  const frames = decode(replay.sides[side].frames);
  if (!frames.length) return { t, vehicles: [], persons: [], signals: [] };
  const every = replay.every || 1;
  const i = Math.max(0, Math.min(frames.length - 1, Math.floor(t / every)));
  const a = frames[i]!;
  const b = frames[Math.min(frames.length - 1, i + 1)]!;
  const f = b === a ? 0 : Math.max(0, Math.min(1, (t - a.t) / (b.t - a.t)));
  const v = a.frame.v;
  const vehicles: VehicleNow[] = [];
  for (let o = 0; o + 5 < v.length; o += 6) {
    const id = v[o]!;
    let x = v[o + 2]! / 10;
    let y = v[o + 3]! / 10;
    let angle = v[o + 4]!;
    let speed = v[o + 5]! / 10;
    const ob = b.index.get(id);
    if (ob !== undefined && f > 0) {
      const w = b.frame.v;
      x += (w[ob + 2]! / 10 - x) * f;
      y += (w[ob + 3]! / 10 - y) * f;
      angle = lerpAngle(angle, w[ob + 4]!, f);
      speed += (w[ob + 5]! / 10 - speed) * f;
    }
    vehicles.push({ id, kind: KINDS[v[o + 1]!] ?? "car", x, y, angle, speed });
  }
  const p = a.frame.p;
  const persons: PersonNow[] = [];
  for (let o = 0; o + 2 < p.length; o += 3) {
    persons.push({ x: p[o]! / 10, y: p[o + 1]! / 10, waiting: p[o + 2] === 1 });
  }
  return { t, vehicles, persons, signals: a.frame.s };
}

export function sceneStats(scene: SceneNow) {
  const n = scene.vehicles.length;
  let halted = 0;
  let sum = 0;
  for (const v of scene.vehicles) {
    if (v.speed < 0.1) halted += 1;
    sum += v.speed;
  }
  return {
    vehicles: n,
    halted,
    meanSpeed: n ? sum / n : 0,
    persons: scene.persons.length,
    waitingPersons: scene.persons.filter((p) => p.waiting).length,
  };
}

/** Footprint of a vehicle as 4 corners (it extends backwards from its front bumper). */
export function footprint(v: VehicleNow): [number, number][] {
  const [length, width] = SIZE[v.kind];
  const rad = (v.angle * Math.PI) / 180;
  const dx = Math.sin(rad);
  const dy = Math.cos(rad);
  const px = dy * (width / 2);
  const py = -dx * (width / 2);
  const bx = v.x - dx * length;
  const by = v.y - dy * length;
  return [
    [v.x + px, v.y + py],
    [v.x - px, v.y - py],
    [bx - px, by - py],
    [bx + px, by + py],
  ];
}

/** Signal colour of one link state character. */
export function signalColor(c: string | undefined): "green" | "yellow" | "red" | "off" {
  if (c === "G" || c === "g") return "green";
  if (c === "y" || c === "Y") return "yellow";
  if (c === "r" || c === "R" || c === "s") return "red";
  return "off";
}

/** Signalised junctions and the links of their signals (stop-line positions). */
export function signalLinks(net: NetworkGeometry, replay: Replay) {
  const order = new Map(replay.signals.map((id, i) => [id, i]));
  return net.signals
    .filter((s) => order.has(s.tls))
    .flatMap((s) =>
      s.links.map((l) => ({
        tls: s.tls,
        slot: order.get(s.tls)!,
        index: l.index,
        position: l.position,
      })),
    );
}

export function duration(replay: Replay): number {
  const frames = replay.sides.left.frames;
  return frames.length ? frames[frames.length - 1]!.t : 0;
}
