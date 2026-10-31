import { expect, test, type Page } from "@playwright/test";

import { fr, mean, meta, read, test as stat } from "./data";

// Every page, with the real numbers it must show (read from the exported results).
async function open(page: Page, path: string, title: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible({
    timeout: 20_000,
  });
}

const main = (page: Page) => page.getByRole("main");

test.describe("pages", () => {
  test("overview: KPIs of COOP-FULL against FT, from the results", async ({ page }) => {
    await open(page, "/", "Vue d'ensemble");
    const wait = mean("grid4x4", "normal", "peak", "coop_full", "mean_waiting_time");
    const ref = mean("grid4x4", "normal", "peak", "ft", "mean_waiting_time");
    const gain = stat("grid4x4", "normal", "peak", "coop_full", "ft", "mean_waiting_time");
    const card = main(page).getByRole("region", { name: "Attente moyenne aux feux" });
    await expect(card).toContainText(`${fr(wait)} s`);
    await expect(card).toContainText(`${fr(ref)} s`);
    await expect(card).toContainText(fr(gain.pairedImprovementPct ?? 0));
    await expect(card).toContainText(gain.significant ? "significatif" : "non significatif");
    await expect(main(page).getByRole("img", { name: /par contrôleur/ })).toBeVisible();
    await expect(
      main(page).getByRole("img", { name: "Véhicules arrêtés au fil de l'épisode" }),
    ).toBeVisible();
    await expect(main(page).getByText("Provenance des données")).toBeVisible();
  });

  test("overview: changing the network updates the numbers", async ({ page }) => {
    await open(page, "/", "Vue d'ensemble");
    await main(page).getByLabel("Réseau").selectOption("real_district");
    const wait = mean("real_district", "normal", "peak", "coop_full", "mean_waiting_time");
    await expect(
      main(page).getByRole("region", { name: "Attente moyenne aux feux" }),
    ).toContainText(`${fr(wait)} s`);
  });

  test("live map: side-by-side replay plays", async ({ page }) => {
    test.skip(meta.replays.length === 0, "no replay recorded (scripts/record_replay.py)");
    await open(page, "/live-map", "Carte en direct");
    // the reference replay of the demonstration when present, otherwise the first one
    const replay =
      meta.replays.find((r) => r.id === "grid4x4__emergency__peak__s3") ?? meta.replays[0]!;
    await main(page).getByLabel("Replay").selectOption(replay.id);
    await expect(main(page).locator("canvas").first()).toBeVisible({ timeout: 20_000 });
    const label = (m: string) => m.toUpperCase().replace(/_/g, "-");
    await expect(
      main(page).getByRole("region", { name: label(replay.left), exact: true }),
    ).toBeVisible();
    await expect(
      main(page).getByRole("region", { name: label(replay.right), exact: true }),
    ).toBeVisible();
    const slider = main(page).getByLabel("Temps de simulation");
    const before = Number(await slider.inputValue());
    await main(page).getByRole("button", { name: "Lecture" }).click();
    await expect
      .poll(async () => Number(await slider.inputValue()), { timeout: 10_000 })
      .toBeGreaterThan(before);
    await main(page).getByRole("button", { name: "Pause" }).click();
    // layout changes used to send deck.gl and React into an update loop (error panel)
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    await main(page).getByRole("button", { name: "Suivre le véhicule d'urgence" }).click();
    await main(page)
      .getByRole("button", { name: label(replay.right), exact: true })
      .click();
    await main(page).getByRole("button", { name: "Côte à côte" }).click();
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.waitForTimeout(1500);
    await expect(page.getByText("Cette partie de l'écran a rencontré une erreur")).toHaveCount(0);
    expect(errors.filter((e) => e.includes("Maximum update depth"))).toEqual([]);
  });

  test("3D simulation: scene renders", async ({ page }) => {
    test.skip(meta.replays.length === 0, "no replay recorded (scripts/record_replay.py)");
    await open(page, "/simulation-3d", "Simulation 3D");
    const canvas = main(page).locator("canvas").first();
    const noWebgl = main(page).getByText("La 3D demande WebGL");
    await expect(canvas.or(noWebgl)).toBeVisible({ timeout: 20_000 });
    await expect(
      main(page).getByRole("button", { name: "Recentrer la vue" }).or(noWebgl),
    ).toBeVisible();
  });

  test("RL agents: learning curves and explained decisions", async ({ page }) => {
    await open(page, "/agents", "Agents RL");
    await expect(main(page).getByText("Algorithme : PPO")).toBeVisible({ timeout: 20_000 });
    await expect(main(page).getByRole("img", { name: "Récompense par épisode" })).toBeVisible();
    const decisions = main(page).getByRole("region", { name: "Décisions expliquées" });
    await expect(decisions.getByRole("row").nth(1)).toBeVisible({ timeout: 20_000 });
    await expect(main(page).getByText("Décisions corrigées par le bouclier")).toBeVisible();
  });

  test("comparative analysis: forest plot, gain map and tests", async ({ page }) => {
    await open(page, "/analytics", "Analyse comparative");
    await expect(main(page).getByRole("img", { name: "Gain par scénario" })).toBeVisible({
      timeout: 20_000,
    });
    await expect(main(page).getByRole("img", { name: "Carte des gains" })).toBeVisible();
    const table = main(page).getByRole("region", { name: "Tests statistiques" });
    await expect(table.getByRole("row").nth(1)).toBeVisible();
    expect(await table.getByRole("row").count()).toBeGreaterThan(10);
    // waiting-time distribution (its open-ended last bin once made every file fail validation)
    await expect(main(page).getByRole("img", { name: "Distribution des attentes" })).toBeVisible();
    await expect(main(page).getByText("Impossible de charger les données")).toHaveCount(0);
  });

  test("scenarios: replays listed, launching needs the backend", async ({ page }) => {
    await open(page, "/scenarios", "Scénarios");
    await expect(main(page).getByRole("button", { name: "Carte", exact: true })).toHaveCount(
      meta.replays.length,
    );
    await expect(main(page).getByRole("button", { name: "Lancer la simulation" })).toBeDisabled();
    await expect(
      main(page).getByText("Disponible avec la source « Backend en direct »").first(),
    ).toBeVisible();
  });

  test("pedestrians: pedestrian waiting from the results", async ({ page }) => {
    await open(page, "/pedestrians", "Piétons");
    const wait = mean("grid4x4", "pedestrians", "peak", "coop_full", "ped_mean_waiting_time");
    await expect(
      main(page).getByRole("region", { name: "Attente moyenne des piétons" }),
    ).toContainText(`${fr(wait)} s`, {
      timeout: 20_000,
    });
    await expect(
      main(page).getByRole("img", { name: "Compromis piétons / véhicules" }),
    ).toBeVisible();
  });

  test("emergency: emergency-vehicle delay from the results", async ({ page }) => {
    await open(page, "/emergency", "Urgences");
    const delay = mean("grid4x4", "emergency", "peak", "coop_full", "ev_delay");
    await expect(
      main(page).getByRole("region", { name: "Retard des véhicules d'urgence" }),
    ).toContainText(`${fr(delay)} s`, {
      timeout: 20_000,
    });
    await expect(
      main(page).getByRole("img", { name: "Effet sur les autres usagers" }),
    ).toBeVisible();
  });

  test("final controller: key messages, figures and demo from the results", async ({ page }) => {
    const final = read<{
      tests: { total: number; best: number; noninf: number };
      worstGap: { candidate: number };
      ambulances: { peak: { faster: number; total: number } };
    }>("final_controller.json");
    await open(page, "/final-controller", "Contrôleur final");
    const messages = main(page).getByRole("region", { name: "Messages clés" });
    const worst = new Intl.NumberFormat("fr", { maximumFractionDigits: 1 });
    await expect(messages).toContainText(`${worst.format(final.worstGap.candidate)} %`, {
      timeout: 20_000,
    });
    const peak = final.ambulances.peak;
    await expect(messages).toContainText(`${peak.faster} / ${peak.total}`);
    const shown = final.tests.best + final.tests.noninf;
    await expect(messages).toContainText(`${shown} / ${final.tests.total}`);
    for (const name of [/pire écart de 12 %/, /Forest plot/, /Barres : la candidate/]) {
      await expect(main(page).getByRole("img", { name })).toBeVisible();
    }
    const demo = main(page).getByRole("img", { name: /Deux vues SUMO/ });
    await expect(demo).toHaveAttribute("src", /demo\.png$/);
    await main(page).getByRole("button", { name: "Lancer l'enregistrement" }).click();
    await expect(demo).toHaveAttribute("src", /demo\.gif$/);
  });

  test("settings: minutes are applied everywhere", async ({ page }) => {
    await open(page, "/settings", "Paramètres");
    await main(page).getByLabel("Durées").selectOption("min");
    await main(page).getByRole("button", { name: "Enregistrer" }).click();
    await page
      .getByRole("navigation", { name: "Navigation principale" })
      .getByRole("link", { name: "Vue d'ensemble" })
      .click();
    const minutes = mean("grid4x4", "normal", "peak", "coop_full", "mean_waiting_time") / 60;
    await expect(
      main(page).getByRole("region", { name: "Attente moyenne aux feux" }),
    ).toContainText(`${fr(minutes)} min`);
  });
});
