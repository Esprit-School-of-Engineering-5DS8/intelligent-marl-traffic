import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, type ComponentRef } from "react";
import * as THREE from "three";

import { useResolvedTheme } from "@/app/theme";
import type { Side } from "@/features/replay/scene";
import type { NetworkGeometry, Replay } from "@/shared/schemas";

import {
  BUILDING_TONES,
  buildCity,
  buildingGeometry,
  facadeTexture,
  FLOOR_H,
  FLOORS,
  seeded,
  type Building,
  type Tree,
} from "./city";
import { buildRoads, projector } from "./geometry";
import { treeGeometry } from "./models";
import { Traffic3D } from "./Traffic3D";

const GAP = 160;
const CROWNS = ["#3d7a4f", "#4c8a5a", "#2f6b45", "#5a9466"].map((c) => new THREE.Color(c));
const tmp = new THREE.Object3D();

/** The buildings of one variant (low, mid, tall) as one instanced mesh. */
function Buildings({
  items,
  variant,
  dark,
  seed,
}: {
  items: Building[];
  variant: Building["variant"];
  dark: boolean;
  seed: string;
}) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const geometry = useMemo(() => buildingGeometry(), []);
  const map = useMemo(
    () => facadeTexture(FLOORS[variant], dark, `${seed}:${variant}`),
    [variant, dark, seed],
  );
  const tones = useMemo(
    () => BUILDING_TONES[dark ? "dark" : "light"].map((c) => new THREE.Color(c)),
    [dark],
  );
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => map.dispose(), [map]);
  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    items.forEach((b, i) => {
      tmp.position.set(b.x, 0, b.z);
      tmp.rotation.set(0, 0, 0);
      tmp.scale.set(b.width, FLOORS[variant] * FLOOR_H * b.scaleY, b.depth);
      tmp.updateMatrix();
      m.setMatrixAt(i, tmp.matrix);
      m.setColorAt(i, tones[b.tone % tones.length]!);
    });
    m.count = items.length;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    m.computeBoundingSphere();
  }, [items, variant, tones]);
  if (!items.length) return null;
  return (
    <instancedMesh ref={mesh} args={[geometry, undefined, items.length]} castShadow receiveShadow>
      <meshStandardMaterial
        map={map}
        emissiveMap={dark ? map : null}
        emissive={dark ? "#ffffff" : "#000000"}
        emissiveIntensity={dark ? 0.28 : 0}
        roughness={0.75}
        metalness={0.05}
      />
    </instancedMesh>
  );
}

function Trees({ items }: { items: Tree[] }) {
  const trunks = useRef<THREE.InstancedMesh>(null);
  const crowns = useRef<THREE.InstancedMesh>(null);
  const geometry = useMemo(() => treeGeometry(), []);
  useEffect(
    () => () => {
      geometry.trunk.dispose();
      geometry.crown.dispose();
    },
    [geometry],
  );
  useLayoutEffect(() => {
    items.forEach((t, i) => {
      tmp.position.set(t.x, 0, t.z);
      tmp.rotation.set(0, i, 0);
      tmp.scale.setScalar(t.scale);
      tmp.updateMatrix();
      trunks.current?.setMatrixAt(i, tmp.matrix);
      crowns.current?.setMatrixAt(i, tmp.matrix);
      crowns.current?.setColorAt(i, CROWNS[i % CROWNS.length]!);
    });
    for (const m of [trunks.current, crowns.current]) {
      if (!m) continue;
      m.count = items.length;
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
      m.computeBoundingSphere();
    }
  }, [items]);
  if (!items.length) return null;
  return (
    <>
      <instancedMesh ref={trunks} args={[geometry.trunk, undefined, items.length]} castShadow>
        <meshStandardMaterial color="#5b4636" roughness={0.9} />
      </instancedMesh>
      <instancedMesh ref={crowns} args={[geometry.crown, undefined, items.length]} castShadow>
        <meshStandardMaterial roughness={0.85} flatShading />
      </instancedMesh>
    </>
  );
}

/**
 * Both controllers on the same traffic, side by side, in a city built around the real
 * network: streets with sidewalks and lane markings, buildings and parks in the blocks,
 * signal heads on poles. Drag to rotate, wheel to zoom, right-drag to pan.
 */
export function Scene3D({
  net,
  replay,
  sides,
  resetKey,
  label,
}: {
  net: NetworkGeometry;
  replay: Replay;
  sides: readonly Side[];
  resetKey: number;
  label: string;
}) {
  const theme = useResolvedTheme();
  const dark = theme === "dark";
  const project = useMemo(() => projector(net), [net]);
  const roads = useMemo(() => buildRoads(net, project, dark), [net, project, dark]);
  const city = useMemo(() => buildCity(net, project), [net, project]);
  const byVariant = useMemo(
    () => ([0, 1, 2] as const).map((v) => city.buildings.filter((b) => b.variant === v)),
    [city],
  );
  useEffect(() => () => roads.dispose(), [roads]);
  // a slight random tilt of the sun per network, so that shadows are not axis-aligned
  const sun = useMemo(() => 0.35 + seeded(net.network)() * 0.3, [net.network]);

  const span = project.width * sides.length + GAP * (sides.length - 1);
  const offsets = sides.map((_, i) => (i - (sides.length - 1) / 2) * (project.width + GAP));
  const distance = Math.max(span, project.depth) * 0.6;
  // the first view: closer than the whole network, so that vehicles and signals read
  const start = distance * 0.62;
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);
  const background = dark ? "#0b1118" : "#e9eef2";

  useEffect(() => {
    controls.current?.reset();
  }, [resetKey, sides.length]);

  return (
    <div role="img" aria-label={label} className="h-full w-full">
      <Canvas
        key={sides.length}
        shadows
        camera={{
          position: [0, start * 0.5, start * 0.62],
          fov: 42,
          near: 1,
          far: distance * 12,
        }}
        dpr={[1, 2]}
        gl={{ antialias: true, logarithmicDepthBuffer: true }}
      >
        <color attach="background" args={[background]} />
        <fog attach="fog" args={[background, distance * 1.1, distance * 3.2]} />
        <hemisphereLight
          args={[dark ? "#b4c4dd" : "#ffffff", dark ? "#1d2733" : "#c2cbd4", dark ? 1.0 : 1.0]}
        />
        <directionalLight
          position={[span * sun, distance * 0.9, distance * 0.5]}
          intensity={dark ? 1.15 : 1.6}
          color={dark ? "#c7d4ff" : "#fff4e0"}
          castShadow
          shadow-mapSize={[4096, 4096]}
          shadow-bias={-0.0004}
          shadow-camera-left={-span * 0.6}
          shadow-camera-right={span * 0.6}
          shadow-camera-top={project.depth * 0.7}
          shadow-camera-bottom={-project.depth * 0.7}
          shadow-camera-near={1}
          shadow-camera-far={distance * 4}
        />
        {sides.map((side, i) => (
          <group key={side} position={[offsets[i]!, 0, 0]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]} receiveShadow>
              <planeGeometry args={[project.width + 120, project.depth + 120]} />
              <meshStandardMaterial color={dark ? "#22302a" : "#d3dccb"} roughness={1} />
            </mesh>
            <mesh geometry={roads} receiveShadow>
              <meshStandardMaterial vertexColors roughness={0.95} side={THREE.DoubleSide} />
            </mesh>
            {byVariant.map((items, v) => (
              <Buildings
                key={v}
                items={items}
                variant={v as Building["variant"]}
                dark={dark}
                seed={net.network}
              />
            ))}
            <Trees items={city.trees} />
            <Traffic3D net={net} replay={replay} side={side} project={project} />
          </group>
        ))}
        <OrbitControls
          ref={controls}
          makeDefault
          enableDamping
          zoomToCursor
          maxPolarAngle={Math.PI / 2.15}
          minDistance={15}
          maxDistance={distance * 3}
          screenSpacePanning={false}
        />
      </Canvas>
    </div>
  );
}
