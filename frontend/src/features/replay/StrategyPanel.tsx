import { MessagesSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useFormat, useTx } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import type { Replay } from "@/shared/schemas";

import { duration, type Side } from "./scene";
import { usePlayback } from "./store";
import { MODE_COLORS, modeAt, segments } from "./strategy";

/**
 * What the LLM strategist decided during the replay, for each side it drives: the mode in
 * force at the current moment and its reason, the modes over the window, and every call.
 */
export function StrategyPanel({
  replay,
  sides,
  className,
}: {
  replay: Replay;
  sides: Side[];
  className?: string;
}) {
  const driven = sides.filter((s) => replay.sides[s].strategy?.length);
  if (!driven.length) return null;
  return (
    <div className={cn("grid gap-3", driven.length > 1 && "md:grid-cols-2", className)}>
      {driven.map((s) => (
        <SidePanel key={s} replay={replay} side={s} />
      ))}
    </div>
  );
}

function SidePanel({ replay, side }: { replay: Replay; side: Side }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const time = usePlayback((s) => Math.floor(s.time));
  const seek = usePlayback((s) => s.seek);
  const data = replay.sides[side];
  const calls = data.strategy ?? [];
  const end = Math.max(1, duration(replay));
  const now = modeAt(calls, time);
  const inWindow = calls.filter((c) => c.t >= 0 && c.t <= end);
  const modeName = (m: string) => tx(`how.modes.${m}`, { defaultValue: m });
  return (
    <section
      aria-label={`${t("strategyPanel.title")} · ${f.methodName(data.method)}`}
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3"
      style={{ borderTopColor: methodColor(data.method), borderTopWidth: 3 }}
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold text-text">
        <MessagesSquare aria-hidden="true" className="size-4 text-text-2" />
        {t("strategyPanel.title")}
      </h3>
      <p className="-mt-2 text-xs text-muted">{f.methodName(data.method)}</p>

      <div aria-live="polite" className="flex flex-col gap-1">
        <p className="text-xs text-muted">{t("strategyPanel.now")}</p>
        <p className="flex flex-wrap items-center gap-2">
          <span
            className="rounded-full px-2.5 py-0.5 text-sm font-semibold text-white"
            style={{ background: MODE_COLORS[now.mode] ?? "var(--ctl-neutral)" }}
          >
            {modeName(now.mode)}
          </span>
          <span className="text-xs text-muted">
            {now.call && now.call.t >= 0
              ? t("strategyPanel.since", { time: f.clock(now.call.t) })
              : t("strategyPanel.start")}
          </span>
        </p>
        {now.call?.reason ? (
          <p className="text-xs leading-relaxed text-text-2">
            <span className="text-muted">{t("strategyPanel.reason")} </span>“{now.call.reason}”
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-1.5">
        <p className="text-xs text-muted">{t("strategyPanel.timeline")}</p>
        <div className="relative h-3 overflow-hidden rounded-full bg-surface-3">
          {segments(calls, end).map((s) => (
            <span
              key={s.from}
              title={`${modeName(s.mode)} ${f.clock(s.from)}–${f.clock(s.to)}`}
              className="absolute inset-y-0"
              style={{
                insetInlineStart: `${(100 * s.from) / end}%`,
                width: `${(100 * (s.to - s.from)) / end}%`,
                background: MODE_COLORS[s.mode] ?? "var(--ctl-neutral)",
              }}
            />
          ))}
          <span
            aria-hidden="true"
            className="absolute inset-y-0 w-0.5 bg-text"
            style={{ insetInlineStart: `${(100 * Math.min(time, end)) / end}%` }}
          />
        </div>
        {inWindow.length ? (
          <ol className="flex max-h-44 flex-col gap-1 overflow-y-auto text-xs">
            {inWindow.map((c) => (
              <li key={c.t}>
                <button
                  type="button"
                  onClick={() => seek(c.t)}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-md px-1.5 py-1 text-start hover:bg-surface-2",
                    now.call === c && "bg-surface-2",
                  )}
                >
                  <span className="tabular w-10 shrink-0 font-mono text-muted">{f.clock(c.t)}</span>
                  <span
                    aria-hidden="true"
                    className="mt-1 size-2 shrink-0 rounded-full"
                    style={{ background: MODE_COLORS[c.mode] ?? "var(--ctl-neutral)" }}
                  />
                  <span className="min-w-0 text-text-2">
                    <span className="font-medium text-text">{modeName(c.mode)}</span>
                    {c.valid ? null : (
                      <span className="text-muted"> · {t("strategyPanel.invalid")}</span>
                    )}
                    <span className="text-muted">
                      {" "}
                      · {t("strategyPanel.latency", { s: f.number(c.latency, 1) })}
                    </span>
                    {c.reason ? <span className="block text-muted">“{c.reason}”</span> : null}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs text-muted">{t("strategyPanel.none")}</p>
        )}
      </div>
      <p className="text-[11px] leading-snug text-muted">{t("strategyPanel.note")}</p>
    </section>
  );
}
