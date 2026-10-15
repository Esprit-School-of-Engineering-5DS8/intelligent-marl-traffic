import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import type { Language } from "@/features/settings/store";

import ar from "./locales/ar.json";
import en from "./locales/en.json";
import fr from "./locales/fr.json";

export const LANGUAGES: Record<Language, { label: string; dir: "ltr" | "rtl" }> = {
  fr: { label: "Français", dir: "ltr" },
  en: { label: "English", dir: "ltr" },
  ar: { label: "العربية", dir: "rtl" },
};

void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr }, en: { translation: en }, ar: { translation: ar } },
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
