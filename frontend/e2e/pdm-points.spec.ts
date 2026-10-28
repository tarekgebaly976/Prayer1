import { expect, test } from "@playwright/test";
import { login, pick } from "./helpers";

test("new measurement point on equipment added from the form gets an automatic code; list filters by tree and search", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/pdm");
  await page.getByRole("button", { name: "New measurement point" }).click();
  const form = page.getByRole("dialog");
  await pick(page, "Asset", "PM1-WIRE-UTW-DR1", /^PM1-WIRE-UTW-DR1 — /);
  await form.getByRole("button", { name: "+ Add equipment under the selected asset" }).click();
  const eq = page.getByRole("dialog", { name: "New asset" });
  const code = `PM1-DR1-MTR${Date.now() % 100000}`;
  await eq.getByLabel("Code").fill(code);
  await eq.getByRole("textbox", { name: /^Name/ }).first().fill("Drive motor");
  await eq.getByRole("button", { name: "Create" }).click();
  await expect(eq).toBeHidden();
  await expect(form.getByPlaceholder(`Automatic: ${code}-CM..`)).toBeVisible();
  await form.getByRole("button", { name: "Create" }).click();
  await expect(form).toBeHidden();
  await expect(page.getByRole("cell", { name: `${code}-CM01` })).toBeVisible();

  await page.getByRole("button", { name: "Hierarchy" }).first().click();
  const tree = page.getByRole("dialog");
  await tree.getByText(/^PM — /).click();
  await tree.getByRole("button", { name: "PM1", exact: true }).click();
  await expect(tree).toBeHidden();
  await expect(page.getByRole("cell", { name: "TMP-DR1-DS" })).toBeVisible();
  await page.getByPlaceholder("Point, equipment code or name").fill(code);
  await expect(page.getByRole("cell", { name: `${code}-CM01` })).toBeVisible();
  await expect(page.getByRole("cell", { name: "TMP-DR1-DS" })).toBeHidden();
});

test("reliability engineer marks a point Critical and it moves to the top of the technician's list", async ({ page, browser }) => {
  await login(page, "reliability");
  await page.goto("/pdm");
  await page.getByRole("cell", { name: "TMP-DR1-DS" }).click();
  const prio = page.locator(".mantine-SegmentedControl-root"); // priority control in the point panel
  await prio.getByText("Critical", { exact: true }).click();
  await expect(page.locator("tbody tr").first()).toContainText("TMP-DR1-DS");

  const tech = await (await browser.newContext()).newPage();
  await login(tech, "tech1");
  await tech.goto("/pdm");
  await expect(tech.locator("tbody tr").first()).toContainText("TMP-DR1-DS");
  await tech.locator("tbody tr").first().click();
  await expect(tech.getByText("Priority:")).toBeHidden(); // technicians see the order, not the control

  await prio.getByText("Normal", { exact: true }).click(); // leave the demo data as it was
  await expect(prio.locator("input[value='3']")).toBeChecked();
  await page.getByRole("button", { name: "Close" }).click(); // back to the full-width list
  await expect(prio).toBeHidden();
});

test("priorities in bulk: download the list, upload changes, preview, apply", async ({ page }) => {
  await login(page, "planner");
  await page.goto("/pdm");
  await page.getByRole("button", { name: "Priorities (Excel)" }).click();
  const dlg = page.getByRole("dialog");
  const dl = page.waitForEvent("download");
  await dlg.getByRole("button", { name: "Download points with priorities" }).click();
  expect((await dl).suggestedFilename()).toBe("measurement_point_priorities.xlsx");
  const csv = (prio: string) => ({ name: "prio.csv", mimeType: "text/csv", buffer: Buffer.from(`point_code,priority\nTMP-DR1-DS,${prio}\n`) });
  await dlg.locator('input[type="file"]').setInputFiles(csv("High"));
  await dlg.getByRole("button", { name: "Preview" }).click();
  await expect(dlg.getByTestId("prio-preview")).toContainText("1 point(s) will change");
  await dlg.getByRole("button", { name: "Apply priorities" }).click();
  await expect(dlg).toBeHidden();
  await expect(page.locator("tbody tr").first()).toContainText("TMP-DR1-DS");
  await expect(page.locator("tbody tr").first()).toContainText("High");

  await page.getByRole("button", { name: "Priorities (Excel)" }).click(); // put the demo data back
  await dlg.locator('input[type="file"]').setInputFiles(csv("Normal"));
  await dlg.getByRole("button", { name: "Preview" }).click();
  await dlg.getByRole("button", { name: "Apply priorities" }).click();
  await expect(dlg).toBeHidden();
});

test("readings history import: preview and import past values into the trend", async ({ page }) => {
  await login(page, "reliability");
  await page.goto("/pdm");
  await page.getByRole("button", { name: "Import readings history" }).click();
  const dlg = page.getByRole("dialog");
  const dl = page.waitForEvent("download");
  await dlg.getByRole("button", { name: /Download template/ }).click();
  expect((await dl).suggestedFilename()).toBe("condition_readings_import.xlsx");
  const csv = "point_code,date,time,value,note\nTMP-DR1-DS,2026-01-10,,61.5,history\nTMP-DR1-DS,2026-01-17,09:30,62.0,history\n";
  await dlg.locator('input[type="file"]').setInputFiles({ name: "hist.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await dlg.getByRole("button", { name: "Preview" }).click();
  await expect(dlg.getByTestId("hist-preview")).toContainText(/(2 readings on 1 points|2 already imported)/); // re-runs find them already there
  if (await dlg.getByRole("button", { name: "Import", exact: true }).isEnabled()) {
    await dlg.getByRole("button", { name: "Import", exact: true }).click();
    await expect(dlg).toBeHidden();
  }
});
