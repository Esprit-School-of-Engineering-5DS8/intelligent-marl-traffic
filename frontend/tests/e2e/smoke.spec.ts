import { expect, test } from "@playwright/test";

test.describe("smoke", () => {
  test("opens the overview without console errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Vue d'ensemble" })).toBeVisible();
    await expect(page).toHaveTitle("Vue d'ensemble - CoTraffic");
    expect(errors).toEqual([]);
  });

  test("reaches every page from the sidebar", async ({ page }) => {
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Navigation principale" });
    const links = nav.getByRole("link");
    const count = await links.count();
    expect(count).toBe(10);

    for (let i = 0; i < count; i += 1) {
      const link = links.nth(i);
      const name = (await link.innerText()).trim();
      await link.click();
      await expect(link).toHaveAttribute("aria-current", "page");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
    }
  });

  test("starts keyboard navigation with the skip link", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Aller au contenu" });
    await expect(skip).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeFocused();
  });

  test("switches to Arabic, right to left, and remembers it", async ({ page }) => {
    await page.goto("/settings");
    const main = page.getByRole("main");
    await main.getByLabel("Langue").selectOption("ar");
    await main.getByRole("button", { name: "Enregistrer" }).click();

    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");

    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("الإعدادات");
  });
});
