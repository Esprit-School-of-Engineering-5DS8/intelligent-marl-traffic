import { useEffect } from "react";
import { create } from "zustand";

import type { Side } from "./scene";

interface PlaybackStore {
  replayId: string | null;
  playing: boolean;
  /** Simulated seconds per real second. */
  speed: number;
  /** Seconds from the start of the recorded window. */
  time: number;
  duration: number;
  side: Side;
  split: boolean;
  selectedJunction: string | null;
  setReplay: (id: string | null) => void;
  setPlaying: (playing: boolean) => void;
  setSpeed: (speed: number) => void;
  seek: (time: number) => void;
  setDuration: (duration: number) => void;
  setSide: (side: Side) => void;
  setSplit: (split: boolean) => void;
  selectJunction: (id: string | null) => void;
}

/** Playback shared by the 2D map and the 3D view: switching pages keeps the same moment. */
export const usePlayback = create<PlaybackStore>()((set) => ({
  replayId: null,
  playing: false,
  speed: 4,
  time: 0,
  duration: 0,
  side: "right",
  split: true,
  selectedJunction: null,
  setReplay: (replayId) => set({ replayId, time: 0, selectedJunction: null }),
  setPlaying: (playing) => set({ playing }),
  setSpeed: (speed) => set({ speed }),
  seek: (time) => set((s) => ({ time: Math.max(0, Math.min(s.duration, time)) })),
  setDuration: (duration) => set({ duration }),
  setSide: (side) => set({ side }),
  setSplit: (split) => set({ split }),
  selectJunction: (selectedJunction) => set({ selectedJunction }),
}));

/** Advances the playback clock while playing; loops at the end of the window. */
export function usePlaybackClock(): void {
  const playing = usePlayback((s) => s.playing);
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.25, (now - last) / 1000);
      last = now;
      const { time, speed, duration } = usePlayback.getState();
      if (duration > 0)
        usePlayback.setState({ time: time + dt * speed >= duration ? 0 : time + dt * speed });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);
}
