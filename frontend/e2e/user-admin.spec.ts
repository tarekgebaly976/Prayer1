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

test("administrator gives a user several departments and clears them from the users list", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/admin");
  const row = page.getByRole("row", { name: /store@demo\.example\.com/ });
  const field = row.getByLabel("Departments");
  const pills = row.locator(".mantine-Pill-label");
  const clear = row.locator(".mantine-InputClearButton-root, .mantine-CloseButton-root").last(); // "clear all", after the pills' own ✕
  await expect(field).toBeVisible(); // users loaded before looking for a left-over
  if (await pills.count()) { await field.hover(); await clear.click(); } // left over from an interrupted run
  await expect(pills).toHaveCount(0);
  await field.click();
  await page.getByRole("option", { name: "SP", exact: true }).click();
  await expect(pills).toHaveText(["SP"]);
  await page.getByRole("option", { name: "PM", exact: true }).click();
  await expect(pills).toHaveText(["SP", "PM"]);
  await page.keyboard.press("Escape");
  await page.reload(); // saved: the main department first
  await expect(pills).toHaveText(["SP", "PM"]);
  await field.hover();
  await clear.click(); // back to the whole plant
  await expect(pills).toHaveCount(0);
  await page.reload();
  await expect(pills).toHaveCount(0);
});

test("administrator imports users from Excel and gets their temporary passwords once", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/admin");
  await page.getByRole("button", { name: "Import users (Excel)" }).click();
  const dlg = page.getByRole("dialog");
  const dl = page.waitForEvent("download");
  await dlg.getByRole("button", { name: "Download current users" }).click();
  expect((await dl).suggestedFilename()).toBe("users.xlsx");
  const email = `e2e.import.${Date.now()}@example.com`;
  const csv = `full_name,email,role,department_code,trade,employee_no,hourly_rate,reset_password,old_email\nImported Tech,${email},technician,PM,mechanical,,,,\n`;
  await dlg.locator('input[type="file"]').setInputFiles({ name: "users.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await dlg.getByRole("button", { name: "Preview" }).click();
  await expect(dlg.getByTestId("users-preview")).toContainText("1 new");
  await dlg.getByRole("button", { name: "Import", exact: true }).click();
  await expect(dlg.getByText("1 added, 0 changed.")).toBeVisible();
  await expect(dlg.getByRole("cell", { name: email })).toBeVisible();
  const download = page.waitForEvent("download");
  await dlg.getByRole("button", { name: "Save passwords (CSV)" }).click();
  expect((await download).suggestedFilename()).toBe("new_passwords.csv");
});
