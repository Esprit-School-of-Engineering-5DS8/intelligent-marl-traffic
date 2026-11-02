import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

import { read } from "./data";

// The pages of the defence story: how the controller decides, the LLM in the loop, the
// large cities. Every number checked here is read from the same exported files.

const main = (page: Page) => page.getByRole("main");

async function open(page: Page, path: string, title: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible({
    timeout: 20_000,
  });
}

const exported = (file: string) =>
  existsSync(fileURLToPath(new URL(`../../public/data/${file}`, import.meta.url)));

test.describe("defence story", () => {
  test("how it works: five layers, and the bias computed live", async ({ page }) => {
    const study = read<{ candidate: { beta: number } }>("combined/study.json");
    await open(page, "/how-it-works", "Comment décide notre contrôleur ?");
    const pipeline = main(page).getByRole("region", { name: "Les cinq couches d'une décision" });
    await expect(pipeline.getByRole("listitem")).toHaveCount(5);

    const slider = main(page).getByRole("slider");
    // just below the threshold e^beta / (1 + e^beta): Max-Pressure keeps the light
    const threshold = (100 * Math.exp(study.candidate.beta)) / (1 + Math.exp(study.candidate.beta));
    await slider.fill(String(Math.floor(threshold * 10) / 10 - 1));
    await expect(
      main(page).getByText("Résultat : la phase de Max-Pressure est appliquée."),
    ).toBeVisible();
    await slider.fill("99.9");
    await expect(
      main(page).getByText("Résultat : la phase de l'agent est appliquée."),
    ).toBeVisible();
    // in the "fluidité" mode, Max-Pressure decides whatever the agent's confidence
    await main(page).getByRole("radio", { name: "Fluidité" }).click();
    await expect(
      main(page).getByText("Résultat : la phase de Max-Pressure est appliquée."),
    ).toBeVisible();
  });

  test("the LLM in the loop: its decisions, its reasons, its guardrails", async ({ page }) => {
    test.skip(!exported("combined/llm_loop.json"), "no LLM-loop export yet");
    const loop = read<{ validRate: number; timeline: { calls: { reason: string }[] } }>(
      "combined/llm_loop.json",
    );
    await open(page, "/llm", "Le LLM dans la boucle de décision");
    await expect(main(page).getByRole("img", { name: /^Modes choisis par le LLM/ })).toBeVisible();
    const decisions = main(page).getByRole("region", { name: "Ses décisions, une par une" });
    await expect(decisions.getByRole("listitem")).toHaveCount(loop.timeline.calls.length);
    await expect(decisions).toContainText(loop.timeline.calls[0]!.reason);
    await expect(
      main(page).getByRole("region", { name: "Pourquoi il ne peut pas faire de dégât" }),
    ).toContainText(`Réponses valides : ${Math.round(100 * loop.validRate)} %`);
    await expect(main(page).getByText("Exploratoire").first()).toBeVisible();
  });

  test("large cities: the street maps and every controller", async ({ page }) => {
    test.skip(!exported("combined/cities.json"), "no large-city export yet");
    const cities = read<{ cities: { network: string; lights: number; driven: number }[] }>(
      "combined/cities.json",
    );
    await open(page, "/cities", "Et dans une vraie grande ville ?");
    for (const c of cities.cities) {
      await expect(
        main(page).getByRole("img", {
          name: `Plan du réseau : ${c.lights} feux, dont ${c.driven} pilotés par nos agents.`,
        }),
      ).toBeVisible();
    }
    await expect(main(page).getByText("Exploratoire").first()).toBeVisible();
  });
});
