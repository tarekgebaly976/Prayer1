import { expect, test } from "@playwright/test";
import { login, pick } from "./helpers";

test("supervisor records LOTO isolation points and signs off the permit", async ({ page }) => {
  await login(page, "mech.sup");
  await page.goto("/work-orders/new");
  await pick(page, "Asset", "PM1-WIRE-UTW-DR1-BRG-DS");
  await page.locator('input[name="title"]').fill(`E2E isolate drive ${Date.now()}`);
  await page.getByLabel("LOTO required").check();
  await page.getByLabel("Permit required").check();
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/work-orders\/[0-9a-f-]{36}$/);

  await page.getByLabel("Isolation point (e.g. MCC-3 breaker Q12)").fill("MCC-3 breaker Q12");
  await page.getByLabel("Lock / tag no.").fill("L-04");
  await page.getByLabel("Zero energy verified").check();
  await page.getByRole("button", { name: "Apply lock" }).click();
  await expect(page.getByText("1 lock(s) still applied — remove before completing")).toBeVisible();

  await page.getByLabel("Permit reference").fill("CWP-2026-0412");
  // Mantine MultiSelect keeps its text input zero-width until opened: click the visible field box.
  await page.locator('label:has-text("Permit types")').locator("xpath=..").locator(".mantine-MultiSelect-input").click();
  await page.getByRole("option", { name: "Electrical", exact: true }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Sign off LOTO / permit" }).click();
  await expect(page.getByText(/Signed by: .* · /)).toBeVisible();
  await expect(page.getByText(/CWP-2026-0412.*Electrical/)).toBeVisible();

  await page.getByRole("button", { name: "Remove lock" }).click();
  await expect(page.getByText("1 lock(s) still applied")).toHaveCount(0);
});
