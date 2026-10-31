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

test("administrator assigns and clears a user's department from the users list", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/admin");
  const row = page.getByRole("row", { name: /store@demo\.example\.com/ });
  const field = row.getByPlaceholder("All departments");
  const clear = row.locator(".mantine-InputClearButton-root, .mantine-CloseButton-root").first();
  if (await clear.isVisible()) { await field.hover(); await clear.click(); } // left over from an interrupted run
  await expect(field).toHaveValue("");
  await field.click();
  await page.getByRole("option", { name: /^SP — / }).click();
  await expect(field).toHaveValue(/^SP — /);
  await field.hover();
  await clear.click(); // back to the whole plant
  await expect(field).toHaveValue("");
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
