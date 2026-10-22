export interface ChartTokens {
  text: string;
  text2: string;
  muted: string;
  border: string;
  surface: string;
  surface2: string;
  accent: string;
  flow: string;
  dense: string;
  jam: string;
  emergency: string;
  font: string;
}

/** Colours of the current theme, read from the CSS custom properties. */
export function readTokens(): ChartTokens {
  const style = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    text: v("--text", "#e6edf3"),
    text2: v("--text-2", "#a7b6c4"),
    muted: v("--muted", "#8193a4"),
    border: v("--border", "#26323f"),
    surface: v("--surface", "#111921"),
    surface2: v("--surface-2", "#17212b"),
    accent: v("--accent", "#9a8cff"),
    flow: v("--flow", "#38c980"),
    dense: v("--dense", "#f2a33a"),
    jam: v("--jam", "#f06063"),
    emergency: v("--emergency", "#5b97ff"),
    font: '"IBM Plex Sans", "IBM Plex Sans Arabic", system-ui, sans-serif',
  };
}
