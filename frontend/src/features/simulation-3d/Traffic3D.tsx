import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { KINDS, SIZE, sceneAt, signalColor, type Kind, type Side } from "@/features/replay/scene";
import { usePlayback } from "@/features/replay/store";
import type { NetworkGeometry, Replay } from "@/shared/schemas";

import type { projector } from "./geometry";
import {
  AMBULANCE_COLOR,
  ambulanceGeometry,
  beaconGeometry,
  brakeGeometry,
  BUS_COLOR,
  busGeometry,
  CAR_COLORS,
  carGeometry,
  CLOTHES,
  INCIDENT_COLOR,
  LAMP_Y,
  personBodyGeometry,
  personHeadGeometry,
  signalGeometry,
} from "./models";

const MAX = 2500;
/** Roof height of each kind (beacons, brake lights). */
const ROOF: Record<Kind, number> = { car: 1.5, bus: 2.95, emergency: 2.5, incident: 1.5 };
const LAMPS = ["red", "yellow", "green"] as const;
const BRIGHT = {
  red: new THREE.Color("#ff3b30"),
  yellow: new THREE.Color("#ffcc00"),
  green: new THREE.Color("#2ee06f"),
};
const DIM = {
  red: new THREE.Color("#3a1414"),
  yellow: new THREE.Color("#3a3110"),
  green: new THREE.Color("#10301c"),
};
const BAR_OFF = new THREE.Color("#5b6573");
const BEACON = { blue: new THREE.Color("#3b82f6"), white: new THREE.Color("#f8fafc") };
const HAZARD = { on: new THREE.Color("#f59e0b"), off: new THREE.Color("#3a2c10") };
const BRAKE = new THREE.Color("#ff2a1a");

const tmp = new THREE.Object3D();

interface Head {
  slot: number;
  indices: number[];
  /** pole position and stop line, three.js (x, z) */
  pole: [number, number];
  stop: [number, number];
  /** rotation about y of the housing (faces the incoming traffic) and of the stop bar */
  facing: number;
  along: number;
  width: number;
}

/** One signal head per controlled lane, at the right of its stop line. */
function signalHeads(
  net: NetworkGeometry,
  replay: Replay,
  p: ReturnType<typeof projector>,
): Head[] {
  const order = new Map(replay.signals.map((id, i) => [id, i]));
  const lanes = new Map(net.lanes.map((l) => [l.id, l]));
  const heads = new Map<string, Head>();
  for (const s of net.signals) {
    const slot = order.get(s.tls);
    if (slot === undefined) continue;
    for (const l of s.links) {
      const key = `${slot}:${l.lane}`;
      const known = heads.get(key);
      if (known) {
        known.indices.push(l.index);
        continue;
      }
      const lane = lanes.get(l.lane);
      const shape = lane?.shape ?? [l.position, l.position];
      const a = shape[shape.length - 2] ?? l.position;
      const b = shape[shape.length - 1] ?? l.position;
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
      const dx = (b[0] - a[0]) / len;
      const dy = (b[1] - a[1]) / len;
      const width = lane?.width ?? 3.2;
      const off = width / 2 + 0.7;
      // right-hand normal in SUMO coordinates (x east, y north) is (dy, -dx)
      const pole = p.to(l.position[0] + dy * off, l.position[1] - dx * off);
      heads.set(key, {
        slot,
        indices: [l.index],
        pole,
        stop: p.to(l.position[0] - dx * 0.4, l.position[1] - dy * 0.4),
        facing: Math.atan2(-dy, -dx),
        along: Math.atan2(dy, dx),
        width,
      });
    }
  }
  return [...heads.values()];
}

/** The most permissive state among the links of a lane (what a driver on it sees). */
function headState(
  states: string | undefined,
  indices: number[],
): "green" | "yellow" | "red" | "off" {
  let best: "green" | "yellow" | "red" | "off" = "off";
  for (const i of indices) {
    const c = signalColor(states?.[i]);
    if (c === "green") return "green";
    if (c === "yellow") best = "yellow";
    else if (c === "red" && best === "off") best = "red";
  }
  return best;
}

/**
 * Vehicles, pedestrians and signals of one controller, drawn as instanced meshes and
 * updated every frame from the playback clock (no React re-render per frame).
 */
export function Traffic3D({
  net,
  replay,
  side,
  project,
}: {
  net: NetworkGeometry;
  replay: Replay;
  side: Side;
  project: ReturnType<typeof projector>;
}) {
  const meshes = useRef<Partial<Record<Kind, THREE.InstancedMesh | null>>>({});
  const beacons = useRef<THREE.InstancedMesh>(null);
  const brakes = useRef<THREE.InstancedMesh>(null);
  const bodies = useRef<THREE.InstancedMesh>(null);
  const headsMesh = useRef<THREE.InstancedMesh>(null);
  const poles = useRef<THREE.InstancedMesh>(null);
  const lamps = useRef<Partial<Record<(typeof LAMPS)[number], THREE.InstancedMesh | null>>>({});
  const bars = useRef<THREE.InstancedMesh>(null);
  const heads = useMemo(() => signalHeads(net, replay, project), [net, replay, project]);

  const geometries = useMemo(() => {
    const g = {
      car: carGeometry(...SIZE.car),
      bus: busGeometry(...SIZE.bus),
      emergency: ambulanceGeometry(...SIZE.emergency),
      incident: carGeometry(...SIZE.incident),
      beacon: beaconGeometry(),
      brake: brakeGeometry(1.8),
      body: personBodyGeometry(),
      head: personHeadGeometry(),
      pole: signalGeometry(),
      lamp: new THREE.SphereGeometry(0.16, 12, 8),
      bar: new THREE.BoxGeometry(0.45, 0.05, 1),
    };
    return g;
  }, []);
  useEffect(() => () => Object.values(geometries).forEach((g) => g.dispose()), [geometries]);

  useEffect(() => {
    // poles, lamps and stop bars do not move: place them once
    const n = heads.length;
    heads.forEach((h, i) => {
      tmp.position.set(h.pole[0], 0, h.pole[1]);
      tmp.rotation.set(0, h.facing, 0);
      tmp.scale.set(1, 1, 1);
      tmp.updateMatrix();
      poles.current?.setMatrixAt(i, tmp.matrix);
      for (const lamp of LAMPS) {
        const m = lamps.current[lamp];
        if (!m) continue;
        tmp.position.set(
          h.pole[0] + Math.cos(h.facing) * 0.24,
          LAMP_Y[lamp],
          h.pole[1] - Math.sin(h.facing) * 0.24,
        );
        tmp.updateMatrix();
        m.setMatrixAt(i, tmp.matrix);
        m.setColorAt(i, DIM[lamp]);
      }
      tmp.position.set(h.stop[0], 0.09, h.stop[1]);
      tmp.rotation.set(0, h.along, 0);
      tmp.scale.set(1, 1, h.width * 0.92);
      tmp.updateMatrix();
      bars.current?.setMatrixAt(i, tmp.matrix);
      bars.current?.setColorAt(i, BAR_OFF);
    });
    for (const m of [poles.current, bars.current, ...LAMPS.map((l) => lamps.current[l])]) {
      if (!m) continue;
      m.count = n;
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }
    tmp.scale.set(1, 1, 1);
  }, [heads]);

  useFrame(() => {
    const time = usePlayback.getState().time;
    const scene = sceneAt(replay, side, time);
    const counts: Record<Kind, number> = { car: 0, bus: 0, emergency: 0, incident: 0 };
    let nBeacon = 0;
    let nBrake = 0;
    const flash = Math.floor(time * 3) % 2 === 0;
    for (const v of scene.vehicles) {
      const mesh = meshes.current[v.kind];
      if (!mesh) continue;
      const i = counts[v.kind]++;
      if (i >= MAX) continue;
      const [length] = SIZE[v.kind];
      const rad = (v.angle * Math.PI) / 180;
      const sin = Math.sin(rad);
      const cos = Math.cos(rad);
      // centre of the vehicle: half its length behind the front bumper (SUMO's position)
      const [x, z] = project.to(v.x - sin * (length / 2), v.y - cos * (length / 2));
      const yaw = Math.PI / 2 - rad;
      tmp.position.set(x, 0.12, z);
      tmp.rotation.set(0, yaw, 0);
      tmp.updateMatrix();
      mesh.setMatrixAt(i, tmp.matrix);
      mesh.setColorAt(
        i,
        v.kind === "bus"
          ? BUS_COLOR
          : v.kind === "emergency"
            ? AMBULANCE_COLOR
            : v.kind === "incident"
              ? INCIDENT_COLOR
              : CAR_COLORS[v.id % CAR_COLORS.length]!,
      );
      // three.js forward of the vehicle: (sin, -cos) in (x, z)
      const fx = sin;
      const fz = -cos;
      if ((v.kind === "emergency" || v.kind === "incident") && beacons.current && nBeacon < MAX) {
        const k = nBeacon++;
        tmp.position.set(x + fx * length * 0.1, ROOF[v.kind] + 0.12, z + fz * length * 0.1);
        tmp.updateMatrix();
        beacons.current.setMatrixAt(k, tmp.matrix);
        beacons.current.setColorAt(
          k,
          v.kind === "emergency"
            ? flash
              ? BEACON.blue
              : BEACON.white
            : flash
              ? HAZARD.on
              : HAZARD.off,
        );
      }
      if (v.speed < 0.5 && brakes.current && nBrake < MAX) {
        const k = nBrake++;
        tmp.position.set(
          x - fx * (length / 2 + 0.04),
          v.kind === "bus" ? 1.0 : 0.75,
          z - fz * (length / 2 + 0.04),
        );
        tmp.updateMatrix();
        brakes.current.setMatrixAt(k, tmp.matrix);
      }
    }
    for (const k of KINDS) {
      const mesh = meshes.current[k];
      if (!mesh) continue;
      mesh.count = Math.min(MAX, counts[k]);
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
    for (const [m, n] of [
      [beacons.current, nBeacon],
      [brakes.current, nBrake],
    ] as const) {
      if (!m) continue;
      m.count = n;
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }

    const body = bodies.current;
    const head = headsMesh.current;
    if (body && head) {
      const n = Math.min(MAX, scene.persons.length);
      for (let i = 0; i < n; i += 1) {
        const p = scene.persons[i]!;
        const [x, z] = project.to(p.x, p.y);
        tmp.position.set(x, 0.12, z);
        tmp.rotation.set(0, 0, 0);
        tmp.updateMatrix();
        body.setMatrixAt(i, tmp.matrix);
        head.setMatrixAt(i, tmp.matrix);
        body.setColorAt(i, CLOTHES[i % CLOTHES.length]!);
      }
      body.count = n;
      head.count = n;
      body.instanceMatrix.needsUpdate = true;
      head.instanceMatrix.needsUpdate = true;
      if (body.instanceColor) body.instanceColor.needsUpdate = true;
    }

    heads.forEach((h, i) => {
      const state = headState(scene.signals[h.slot], h.indices);
      for (const lamp of LAMPS)
        lamps.current[lamp]?.setColorAt(i, state === lamp ? BRIGHT[lamp] : DIM[lamp]);
      bars.current?.setColorAt(i, state === "off" ? BAR_OFF : BRIGHT[state]);
    });
    for (const lamp of LAMPS) {
      const m = lamps.current[lamp];
      if (m?.instanceColor) m.instanceColor.needsUpdate = true;
    }
    if (bars.current?.instanceColor) bars.current.instanceColor.needsUpdate = true;
  });

  const signals = Math.max(1, heads.length);
  return (
    <group>
      {KINDS.map((k) => (
        <instancedMesh
          key={k}
          ref={(m) => {
            meshes.current[k] = m;
          }}
          args={[geometries[k], undefined, MAX]}
          frustumCulled={false}
          castShadow
        >
          <meshStandardMaterial vertexColors roughness={0.35} metalness={0.25} />
        </instancedMesh>
      ))}
      <instancedMesh ref={beacons} args={[geometries.beacon, undefined, MAX]} frustumCulled={false}>
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={brakes} args={[geometries.brake, undefined, MAX]} frustumCulled={false}>
        <meshBasicMaterial color={BRAKE} toneMapped={false} />
      </instancedMesh>
      <instancedMesh
        ref={bodies}
        args={[geometries.body, undefined, MAX]}
        frustumCulled={false}
        castShadow
      >
        <meshStandardMaterial vertexColors roughness={0.8} />
      </instancedMesh>
      <instancedMesh ref={headsMesh} args={[geometries.head, undefined, MAX]} frustumCulled={false}>
        <meshStandardMaterial color="#d9a98a" roughness={0.7} />
      </instancedMesh>
      <instancedMesh
        ref={poles}
        args={[geometries.pole, undefined, signals]}
        frustumCulled={false}
        castShadow
      >
        <meshStandardMaterial vertexColors roughness={0.6} metalness={0.3} />
      </instancedMesh>
      {LAMPS.map((lamp) => (
        <instancedMesh
          key={lamp}
          ref={(m) => {
            lamps.current[lamp] = m;
          }}
          args={[geometries.lamp, undefined, signals]}
          frustumCulled={false}
        >
          <meshBasicMaterial toneMapped={false} />
        </instancedMesh>
      ))}
      <instancedMesh ref={bars} args={[geometries.bar, undefined, signals]} frustumCulled={false}>
        <meshBasicMaterial toneMapped={false} transparent opacity={0.85} />
      </instancedMesh>
    </group>
  );
}
