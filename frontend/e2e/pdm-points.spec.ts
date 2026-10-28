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
