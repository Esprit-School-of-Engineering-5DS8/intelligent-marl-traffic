import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type ComponentRef } from "react";

import * as THREE from "three";

import { useResolvedTheme } from "@/app/theme";
import type { Side } from "@/features/replay/scene";
import type { NetworkGeometry, Replay } from "@/shared/schemas";

import { buildRoads, projector } from "./geometry";
import { Traffic3D } from "./Traffic3D";
import type { Visibility } from "./visibility";

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
  visible,
  label,
}: {
  net: NetworkGeometry;
  replay: Replay;
  sides: readonly Side[];
  resetKey: number;
  visible: Visibility;
  label: string;
}) {
  const theme = useResolvedTheme();
  const dark = theme === "dark";
  const project = useMemo(() => projector(net), [net]);
  const roads = useMemo(() => buildRoads(net, project, dark), [net, project, dark]);
  useEffect(() => () => roads.dispose(), [roads]);

  const span = project.width * sides.length + GAP * (sides.length - 1);
  const offsets = sides.map((_, i) => (i - (sides.length - 1) / 2) * (project.width + GAP));
  // The grids are flat, so a steep three-quarter view keeps the network square on screen
  // (a shallow angle stretches its depth into tall strips) while still reading as 3D.
  const distance =
    sides.length > 1
      ? Math.max(span * 0.95, project.depth * 1.6)
      : Math.max(project.depth, project.width) * 1.3;
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);

  useEffect(() => {
    controls.current?.reset();
  }, [resetKey, sides.length]);

  return (
    <div role="img" aria-label={label} className="h-full w-full">
      <Canvas
        key={sides.length}
        camera={{
          position: [0, distance * 0.86, distance * 0.5],
          fov: 42,
          near: 1,
          far: distance * 10,
        }}
        dpr={[1, 2]}
        gl={{ antialias: true }}
      >
        <color attach="background" args={[dark ? "#0a0f14" : "#eef2f5"]} />
        <hemisphereLight args={[dark ? "#b8c4d6" : "#ffffff", dark ? "#1b2430" : "#b6c2cf", 1.1]} />
        <directionalLight position={[span * 0.3, distance * 1.4, distance * 0.5]} intensity={1.2} />
        {sides.map((side, i) => (
          <group key={side} position={[offsets[i]!, 0, 0]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
              <planeGeometry args={[project.width + 40, project.depth + 40]} />
              <meshStandardMaterial color={dark ? "#121a22" : "#dfe6dc"} />
            </mesh>
            <mesh geometry={roads}>
              <meshStandardMaterial vertexColors roughness={0.95} side={THREE.DoubleSide} />
            </mesh>
            <Traffic3D
              net={net}
              replay={replay}
              side={side}
              project={project}
              visible={visible}
            />
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
