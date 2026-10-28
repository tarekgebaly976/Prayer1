import path from "node:path";
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("manager adds a shift type and previews a roster grid with an unknown name", async ({ page }) => {
  await login(page, "manager");
  await page.goto("/shifts");
  await page.getByRole("tab", { name: "Shift types" }).click();
  const code = `T${Date.now() % 100000}`;
  await page.getByRole("button", { name: "New shift type" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Code").fill(code);
  await dialog.getByLabel("Name").fill("Test general 10h");
  await dialog.getByLabel("Hours").fill("10");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("cell", { name: code, exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Import roster (Excel)" }).click();
  const imp = page.getByRole("dialog");
  await imp.locator('input[type="file"]').setInputFiles(path.join(__dirname, "fixtures", "roster.xlsx"));
  await imp.getByRole("button", { name: "Preview" }).click();
  await expect(imp.getByText("Zz Unknown Technician")).toBeVisible();
  await expect(imp.getByRole("button", { name: "Import", exact: true })).toBeDisabled(); // manager cannot create users
});
