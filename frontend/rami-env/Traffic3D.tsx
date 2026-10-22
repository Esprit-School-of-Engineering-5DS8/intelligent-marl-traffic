import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import {
  KINDS,
  SIZE,
  sceneAt,
  signalColor,
  signalLinks,
  type Kind,
  type Side,
} from "@/features/replay/scene";
import { usePlayback } from "@/features/replay/store";
import type { NetworkGeometry, Replay } from "@/shared/schemas";

import type { projector } from "./geometry";

const MAX = 2500;
const HEIGHT: Record<Kind, number> = { car: 1.5, bus: 3.1, emergency: 2.4, incident: 1.5 };
const COLORS = {
  flow: new THREE.Color("#38c980"),
  dense: new THREE.Color("#f2a33a"),
  jam: new THREE.Color("#f06063"),
  bus: new THREE.Color("#f5c451"),
  emergencyA: new THREE.Color("#5b97ff"),
  emergencyB: new THREE.Color("#ff4d6d"),
  incident: new THREE.Color("#d946ef"),
  green: new THREE.Color("#22c55e"),
  yellow: new THREE.Color("#facc15"),
  red: new THREE.Color("#ef4444"),
  off: new THREE.Color("#64748b"),
  person: new THREE.Color("#93c5fd"),
  personWaiting: new THREE.Color("#fb7185"),
};

const tmp = new THREE.Object3D();

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
  const persons = useRef<THREE.InstancedMesh>(null);
  const signals = useRef<THREE.InstancedMesh>(null);
  const links = useMemo(() => signalLinks(net, replay), [net, replay]);

  const boxes = useMemo(
    () =>
      Object.fromEntries(
        KINDS.map((k) => {
          const [length, width] = SIZE[k];
          return [k, new THREE.BoxGeometry(length, HEIGHT[k], width)];
        }),
      ) as Record<Kind, THREE.BoxGeometry>,
    [],
  );
  const personGeometry = useMemo(() => new THREE.CylinderGeometry(0.35, 0.35, 1.7, 8), []);
  const signalGeometry = useMemo(() => new THREE.SphereGeometry(1.1, 12, 8), []);

  useEffect(() => {
    // signal heads do not move: place them once
    const mesh = signals.current;
    if (!mesh) return;
    links.forEach((l, i) => {
      const [x, z] = project.to(l.position[0], l.position[1]);
      tmp.position.set(x, 3.2, z);
      tmp.rotation.set(0, 0, 0);
      tmp.updateMatrix();
      mesh.setMatrixAt(i, tmp.matrix);
      mesh.setColorAt(i, COLORS.off);
    });
    mesh.count = links.length;
    mesh.instanceMatrix.needsUpdate = true;
  }, [links, project]);

  useEffect(
    () => () => {
      Object.values(boxes).forEach((g) => g.dispose());
      personGeometry.dispose();
      signalGeometry.dispose();
    },
    [boxes, personGeometry, signalGeometry],
  );

  useFrame(() => {
    const time = usePlayback.getState().time;
    const scene = sceneAt(replay, side, time);
    const counts: Record<Kind, number> = { car: 0, bus: 0, emergency: 0, incident: 0 };
    const flash = Math.floor(time * 2) % 2 === 0;
    for (const v of scene.vehicles) {
      const mesh = meshes.current[v.kind];
      if (!mesh) continue;
      const i = counts[v.kind]++;
      if (i >= MAX) continue;
      const [length] = SIZE[v.kind];
      const rad = (v.angle * Math.PI) / 180;
      // centre of the vehicle: half its length behind the front bumper
      const [x, z] = project.to(
        v.x - Math.sin(rad) * (length / 2),
        v.y - Math.cos(rad) * (length / 2),
      );
      tmp.position.set(x, HEIGHT[v.kind] / 2 + 0.15, z);
      tmp.rotation.set(0, Math.PI / 2 - rad, 0);
      tmp.updateMatrix();
      mesh.setMatrixAt(i, tmp.matrix);
      const color =
        v.kind === "emergency"
          ? flash
            ? COLORS.emergencyA
            : COLORS.emergencyB
          : v.kind === "bus"
            ? COLORS.bus
            : v.kind === "incident"
              ? COLORS.incident
              : v.speed < 0.5
                ? COLORS.jam
                : v.speed < 5
                  ? COLORS.dense
                  : COLORS.flow;
      mesh.setColorAt(i, color);
    }
    for (const k of KINDS) {
      const mesh = meshes.current[k];
      if (!mesh) continue;
      mesh.count = Math.min(MAX, counts[k]);
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
    const pm = persons.current;
    if (pm) {
      const n = Math.min(MAX, scene.persons.length);
      for (let i = 0; i < n; i += 1) {
        const p = scene.persons[i]!;
        const [x, z] = project.to(p.x, p.y);
        tmp.position.set(x, 1, z);
        tmp.rotation.set(0, 0, 0);
        tmp.updateMatrix();
        pm.setMatrixAt(i, tmp.matrix);
        pm.setColorAt(i, p.waiting ? COLORS.personWaiting : COLORS.person);
      }
      pm.count = n;
      pm.instanceMatrix.needsUpdate = true;
      if (pm.instanceColor) pm.instanceColor.needsUpdate = true;
    }
    const sm = signals.current;
    if (sm) {
      links.forEach((l, i) =>
        sm.setColorAt(i, COLORS[signalColor(scene.signals[l.slot]?.[l.index])]),
      );
      if (sm.instanceColor) sm.instanceColor.needsUpdate = true;
    }
  });

  return (
    <group>
      {KINDS.map((k) => (
        <instancedMesh
          key={k}
          ref={(m) => {
            meshes.current[k] = m;
          }}
          args={[boxes[k], undefined, MAX]}
          frustumCulled={false}
          castShadow
        >
          <meshStandardMaterial roughness={0.5} metalness={0.1} />
        </instancedMesh>
      ))}
      <instancedMesh ref={persons} args={[personGeometry, undefined, MAX]} frustumCulled={false}>
        <meshStandardMaterial roughness={0.8} />
      </instancedMesh>
      <instancedMesh
        ref={signals}
        args={[signalGeometry, undefined, Math.max(1, links.length)]}
        frustumCulled={false}
      >
        <meshStandardMaterial emissiveIntensity={0.6} toneMapped={false} />
      </instancedMesh>
    </group>
  );
}
