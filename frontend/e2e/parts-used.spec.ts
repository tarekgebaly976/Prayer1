import { expect, test } from "@playwright/test";
import { login, pick } from "./helpers";

test("supervisor records a spare part used on a work order and finds it in the parts-used report", async ({ page }) => {
  const title = `E2E seal change ${Date.now()}`;
  await login(page, "mech.sup");
  await page.goto("/work-orders/new");
  await pick(page, "Asset", "PM1-WIRE-UTW-DR1-BRG-DS");
  await page.locator('input[name="title"]').fill(title);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/work-orders\/[0-9a-f-]{36}$/);
  const heading = (await page.getByRole("heading", { name: title }).textContent()) ?? "";
  const number = heading.split(" · ")[0].trim();

  await page.getByRole("tab", { name: "Materials" }).click();
  await pick(page, /Spare part \(search/, "23148", /BRG-23148/);
  await page.getByLabel("Quantity").first().fill("2");
  await page.getByRole("button", { name: "Add part used" }).click();
  await expect(page.getByRole("cell", { name: "Spherical roller bearing 23148 CCK/W33" })).toBeVisible();
  await expect(page.getByRole("cell", { name: /19,600/ }).first()).toBeVisible(); // 2 × 9,800 book cost

  await page.goto("/inventory");
  await page.getByRole("tab", { name: "Parts used" }).click();
  await expect(page.getByRole("link", { name: number })).toBeVisible();
});
