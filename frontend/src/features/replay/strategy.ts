import type { StrategyCall } from "@/shared/schemas";

export const MODES = ["equilibre", "fluidite", "agent"] as const;

/** Each mode in the colour of the controller it amounts to (theme tokens). */
export const MODE_COLORS: Record<string, string> = {
  equilibre: "var(--ctl-candidate)", // the candidate: COOP-FULL with the Max-Pressure bias
  fluidite: "var(--ctl-mp)", // Max-Pressure at every light
  agent: "var(--ctl-coop-full)", // the agent alone
};

export interface ModeNow {
  mode: string;
  /** The call that set the mode (none: the starting mode). */
  call: StrategyCall | null;
}

/**
 * The mode in force at ``t`` (seconds from the start of the window): the last valid call
 * applied by then; before any, the mode the first call found.
 */
export function modeAt(calls: StrategyCall[], t: number): ModeNow {
  let now: ModeNow = { mode: calls[0]?.previous ?? "equilibre", call: null };
  for (const c of calls) {
    if (c.t > t) break;
    if (c.valid) now = { mode: c.mode, call: c };
  }
  return now;
}

/** The modes over ``[0, end]``, as consecutive segments for a timeline. */
export function segments(
  calls: StrategyCall[],
  end: number,
): { mode: string; from: number; to: number }[] {
  const out: { mode: string; from: number; to: number }[] = [];
  let current = modeAt(calls, 0).mode;
  let from = 0;
  for (const c of calls) {
    if (!c.valid || c.t <= 0 || c.t >= end) continue;
    if (c.mode !== current) {
      out.push({ mode: current, from, to: c.t });
      current = c.mode;
      from = c.t;
    }
  }
  out.push({ mode: current, from, to: end });
  return out;
}
