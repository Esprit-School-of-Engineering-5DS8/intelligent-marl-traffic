import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// WCAG 2.1 A and AA rules on every page, in the dark (default) and light themes
const PAGES = [
  "/",
  "/analytics",
  "/agents",
  "/pedestrians",
  "/emergency",
  "/scenarios",
  "/assistant",
  "/settings",
];

for (const theme of ["dark", "light"] as const) {
  test.describe(`accessibility (${theme})`, () => {
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
    for (const path of PAGES) {
      test(`${path} has no WCAG A/AA violation`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
        await page.waitForLoadState("networkidle");
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          // chart canvases are images with a text alternative and a data table
          .exclude("canvas")
          .analyze();
        const summary = results.violations.map(
          (v) => `${v.id}: ${v.nodes.length} (${v.nodes[0]?.target.join(" ")})`,
        );
        expect(summary).toEqual([]);
      });
    }
  });
}
