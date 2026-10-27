import path from "node:path";
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("manager uploads the company KPI sheet and enters a month in the app", async ({ page }) => {
  await login(page, "manager");
  await page.goto("/kpis");
  await page.getByRole("tab", { name: "Company KPIs" }).click();
  await page.locator('input[type="file"]').setInputFiles(path.join(__dirname, "fixtures", "kpi_scorecard.xlsx"));
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByText(/1 KPI · 14 values · 0 cleared · 0 with errors/)).toBeVisible();
  await page.getByRole("button", { name: "Import", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: "E2E MTTR - PM" });
  await expect(row).toBeVisible();

  const value = String(1 + (Date.now() % 9)); // differs between reruns
  await page.getByRole("button", { name: "Enter month" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Month").click();
  await page.getByRole("option", { name: "Nov 2026" }).click();
  const card = dialog.locator(".mantine-Card-root").filter({ hasText: "E2E MTTR - PM" });
  await expect(card.getByLabel("Target")).toHaveValue("2"); // prefilled
  await card.getByLabel("Actual").fill(value);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(row.getByRole("cell").nth(13)).toContainText(value); // Nov column: KPI, label, YTD, Jan..Nov
});
