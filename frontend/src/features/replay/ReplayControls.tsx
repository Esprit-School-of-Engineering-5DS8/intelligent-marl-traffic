import { Columns2, Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useId } from "react";
import { useTranslation } from "react-i18next";

import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import type { Meta, Replay } from "@/shared/schemas";
import { Button } from "@/shared/ui/button";

import { duration } from "./scene";
import { replayTitle } from "./title";
import { usePlayback } from "./store";

const SPEEDS = [1, 2, 4, 8, 16];

/** Picks the replay (the first one by default). */
export function ReplayPicker({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const f = useFormat();
  const id = useId();
  const replayId = usePlayback((s) => s.replayId);
  const setReplay = usePlayback((s) => s.setReplay);
  useEffect(() => {
    if (!replayId || !meta.replays.includes(replayId)) setReplay(meta.replays[0] ?? null);
  }, [meta.replays, replayId, setReplay]);
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-text-2">
        {t("replay.replay")}
      </label>
      <select
        id={id}
        value={replayId ?? ""}
        onChange={(e) => setReplay(e.target.value)}
        className="h-9 min-w-0 rounded-md border border-border-strong bg-surface-2 px-2 text-sm text-text"
      >
        {meta.replays.map((r) => (
          <option key={r} value={r}>
            {replayTitle(r, f)}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Play/pause, speed, time slider and which controller is shown. */
export function ReplayControls({ replay }: { replay: Replay }) {
  const { t } = useTranslation();
  const f = useFormat();
  const sliderId = useId();
  const speedId = useId();
  const {
    playing,
    speed,
    time,
    side,
    split,
    setPlaying,
    setSpeed,
    seek,
    setDuration,
    setSide,
    setSplit,
  } = usePlayback();
  const total = duration(replay);

  useEffect(() => {
    setDuration(total);
  }, [total, setDuration]);

  // Space toggles playback when the focus is not in a form field
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (e.code !== "Space" || target?.closest("input, select, textarea, button, [role=dialog]"))
        return;
      e.preventDefault();
      setPlaying(!usePlayback.getState().playing);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPlaying]);

  const sides = (["left", "right"] as const).map((s) => ({
    side: s,
    method: replay.sides[s].method,
  }));

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        variant="primary"
        size="icon"
        onClick={() => setPlaying(!playing)}
        aria-label={playing ? t("replay.pause") : t("replay.play")}
        aria-keyshortcuts="Space"
      >
        {playing ? (
          <Pause aria-hidden="true" />
        ) : (
          <Play aria-hidden="true" className="rtl:-scale-x-100" />
        )}
      </Button>
      <Button variant="ghost" size="icon" onClick={() => seek(0)} aria-label="0:00">
        <RotateCcw aria-hidden="true" />
      </Button>
      <div className="flex min-w-48 flex-1 items-center gap-2">
        <label htmlFor={sliderId} className="sr-only">
          {t("replay.time")}
        </label>
        <input
          id={sliderId}
          type="range"
          min={0}
          max={total}
          step={1}
          value={Math.round(time)}
          onChange={(e) => seek(Number(e.target.value))}
          aria-valuetext={f.clock(time)}
          className="h-2 flex-1 cursor-pointer accent-[var(--accent)]"
        />
        <span className="tabular w-24 text-end text-xs text-text-2">
          {f.clock(time)} / {f.clock(total)}
        </span>
      </div>
      <label htmlFor={speedId} className="sr-only">
        {t("replay.speed")}
      </label>
      <select
        id={speedId}
        value={speed}
        onChange={(e) => setSpeed(Number(e.target.value))}
        className="h-9 rounded-md border border-border-strong bg-surface-2 px-2 text-sm text-text"
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            ×{s}
          </option>
        ))}
      </select>
      <div
        role="group"
        aria-label={t("replay.side")}
        className="flex rounded-md border border-border-strong p-0.5"
      >
        <button
          type="button"
          aria-pressed={split}
          onClick={() => setSplit(true)}
          className={cn(
            "flex h-7 items-center gap-1.5 rounded px-2 text-xs",
            split ? "bg-surface-3 text-text" : "text-muted",
          )}
        >
          <Columns2 aria-hidden="true" className="size-3.5" />
          {t("replay.split")}
        </button>
        {sides.map(({ side: s, method }) => (
          <button
            key={s}
            type="button"
            aria-pressed={!split && side === s}
            onClick={() => {
              setSplit(false);
              setSide(s);
            }}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded px-2 text-xs",
              !split && side === s ? "bg-surface-3 text-text" : "text-muted",
            )}
          >
            <span
              aria-hidden="true"
              className="size-2 rounded-full"
              style={{ background: methodColor(method) }}
            />
            {f.methodName(method)}
          </button>
        ))}
      </div>
    </div>
  );
}
