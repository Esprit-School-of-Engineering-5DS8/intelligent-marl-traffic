import { useEffect, useSyncExternalStore } from "react";

import { useSettings, type ThemeChoice } from "../features/settings/store";
import { applyLanguage } from "../shared/i18n";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function subscribe(onChange: () => void): () => void {
  if (typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY).matches : true;
}

/** The theme actually shown: "system" follows the operating system and its changes. */
export function useResolvedTheme(): Exclude<ThemeChoice, "system"> {
  const choice = useSettings((s) => s.theme);
  const prefersDark = useSyncExternalStore(subscribe, systemPrefersDark);
  if (choice !== "system") return choice;
  return prefersDark ? "dark" : "light";
}

/** Keeps <html data-theme>, lang and dir in step with the settings. */
export function useDocumentSettings(): void {
  const theme = useResolvedTheme();
  const language = useSettings((s) => s.language);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    applyLanguage(language);
  }, [language]);
}
