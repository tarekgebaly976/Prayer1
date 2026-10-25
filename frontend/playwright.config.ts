import { defineConfig, devices } from "@playwright/test";

// Runs against an already-running stack (see docs/TESTING.md): API on :8000 seeded with demo data, web on :3000.
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["junit", { outputFile: "test-results/e2e-junit.xml" }]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", ignoreHTTPSErrors: !!process.env.E2E_IGNORE_TLS, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] }, testIgnore: /mobile\.spec\.ts/ },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec\.ts/ },
  ],
});
