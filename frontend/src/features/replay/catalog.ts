import type { Meta } from "@/shared/schemas";

export type ReplayEntry = Meta["replays"][number];

const CANDIDATES = new Set(["hybrid_h2", "hybrid_h2_llmstrat"]);

export const withCandidate = (r: ReplayEntry) => CANDIDATES.has(r.left) || CANDIDATES.has(r.right);

/** The events of a replay, read from its id (network__events__demand__seed). */
export const replayEvents = (id: string) => (id.split("__")[1] ?? "").split("+");

/**
 * The replays in the order the pages offer them: the LLM in the loop first, then our
 * candidate, then the first study's (stable inside each group).
 */
export function orderReplays(replays: ReplayEntry[]): ReplayEntry[] {
  const rank = (r: ReplayEntry) => (r.llm ? 0 : withCandidate(r) ? 1 : 2);
  return [...replays].sort((a, b) => rank(a) - rank(b));
}

/** The first replay showing ``event`` (our candidate's first). */
export function firstWith(replays: ReplayEntry[], event: string): ReplayEntry | undefined {
  const order = [...replays].sort((a, b) => Number(withCandidate(b)) - Number(withCandidate(a)));
  return order.find((r) => replayEvents(r.id).includes(event));
}
