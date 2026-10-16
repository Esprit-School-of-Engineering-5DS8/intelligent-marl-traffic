import { defineConfig, devices } from "@playwright/test";

const port = 4175;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  // the preview server answers slowly on Windows under parallel load
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://localhost:${port}`,
    trace: "on-first-retry",
    locale: "fr-FR",
    viewport: { width: 1440, height: 900 },
    launchOptions: {
      // SLOWMO=400 npx playwright test --headed: slowed down to be watched during a demo
      slowMo: Number(process.env.SLOWMO ?? 0),
      // software WebGL, so the 3D view also renders on machines without a GPU
      args: ["--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  // the production build, as it will be served
  webServer: {
    command: `npm run build && npm run preview -- --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
  },
});
