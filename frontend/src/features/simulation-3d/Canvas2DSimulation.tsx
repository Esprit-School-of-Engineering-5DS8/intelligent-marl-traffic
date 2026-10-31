import React, { useEffect, useRef } from "react";
import type { NetworkGeometry, Replay } from "@/shared/schemas";
import { sceneAt, type Side } from "@/features/replay/scene";
import { usePlayback } from "@/features/replay/store";

interface Canvas2DSimulationProps {
  net: NetworkGeometry;
  replay: Replay;
  side: Side;
  label: string;
}

export function Canvas2DSimulation({ net, replay, side, label }: Canvas2DSimulationProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const time = usePlayback((s) => s.time);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Handle high DPI
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.resetTransform?.();
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;

    // Clear background (dark asphalt theme)
    ctx.fillStyle = "#090d16";
    ctx.fillRect(0, 0, width, height);

    // Compute coordinate transformation based on net bounds
    const [[minX, minY], [maxX, maxY]] = net.bounds;
    const netW = Math.max(maxX - minX, 10);
    const netH = Math.max(maxY - minY, 10);
    const padding = 36;
    const scale = Math.min((width - padding * 2) / netW, (height - padding * 2) / netH);

    const toScreenX = (x: number) => padding + (x - minX) * scale;
    // Invert Y axis for standard cartesian to screen coordinates
    const toScreenY = (y: number) => height - (padding + (y - minY) * scale);

    // 1. Draw lanes / road network
    ctx.lineWidth = Math.max(2, 2.8 * scale);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    for (const lane of net.lanes) {
      if (lane.shape.length < 2) continue;
      ctx.beginPath();
      const [start, ...rest] = lane.shape;
      ctx.moveTo(toScreenX(start[0]), toScreenY(start[1]));
      for (const pt of rest) {
        ctx.lineTo(toScreenX(pt[0]), toScreenY(pt[1]));
      }
      ctx.strokeStyle = lane.kind === "crossing" ? "rgba(148, 163, 184, 0.25)" : "#1e293b";
      ctx.stroke();
    }

    // 2. Draw junctions
    for (const junc of net.junctions) {
      const jx = toScreenX(junc.position[0]);
      const jy = toScreenY(junc.position[1]);
      ctx.beginPath();
      ctx.arc(jx, jy, Math.max(4, 5 * scale), 0, Math.PI * 2);
      ctx.fillStyle = junc.signalised ? "rgba(34, 197, 94, 0.25)" : "rgba(100, 116, 139, 0.2)";
      ctx.fill();
      if (junc.signalised) {
        ctx.strokeStyle = "rgba(34, 197, 94, 0.8)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }

    // 3. Draw vehicles and persons at current replay time
    const scene = sceneAt(replay, side, time);

    for (const v of scene.vehicles) {
      const vx = toScreenX(v.x);
      const vy = toScreenY(v.y);

      // Color based on vehicle kind
      let color = "#38c980"; // car / default
      let radius = Math.max(3, 3.5 * scale);

      if (v.kind === "bus") {
        color = "#f5c451";
        radius = Math.max(4, 5 * scale);
      } else if (v.kind === "emergency") {
        color = "#ff4d6d";
        radius = Math.max(4, 4.5 * scale);
      } else if (v.kind === "incident") {
        color = "#d946ef";
        radius = Math.max(4, 4.5 * scale);
      }

      ctx.save();
      ctx.translate(vx, vy);
      ctx.rotate((-v.angle * Math.PI) / 180);

      // Vehicle body
      ctx.fillStyle = color;
      ctx.beginPath();
      const vLen = radius * 2.2;
      const vWidth = radius * 1.2;
      ctx.roundRect
        ? ctx.roundRect(-vWidth / 2, -vLen / 2, vWidth, vLen, 2)
        : ctx.fillRect(-vWidth / 2, -vLen / 2, vWidth, vLen);
      ctx.fill();

      // Heading indicator
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(0, vLen / 2 - 1, 1, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
    }

    // 4. Draw pedestrians
    for (const p of scene.persons) {
      const px = toScreenX(p.x);
      const py = toScreenY(p.y);
      ctx.beginPath();
      ctx.arc(px, py, Math.max(2, 2.2 * scale), 0, Math.PI * 2);
      ctx.fillStyle = p.waiting ? "#f87171" : "#93c5fd";
      ctx.fill();
    }
  }, [net, replay, side, time]);

  return (
    <div className="relative w-full h-[460px] bg-slate-950 overflow-hidden rounded-b-lg">
      <canvas ref={canvasRef} className="w-full h-full block" />
      <div className="absolute top-3 left-3 px-2 py-1 bg-black/60 backdrop-blur-md rounded border border-white/10 text-[11px] font-mono text-white/80">
        {label}
      </div>
    </div>
  );
}

