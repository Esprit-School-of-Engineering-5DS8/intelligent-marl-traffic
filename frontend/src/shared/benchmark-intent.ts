/**
 * Hand-off between the three Benchmark pages.
 *
 * The shell owns tab navigation, so pages never touch the DOM or the router: they ask for a
 * tab (and optionally what to show there) and the shell switches. The intent survives the
 * page swap, which is how "register a model, then benchmark it" stays one click.
 */

export type BenchmarkTab = "training" | "models" | "compare";

export type BenchmarkIntent = {
  tab: BenchmarkTab;
  /** Controller spec to preselect in Compare, e.g. `model:generalist@v2`. */
  model?: string;
  network?: string;
  scenario?: string;
};

let pending: BenchmarkIntent | null = null;

/** Ask the shell to switch tabs, remembering what the destination should open. */
export function openBenchmark(intent: BenchmarkIntent): void {
  pending = intent;
  window.dispatchEvent(new CustomEvent("benchmark:navigate", { detail: intent }));
}

/** Consume the intent for this tab once; a later manual visit starts fresh. */
export function takeBenchmarkIntent(tab: BenchmarkTab): BenchmarkIntent | null {
  const intent = pending;
  pending = null;
  return intent && intent.tab === tab ? intent : null;
}
