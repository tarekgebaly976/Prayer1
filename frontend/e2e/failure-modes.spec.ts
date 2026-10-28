import path from "node:path";
import { expect, test } from "@playwright/test";
import { login, pick } from "./helpers";

test("failure-mode catalogue: import, equipment types, request with standard symptom, Pareto", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/admin");
  await page.getByRole("tab", { name: "Departments / Failure codes" }).click();
  await page.getByRole("button", { name: "Import failure codes (Excel)" }).first().click();
  const imp = page.getByRole("dialog");
  await imp.locator('input[type="file"]').setInputFiles(path.join(__dirname, "fixtures", "failure_codes.xlsx"));
  await imp.getByRole("button", { name: "Preview" }).click();
  await expect(imp.getByTestId("fc-preview")).toContainText("0 with errors");
  await expect(imp.getByTestId("fc-preview")).toContainText("Gearboxes");
  await imp.getByRole("button", { name: "Import", exact: true }).click();
  await expect(imp).toBeHidden();

  await page.goto("/assets");
  await page.getByRole("button", { name: "Equipment types" }).click();
  const cls = page.getByRole("dialog");
  await cls.getByRole("button", { name: "Preview" }).click();
  await expect(cls.getByTestId("classify-preview")).toBeVisible();
  const apply = cls.getByRole("button", { name: /^Apply to/ });
  if (await apply.isEnabled()) await apply.click(); // disabled on a re-run: every recognisable asset already has a type
  else await page.keyboard.press("Escape");
  await expect(cls).toBeHidden();

  await page.goto("/requests");
  await page.getByRole("button", { name: "New work request" }).click();
  const req = page.getByRole("dialog");
  await pick(page, "Asset", "PM1-WIRE-UTW-DR1-GBX", /^PM1-WIRE-UTW-DR1-GBX — /);
  await req.getByRole("combobox", { name: /^Symptoms/ }).click();
  await page.getByRole("option", { name: "Abnormal noise" }).click();
  await req.getByRole("combobox", { name: /Suspected failure mode/ }).click();
  await expect(page.getByText("For this equipment (Gearboxes)")).toBeVisible(); // the gearbox modes come first
  await page.getByRole("option", { name: /^Gear tooth wear/ }).click();
  await expect(req.getByRole("textbox", { name: /^Title/ })).toHaveValue("Abnormal noise – Gear tooth wear");
  await req.getByRole("button", { name: "Submit" }).click();
  await expect(req).toBeHidden();
  await expect(page.getByRole("cell", { name: "Abnormal noise – Gear tooth wear" }).first()).toBeVisible();

  await page.goto("/kpis");
  await page.getByRole("tab", { name: "Failure modes" }).click();
  await expect(page.getByText(/Counts work orders/)).toBeVisible();
});
