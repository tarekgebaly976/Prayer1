import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("administrator edits a user from the Users list", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/admin");
  const row = page.getByRole("row", { name: /viewer@demo\.example\.com/ });
  await row.getByRole("button", { name: "Edit" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Reset password" })).toBeDisabled(); // needs a 12+ character password
  await expect(dialog.getByRole("button", { name: "Remove from plant" })).toBeVisible();
  const name = dialog.getByLabel("Name");
  const original = await name.inputValue();
  await name.fill(`${original} (edited)`);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: `${original} (edited)` })).toBeVisible();

  await page.getByRole("row", { name: /viewer@demo\.example\.com/ }).getByRole("button", { name: "Edit" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill(original);
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: original, exact: true })).toBeVisible();
});
