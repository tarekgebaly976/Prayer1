import { expect, test } from "@playwright/test";
import { login, pick } from "./helpers";

test("planner downloads an A4 sheet of QR labels for a line and everything below it", async ({ page }) => {
  await login(page, "planner");
  await page.goto("/assets");
  await page.getByRole("button", { name: "Print QR labels" }).click();
  const dialog = page.getByRole("dialog");
  await pick(page, /Asset and everything below it/, "PM1-WIRE");
  const wait = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "Download PDF" }).click();
  const file = await wait;
  expect(file.suggestedFilename()).toMatch(/^QR_labels_PM1-WIRE.*\.pdf$/);
  const path = await file.path();
  const head = (await import("node:fs")).readFileSync(path).subarray(0, 4).toString();
  expect(head).toBe("%PDF");
  await expect(dialog).toBeHidden();
});
