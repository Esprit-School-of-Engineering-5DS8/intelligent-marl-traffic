import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { read } from "./data";

// The pages on the combined study: every number they show is read here from the same
// exported files (scripts/dashboard_combined.py, scripts/combined_figures.py).

interface TestRow {
  family: string;
  network: string;
  scenario: string;
  demand: string;
  metric: "travel" | "waiting";
  gain: number;
  verdict: string;
}

const final = read<{
  worstGap: { candidate: number; othersMin: number; othersMax: number };
  ambulances: { peak: { faster: number; total: number } };
  tests: { total: number; best: number; noninf: number };
}>("final_controller.json");
const study = read<{ episodes: number; prereg: string; tests: number; variantsTried: number }>(
  "combined/study.json",
);
const tests = read<{ tests: TestRow[] }>("combined/tests.json").tests.filter(
  (t) => t.family === "hybrid",
);

const one = new Intl.NumberFormat("fr", { maximumFractionDigits: 1 });
const signed = (v: number) => `${v > 0 ? "+" : ""}${one.format(v)} %`;
const find = (network: string, scenario: string, demand: string, metric: string) => {
  const t = tests.find(
    (x) =>
      x.network === network &&
      x.scenario === scenario &&
      x.demand === demand &&
      x.metric === metric,
  );
  if (!t) throw new Error(`no test ${network} ${scenario} ${demand} ${metric}`);
  return t;
};

const main = (page: Page) => page.getByRole("main");

async function open(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
}

test.describe("combined study", () => {
  test("home: the three key numbers, the rigour banner and the four layers", async ({ page }) => {
    await open(page, "/");
    const numbers = main(page).getByRole("region", { name: "Trois chiffres à retenir" });
    const worst = numbers.getByRole("region", { name: /Pire écart au meilleur contrôleur/ });
    await expect(worst).toContainText(`${one.format(final.worstGap.candidate)} %`, {
      timeout: 20_000,
    });
    await expect(worst).toContainText(`${one.format(final.worstGap.othersMax)} %`);
    const peak = final.ambulances.peak;
    await expect(
      numbers.getByRole("region", { name: /Trajets d'ambulance plus rapides/ }),
    ).toContainText(`${peak.faster} / ${peak.total}`);
    const sensors = find("grid4x4", "sensor_noise", "peak", "waiting");
    const tile = numbers.getByRole("region", { name: /Attente sous capteurs bruités/ });
    await expect(tile).toContainText(signed(sensors.gain));
    await expect(tile).toContainText("Prouvée meilleure");
    await expect(tile).toContainText("Pré-enregistré");

    const rigour = main(page).getByRole("list", { name: "La rigueur de l'évaluation" });
    await expect(rigour).toContainText(study.prereg);
    await expect(rigour).toContainText(new Intl.NumberFormat("fr").format(study.episodes));
    await expect(rigour).toContainText(`${study.variantsTried} variantes`);

    const layers = main(page).getByRole("region", { name: /Comment décide la candidate/ });
    await expect(layers.getByRole("listitem")).toHaveCount(4);
    await expect(
      main(page).getByRole("region", { name: "Ce qu'on ne peut pas affirmer" }),
    ).toBeVisible();
  });

  test("final controller: the forest plot and the final table follow the filters", async ({
    page,
  }) => {
    await open(page, "/final-controller");
    const table = main(page).getByRole("region", {
      name: "Tests de non-infériorité de la candidate contre la meilleure référence.",
    });
    // header + every preregistered test
    await expect(table.getByRole("row")).toHaveCount(study.tests + 1, { timeout: 20_000 });

    await main(page).getByRole("radio", { name: "Quartier réel (OSM)" }).click();
    const district = tests.filter((t) => t.network === "real_district");
    await expect(table.getByRole("row")).toHaveCount(district.length + 1);
    await expect(main(page).getByRole("img", { name: /^Quartier réel \(OSM\) :/ })).toBeVisible();
    await expect(
      main(page).getByRole("img", { name: /^Grille 4x4 · cas principaux :/ }),
    ).toHaveCount(0);

    // only the true losses, both networks
    await main(page).getByRole("radio", { name: "Tous" }).first().click();
    for (const v of ["Prouvée meilleure", "Prouvée non inférieure", "Trop large pour conclure"]) {
      await main(page)
        .getByRole("button", { name: new RegExp(`^${v}`) })
        .click();
    }
    const losses = tests.filter((t) => t.verdict === "loss" || t.verdict === "lossBeyond");
    await expect(table.getByRole("row")).toHaveCount(losses.length + 1);
    const first = losses.find((t) => t.network === "grid4x4" && t.scenario === "normal")!;
    await expect(table).toContainText(signed(first.gain));
  });

  test("final controller: the ablation tab, with the validation ranking", async ({ page }) => {
    await open(page, "/final-controller");
    await main(page).getByRole("tab", { name: "Ablation des couches" }).click();
    await expect(main(page).getByRole("img", { name: /^Gain de chaque couche/ })).toBeVisible({
      timeout: 20_000,
    });
    const ranking = main(page).getByRole("region", {
      name: "Tableau : Comment la candidate a été choisie",
    });
    await expect(ranking.getByRole("rowheader", { name: /H2 β = 4 \(retenue\)/ })).toBeVisible();
    await expect(ranking.getByRole("rowheader", { name: "H2 β = 8" })).toBeVisible();
    await expect(ranking.getByRole("row")).toHaveCount(study.variantsTried + 1);
  });

  test("robustness: each situation's preregistered tests, and the stopped big city", async ({
    page,
  }) => {
    await open(page, "/robustness");
    const cases: [string, string, string, string][] = [
      ["Capteurs bruités", "grid4x4", "sensor_noise", "peak"],
      ["Avec des bus", "grid4x4", "buses", "medium"],
      ["Grille 8x8, sans réentraînement", "grid8x8", "normal", "peak"],
    ];
    for (const [title, network, scenario, demand] of cases) {
      const card = main(page).getByRole("region", { name: new RegExp(`^${title}`) });
      for (const metric of ["travel", "waiting"]) {
        await expect(card).toContainText(signed(find(network, scenario, demand, metric).gain), {
          timeout: 20_000,
        });
      }
    }
    const loss = find("grid8x8", "normal", "peak", "travel");
    expect(loss.verdict).toBe("loss");
    await expect(
      main(page)
        .getByRole("region", { name: /^Grille 8x8/ })
        .getByText("Vraie perte")
        .first(),
    ).toBeVisible();
    const city = main(page).getByRole("region", { name: /Une grande ville : tentative arrêtée/ });
    await expect(city.getByText("Arrêté", { exact: true })).toBeVisible();
    await expect(city).toContainText("ne sont pas des résultats d'évaluation");
  });

  test("command palette: Ctrl+K, search without accents, arrows and Enter", async ({ page }) => {
    await open(page, "/settings");
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Palette de commandes" });
    await expect(palette).toBeVisible();
    await page.keyboard.type("controleur");
    await expect(palette.getByRole("option").first()).toHaveText(/Contrôleur final/);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/final-controller$/);
    await expect(palette).toHaveCount(0);

    const before = await page.locator("html").getAttribute("data-theme");
    await page.keyboard.press("Control+k");
    await page.keyboard.type("theme");
    await page.keyboard.press("Enter");
    await expect(page.locator("html")).toHaveAttribute(
      "data-theme",
      before === "dark" ? "light" : "dark",
    );
  });
});

for (const theme of ["dark", "light"] as const) {
  test.describe(`accessibility of the new views (${theme})`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => {
        localStorage.setItem(
          "cotraffic-settings",
          JSON.stringify({
            state: {
              theme: t,
              language: "fr",
              timeUnit: "s",
              speedUnit: "kmh",
              dataSource: "mock",
              llmProvider: "ollama",
            },
            version: 1,
          }),
        );
      }, theme);
    });

    const axe = (page: Page) =>
      new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .exclude("canvas")
        .analyze()
        .then((r) =>
          r.violations.map((v) => `${v.id}: ${v.nodes.length} (${v.nodes[0]?.target.join(" ")})`),
        );

    test("the ablation tab has no WCAG A/AA violation", async ({ page }) => {
      await open(page, "/final-controller");
      await main(page).getByRole("tab", { name: "Ablation des couches" }).click();
      await expect(main(page).getByRole("img", { name: /^Gain de chaque couche/ })).toBeVisible({
        timeout: 20_000,
      });
      await page.waitForTimeout(800);
      expect(await axe(page)).toEqual([]);
    });

    test("the open command palette has no WCAG A/AA violation", async ({ page }) => {
      await open(page, "/");
      await page.keyboard.press("Control+k");
      await expect(page.getByRole("dialog", { name: "Palette de commandes" })).toBeVisible();
      await page.waitForTimeout(400);
      expect(await axe(page)).toEqual([]);
    });
  });
}
