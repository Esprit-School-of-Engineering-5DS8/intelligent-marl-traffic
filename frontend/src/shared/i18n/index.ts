import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import type { Language } from "@/features/settings/store";

import ar from "./locales/ar.json";
import en from "./locales/en.json";
import fr from "./locales/fr.json";
import pending from "./locales/pending.fr.json";

export const LANGUAGES: Record<Language, { label: string; dir: "ltr" | "rtl" }> = {
  fr: { label: "Français", dir: "ltr" },
  en: { label: "English", dir: "ltr" },
  ar: { label: "العربية", dir: "rtl" },
};

/**
 * The new pages are written in French first (pending.fr.json): until their English and
 * Arabic translations exist, those two languages show the French text (fallbackLng), never
 * a raw key.
 */
export const PENDING = pending;

void i18n.use(initReactI18next).init({
  resources: {
    fr: { translation: { ...fr, ...pending } },
    en: { translation: en },
    ar: { translation: ar },
  },
  lng: "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false }, // React escapes
  returnNull: false,
});

/** Switch the interface language, its direction (Arabic: right to left) and <html lang>. */
export function applyLanguage(language: Language): void {
  void i18n.changeLanguage(language);
  document.documentElement.lang = language;
  document.documentElement.dir = LANGUAGES[language].dir;
}

export default i18n;
