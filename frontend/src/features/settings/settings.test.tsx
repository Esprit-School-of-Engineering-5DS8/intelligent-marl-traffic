import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderApp } from "@/test/render";

import { DEFAULT_SETTINGS, useSettings } from "./store";

describe("settings store", () => {
  it("updates, persists and resets", () => {
    useSettings.getState().update({ language: "en", timeUnit: "min" });
    expect(useSettings.getState()).toMatchObject({ language: "en", timeUnit: "min" });
    expect(window.localStorage.getItem("cotraffic-settings")).toContain('"language":"en"');

    useSettings.getState().reset();
    expect(useSettings.getState()).toMatchObject(DEFAULT_SETTINGS);
  });
});

describe("settings page", () => {
  it("applies the language on save, including right-to-left for Arabic", async () => {
    const { user } = renderApp("/settings");
    await screen.findByRole("heading", { level: 1, name: "Paramètres" });
    const page = within(screen.getByRole("main"));
    await user.selectOptions(page.getByLabelText("Langue"), "ar");
    // not applied before saving
    expect(document.documentElement.dir).toBe("ltr");
    expect(page.getByRole("status")).toHaveTextContent("Modifications non enregistrées");

    await user.click(page.getByRole("button", { name: "Enregistrer" }));

    expect(useSettings.getState().language).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(await screen.findByRole("heading", { level: 1, name: "الإعدادات" })).toBeVisible();
  });

  it("follows a theme change made from the top bar", async () => {
    const { user } = renderApp("/settings");
    await screen.findByRole("heading", { level: 1, name: "Paramètres" });
    const theme = within(screen.getByRole("main")).getByLabelText("Thème");
    expect(theme).toHaveValue("dark");

    await user.click(screen.getByRole("button", { name: "Passer au thème clair" }));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(theme).toHaveValue("light");
  });
});
