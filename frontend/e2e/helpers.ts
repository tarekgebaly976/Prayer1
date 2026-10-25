import { expect, type Page } from "@playwright/test";

export const PASSWORD = process.env.E2E_PASSWORD ?? "Demo-Passw0rd!2026";
export const user = (k: string) => `${k}@demo.example.com`;

export async function login(page: Page, who: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/email|البريد/i).fill(user(who));
  await page.locator('input[name="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: /sign in|دخول/i }).click();
  await expect(page).toHaveURL(/\/$/);
  // Tests must not depend on a language preference saved by an earlier test.
  const csrf = (await page.context().cookies()).find((c) => c.name === "cmms_csrf")?.value ?? "";
  const res = await page.request.post("/api/v1/auth/locale", { data: { locale: "en" }, headers: { "X-CSRF-Token": csrf } });
  expect(res.status()).toBe(204);
  if ((await page.locator("html").getAttribute("lang")) !== "en") await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
}

export async function logout(page: Page): Promise<void> {
  await page.getByTestId("account-menu").click();
  await page.getByRole("menuitem", { name: /sign out|تسجيل الخروج/i }).click();
  await expect(page).toHaveURL(/\/login/);
}

/** Pick an option in a searchable Mantine Select by its label. */
export async function pick(page: Page, label: string | RegExp, search: string, option?: RegExp): Promise<void> {
  const input = page.getByRole("combobox", { name: label, exact: typeof label === "string" }).first();
  await input.click();
  await input.fill(search);
  await page.getByRole("option", { name: option ?? new RegExp(search) }).first().click();
}
