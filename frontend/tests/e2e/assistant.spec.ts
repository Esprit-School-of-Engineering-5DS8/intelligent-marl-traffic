import { expect, test, type Page } from "@playwright/test";

import { fr, mean, summary, test as stat } from "./data";

// The assistant without backend: every answer must carry the numbers of the result files,
// its sources, and never start an action by itself.

async function openAssistant(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
  await page.keyboard.press("Control+k");
  const panel = page.getByRole("dialog", { name: "Assistant" });
  await expect(panel).toBeVisible();
  // the suggestions become clickable once the results are loaded
  await expect(panel.getByRole("button", { name: /^Compare COOP-FULL et FT/ })).toBeEnabled({
    timeout: 20_000,
  });
  return panel;
}

async function ask(page: Page, question: string) {
  const panel = page.getByRole("dialog", { name: "Assistant" });
  await panel.getByLabel("Votre question").fill(question);
  await panel.getByLabel("Votre question").press("Enter");
  const answer = panel.getByRole("log").getByRole("listitem").last();
  // the answer is complete when its sources or its "written by" line appear
  await expect(answer.getByText("Rédigé par le code à partir des résultats")).toBeVisible({
    timeout: 15_000,
  });
  return answer;
}

test.describe("assistant (no backend)", () => {
  test("compares two controllers with the paired test and its sources", async ({ page }) => {
    await openAssistant(page);
    const answer = await ask(
      page,
      "COOP-FULL est-il meilleur que FT sur l'attente en pointe sur la grille ?",
    );
    const a = mean("grid4x4", "normal", "peak", "coop_full", "mean_waiting_time");
    const b = mean("grid4x4", "normal", "peak", "ft", "mean_waiting_time");
    const t = stat("grid4x4", "normal", "peak", "coop_full", "ft", "mean_waiting_time");
    await expect(answer).toContainText(`${fr(a)} s contre ${fr(b)} s`);
    await expect(answer).toContainText(fr(Math.abs(t.pairedImprovementPct ?? 0)));
    await expect(answer).toContainText(t.significant ? "(significatif)" : "(non significatif)");
    await expect(answer).toContainText("results/summary/comparisons_mean_waiting_time.csv");
    // the comparison table drawn from the same numbers
    await expect(answer.getByRole("table", { name: "Comparaison" })).toContainText(`${fr(a)} s`);
  });

  test("says when the learned agent is worse (no flattering)", async ({ page }) => {
    await openAssistant(page);
    const answer = await ask(
      page,
      "Les véhicules d'urgence passent-ils plus vite avec COOP-FULL qu'avec EV-RULE-MP ?",
    );
    const coop = mean("grid4x4", "emergency", "peak", "coop_full", "ev_delay");
    const rule = mean("grid4x4", "emergency", "peak", "ev_rule_mp", "ev_delay");
    await expect(answer).toContainText(`${fr(coop)} s contre ${fr(rule)} s`);
    await expect(answer).toContainText(coop > rule ? "moins bien" : "mieux");
  });

  test("names the best controller, computed from the results", async ({ page }) => {
    await openAssistant(page);
    const answer = await ask(
      page,
      "Quel est le meilleur contrôleur sur l'attente en pointe dans le quartier réel ?",
    );
    const ranked = summary
      .filter(
        (r) =>
          r.network === "real_district" &&
          r.scenario === "normal" &&
          r.demand === "peak" &&
          r.metric === "mean_waiting_time" &&
          r.mean !== null,
      )
      .sort((x, y) => (x.mean ?? 0) - (y.mean ?? 0));
    const labels: Record<string, string> = {
      mp: "MP",
      coop_full: "COOP-FULL",
      coop: "COOP",
      act: "ACT",
      ft: "FT",
      ind: "IND",
    };
    await expect(answer).toContainText(
      `le meilleur contrôleur est ${labels[ranked[0]!.method] ?? ranked[0]!.method}`,
    );
  });

  test("draws a chart in the conversation", async ({ page }) => {
    await openAssistant(page);
    const answer = await ask(page, "Montre le graphique du CO2 sur le quartier réel");
    await expect(answer).toContainText("CO2 total par contrôleur");
    await expect(answer.getByRole("img", { name: /CO2 total · Quartier réel/ })).toBeVisible();
  });

  test("opens a junction on the map only when the user clicks", async ({ page }) => {
    await openAssistant(page);
    const answer = await ask(page, "Montre le carrefour B2");
    await expect(page).toHaveURL(/\/$/);
    await answer.getByRole("button", { name: "Ouvrir le carrefour B2 sur la carte" }).click();
    await expect(page).toHaveURL(/\/live-map$/);
    await expect(page.getByRole("heading", { name: "Carrefour B2" })).toBeVisible({
      timeout: 20_000,
    });
  });

  test("never launches a simulation without the backend and a confirmation", async ({ page }) => {
    await openAssistant(page);
    const answer = await ask(page, "Lance une simulation urgences sur la grille");
    await expect(answer).toContainText("demande le backend");
    await expect(answer.getByRole("button", { name: "Confirmer le lancement" })).toHaveCount(0);
  });

  test("answers in English when the interface is in English", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("main").getByLabel("Langue").selectOption("en");
    await page.getByRole("main").getByRole("button", { name: "Enregistrer" }).click();
    await page.keyboard.press("Control+k");
    const panel = page.getByRole("dialog", { name: "Assistant" });
    await expect(panel.getByRole("button", { name: /^Compare COOP-FULL and FT/ })).toBeEnabled({
      timeout: 20_000,
    });
    await panel
      .getByLabel("Your question")
      .fill("Is COOP-FULL better than FT on waiting at peak on the grid?");
    await panel.getByLabel("Your question").press("Enter");
    const a = mean("grid4x4", "normal", "peak", "coop_full", "mean_waiting_time");
    const b = mean("grid4x4", "normal", "peak", "ft", "mean_waiting_time");
    const en = (v: number) => new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(v);
    await expect(panel.getByRole("log")).toContainText(`${en(a)} s vs ${en(b)} s`, {
      timeout: 15_000,
    });
  });
});
