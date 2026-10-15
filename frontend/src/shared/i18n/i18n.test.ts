import { afterEach, describe, expect, it } from "vitest";

import i18n, { applyLanguage } from "@/shared/i18n";

import ar from "./locales/ar.json";
import en from "./locales/en.json";
import fr from "./locales/fr.json";

function keys(tree: object, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "object" && value !== null
      ? keys(value as object, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

describe("translations", () => {
  afterEach(() => applyLanguage("fr"));

  it("English and Arabic define exactly the French keys", () => {
    const reference = keys(fr).sort();
    expect(keys(en).sort()).toEqual(reference);
    expect(keys(ar).sort()).toEqual(reference);
  });

  it("no translation is left empty", () => {
    for (const language of ["fr", "en", "ar"] as const) {
      const empty = keys(fr).filter((key) => {
        const value: unknown = i18n.getResource(language, "translation", key);
        return typeof value !== "string" || value.trim() === "";
      });
      expect(empty, language).toEqual([]);
    }
  });

  it("Arabic switches the document to right to left", () => {
    applyLanguage("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(document.documentElement.lang).toBe("ar");
    expect(i18n.t("nav.settings")).toBe(ar.nav.settings);

    applyLanguage("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(i18n.t("nav.settings")).toBe(en.nav.settings);
  });
});
