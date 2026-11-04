import { expect, test } from "@playwright/test";
import { login, logout, PASSWORD, user } from "./helpers";

const NEW_PASSWORD = "Changed-Passw0rd!2026";

async function changePassword(page: import("@playwright/test").Page, from: string, to: string): Promise<void> {
  await page.getByTestId("account-menu").click();
  await page.getByRole("menuitem", { name: /change password/i }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Current password").fill(from);
  await dialog.getByLabel("New password", { exact: true }).fill(to);
  await dialog.getByLabel("Repeat new password").fill(to);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/password changed/i)).toBeVisible();
  await expect(dialog).toBeHidden();
}

test("user changes own password and signs in with it", async ({ page }) => {
  await login(page, "store");
  await changePassword(page, PASSWORD, NEW_PASSWORD);
  await logout(page);

  await page.getByLabel(/email/i).fill(user("store"));
  await page.locator('input[name="password"]').fill(NEW_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/$/);

  // Restore the demo password so other tests and reruns keep working.
  await changePassword(page, NEW_PASSWORD, PASSWORD);
});

test("change password rejects a wrong current password", async ({ page }) => {
  await login(page, "store");
  await page.getByTestId("account-menu").click();
  await page.getByRole("menuitem", { name: /change password/i }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Current password").fill("Wrong-Passw0rd!2026");
  await dialog.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await dialog.getByLabel("Repeat new password").fill("Different-Passw0rd!1");
  await expect(dialog.getByText(/do not match/i)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Save" })).toBeDisabled();
  await dialog.getByLabel("Repeat new password").fill(NEW_PASSWORD);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/current password is incorrect/i)).toBeVisible();
});

test("public pages open without signing in; forgot password says to ask the administrator when e-mail is off", async ({ page }) => {
  await page.goto("/privacy"); // linked from the store listing: must not bounce to the sign-in page
  await expect(page.getByRole("heading", { name: /Privacy policy/ })).toBeVisible();
  await expect(page).toHaveURL(/\/privacy$/);

  await page.goto("/login");
  await page.getByTestId("forgot-link").click();
  await expect(page).toHaveURL(/\/forgot-password$/);
  // The test API has no mail server: no self-service reset, the page sends people to their administrator.
  await expect(page.getByTestId("reset-unavailable")).toBeVisible();

  await page.goto("/reset-password?token=not-a-real-token-but-long-enough&lang=ar");
  await expect(page).toHaveURL(/\/reset-password/);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl"); // the link's language
  await page.getByLabel(/كلمة المرور الجديدة/).first().fill("Another-Passw0rd!");
  await page.getByLabel(/أعد كتابة/).fill("Another-Passw0rd!");
  await page.getByRole("button", { name: "حفظ كلمة السر الجديدة" }).click();
  await expect(page.getByTestId("reset-bad-link")).toBeVisible();
});
