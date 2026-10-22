import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type ComponentRef } from "react";

import * as THREE from "three";

import { useResolvedTheme } from "@/app/theme";
import type { Side } from "@/features/replay/scene";
import type { NetworkGeometry, Replay } from "@/shared/schemas";

import { buildRoads, projector } from "./geometry";
import { Traffic3D } from "./Traffic3D";

const GAP = 120;

/**
 * Both controllers on the same traffic, side by side in one 3D scene. Drag to rotate,
 * wheel to zoom, right-drag to pan (OrbitControls).
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
  useEffect(() => () => roads.dispose(), [roads]);

  const span = project.width * sides.length + GAP * (sides.length - 1);
  const offsets = sides.map((_, i) => (i - (sides.length - 1) / 2) * (project.width + GAP));
  const distance = Math.max(span, project.depth) * 0.62;
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);

  useEffect(() => {
    controls.current?.reset();
  }, [resetKey, sides.length]);

  return (
    <div role="img" aria-label={label} className="h-full w-full">
      <Canvas
        key={sides.length}
        camera={{
          position: [0, distance * 0.7, distance * 0.55],
          fov: 45,
          near: 1,
          far: distance * 10,
        }}
        dpr={[1, 2]}
        gl={{ antialias: true }}
      >
        <color attach="background" args={[dark ? "#0a0f14" : "#eef2f5"]} />
        <hemisphereLight args={[dark ? "#b8c4d6" : "#ffffff", dark ? "#1b2430" : "#b6c2cf", 1.1]} />
        <directionalLight position={[span * 0.3, distance, distance * 0.4]} intensity={1.3} />
        {sides.map((side, i) => (
          <group key={side} position={[offsets[i]!, 0, 0]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
              <planeGeometry args={[project.width + 40, project.depth + 40]} />
              <meshStandardMaterial color={dark ? "#121a22" : "#dfe6dc"} />
            </mesh>
            <mesh geometry={roads}>
              <meshStandardMaterial vertexColors roughness={0.95} side={THREE.DoubleSide} />
            </mesh>
            <Traffic3D net={net} replay={replay} side={side} project={project} />
          </group>
        ))}
        <OrbitControls
          ref={controls}
          makeDefault
          enableDamping
          maxPolarAngle={Math.PI / 2.1}
          minDistance={20}
          maxDistance={distance * 3}
          screenSpacePanning={false}
        />
      </Canvas>
    </div>
  );
}
