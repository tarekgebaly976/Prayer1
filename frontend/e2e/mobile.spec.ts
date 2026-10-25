import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("mobile shell, offline indicator and PWA assets", async ({ page, context }) => {
  await login(page, "tech1");
  await expect(page.getByRole("button", { name: "menu" })).toBeVisible(); // burger on small screens
  await expect(page.getByTestId("net-status")).toBeVisible();
  await context.setOffline(true);
  await expect(page.getByTestId("net-status")).toHaveAttribute("data-variant", "light");
  await page.getByTestId("net-status").hover();
  await expect(page.getByRole("tooltip", { name: /Offline — changes cannot be saved/ })).toBeVisible();
  await context.setOffline(false);
  const manifest = await page.request.get("/manifest.webmanifest");
  expect(manifest.ok()).toBeTruthy();
  expect((await manifest.json()).display).toBe("standalone");
  expect((await page.request.get("/sw.js")).ok()).toBeTruthy();
  await page.goto("/my-work");
  await expect(page.getByRole("heading", { name: "My work" })).toBeVisible();
});
