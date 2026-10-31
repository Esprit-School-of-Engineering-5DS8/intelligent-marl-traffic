export interface ChartTokens {
  text: string;
  text2: string;
  muted: string;
  border: string;
  borderStrong: string;
  surface: string;
  surface2: string;
  accent: string;
  flow: string;
  dense: string;
  jam: string;
  emergency: string;
  /** verdict marks */
  good: string;
  critical: string;
  wide: string;
  /** the candidate's colour (also the verdict "non-inferior": the candidate holds) */
  candidate: string;
  font: string;
  mono: string;
  dark: boolean;
}

/** Colours of the current theme, read from the CSS custom properties. */
export function readTokens(): ChartTokens {
  const style = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    text: v("--text", "#e8eef4"),
    text2: v("--text-2", "#a9b7c5"),
    muted: v("--muted", "#8495a6"),
    border: v("--border", "#232e3a"),
    borderStrong: v("--border-strong", "#364555"),
    surface: v("--surface", "#0f151c"),
    surface2: v("--surface-2", "#151d26"),
    accent: v("--accent", "#e8eef4"),
    flow: v("--flow", "#38c980"),
    dense: v("--dense", "#f2a33a"),
    jam: v("--jam", "#f06063"),
    emergency: v("--emergency", "#5b97ff"),
    good: v("--good", "#0ca30c"),
    critical: v("--critical", "#d03b3b"),
    wide: v("--wide", "#8a8984"),
    candidate: v("--ctl-candidate", "#3987e5"),
    font: '"IBM Plex Sans", "IBM Plex Sans Arabic", system-ui, sans-serif',
    mono: '"IBM Plex Mono", ui-monospace, monospace',
    dark: document.documentElement.dataset.theme !== "light",
  };
}
