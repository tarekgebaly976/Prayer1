import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("planner imports a PM plan from a file and the tasks become one plan", async ({ page }) => {
  await login(page, "planner");
  await page.goto("/pm");
  await page.getByRole("button", { name: "Import plan" }).click();
  const dialog = page.getByRole("dialog");
  // A frequency in days that no earlier run used keeps the generated plan code unique across reruns.
  const days = 200 + (Date.now() % 150);
  const csv = [
    "asset_code,frequency,task,trade,duration_min,crew,shutdown_required",
    `PM1-WIRE-UTW-DR1,${days},1. Clean drive motor 2. Check base bolts,Mechanical,30,1,no`,
    `PM1-WIRE-UTW-DR1,${days},Inspect coupling,Mechanical,15,1,no`,
  ].join("\n");
  await dialog.locator('input[type="file"]').setInputFiles({ name: "pm.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await dialog.getByRole("button", { name: "Preview" }).click();
  await expect(dialog.getByText(/2 · 2 valid · 0 with errors · 1 plans/)).toBeVisible();
  await dialog.getByRole("button", { name: "Import", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText(`PM1-WIRE-UTW-DR1-D${days}-MECH`).first()).toBeVisible();
});
