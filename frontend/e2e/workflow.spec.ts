import { expect, test } from "@playwright/test";
import { login, logout, pick } from "./helpers";

test("login rejects a wrong password with a generic message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill("tech1@demo.example.com");
  await page.locator('input[name="password"]').fill("wrong-password");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByTestId("login-error")).toContainText("Invalid email or password");
});

test("work order lifecycle through the UI: create → approve → assign → execute → review → close", async ({ page, browser }) => {
  const title = `E2E bearing noise ${Date.now()}`;
  await login(page, "planner");
  await page.goto("/work-orders/new");
  await pick(page, "Asset", "PM1-WIRE-UTW-DR1-BRG-DS");
  await page.locator('input[name="title"]').fill(title);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/work-orders\/[0-9a-f-]{36}$/);
  const woUrl = page.url();
  await expect(page.getByTestId("wo-status")).toHaveText("Triage");
  await page.getByTestId("to-awaiting_approval").click();
  await page.getByTestId("transition-confirm").click();
  await expect(page.getByTestId("wo-status")).toHaveText("Awaiting approval");
  // planner has no approval permission: no approve button rendered (backend also enforces)
  await expect(page.getByTestId("to-approved")).toHaveCount(0);
  await logout(page);

  await login(page, "mech.sup");
  await page.goto(woUrl);
  await page.getByTestId("to-approved").click();
  await page.getByTestId("transition-confirm").click();
  await expect(page.getByTestId("wo-status")).toHaveText("Approved");
  await page.getByRole("tab", { name: "Details" }).click();
  await pick(page, "Assign", "Ahmed Saleh");
  await page.getByRole("button", { name: "Assign", exact: true }).click();
  await expect(page.getByText("Ahmed Saleh (Lead)")).toBeVisible();
  await logout(page);

  // Technician on a phone-sized viewport
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const tp = await phone.newPage();
  await login(tp, "tech1");
  await tp.goto("/my-work");
  await tp.getByTestId("my-wo-card").filter({ hasText: title }).click();
  await tp.getByTestId("to-in_progress").click();
  await tp.getByTestId("transition-confirm").click();
  await expect(tp.getByTestId("wo-status")).toHaveText("In progress");
  await tp.getByRole("tab", { name: "Labor" }).click();
  await tp.getByRole("button", { name: "Book labor" }).click();
  await expect(tp.getByText("1 h")).toBeVisible();
  await tp.getByRole("tab", { name: "Checklist" }).click();
  await tp.getByLabel("Findings").first().fill("Outer race spalling, replaced bearing");
  await tp.getByLabel("Root cause").fill("Insufficient lubrication");
  await tp.getByRole("button", { name: "Save" }).first().click();
  await tp.getByTestId("to-awaiting_review").click();
  await tp.getByTestId("transition-confirm").click();
  await expect(tp.getByTestId("wo-status")).toHaveText("Awaiting review / test");
  await phone.close();

  await login(page, "mech.sup");
  await page.goto(woUrl);
  // Corrective work needs problem/cause/remedy codes before completion
  await page.getByTestId("to-completed").click();
  await page.getByTestId("transition-confirm").click();
  await expect(page.getByText(/codes are required/)).toBeVisible();
  await page.keyboard.press("Escape");
  await pick(page, "Problem", "VIB");
  await pick(page, "Cause", "LUB");
  await pick(page, "Remedy", "REPL");
  await page.getByRole("button", { name: "Save" }).first().click();
  await expect(page.getByText("Saved").first()).toBeVisible();
  await page.getByTestId("to-completed").click();
  await page.getByTestId("transition-confirm").click();
  await expect(page.getByTestId("wo-status")).toHaveText("Completed");
  await page.getByTestId("to-closed").click();
  await page.getByTestId("transition-confirm").click();
  await expect(page.getByTestId("wo-status")).toHaveText("Closed");
  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByText("Omar Al-Shehri").first()).toBeVisible();

  // Persistence across a brand-new browser session
  const fresh = await browser.newContext();
  const fp = await fresh.newPage();
  await login(fp, "manager");
  await fp.goto(woUrl);
  await expect(fp.getByTestId("wo-status")).toHaveText("Closed");
  await fresh.close();
});

test("technician cannot reach administration (UI and API)", async ({ page }) => {
  await login(page, "tech1");
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);
  await page.goto("/admin");
  await expect(page.getByText("You do not have access to this page.")).toBeVisible();
  const me = await page.request.get("/api/v1/auth/me");
  const plant = (await me.json()).plants[0].plant_id as string;
  const r = await page.request.get("/api/v1/audit-logs", { headers: { "X-Plant-Id": plant } });
  expect(r.status()).toBe(403);
});

test("Arabic switches the interface to right-to-left", async ({ page }) => {
  await login(page, "manager");
  await page.getByRole("button", { name: "Language" }).click();
  await page.getByRole("menuitem", { name: "العربية" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.getByRole("link", { name: "أوامر العمل", exact: true })).toBeVisible();
  await page.reload(); // preference persisted server-side
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await page.getByRole("button", { name: "اللغة" }).click();
  await page.getByRole("menuitem", { name: "English" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});

test("QR code lookup opens the asset", async ({ page }) => {
  await login(page, "tech1");
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const plant = me.plants[0].plant_id as string;
  const list = await (await page.request.get("/api/v1/assets?q=PM1-WIRE-UTW-DR1-GBX", { headers: { "X-Plant-Id": plant } })).json();
  const token = list.items[0].qr_token as string;
  await page.goto("/scan");
  await page.getByTestId("qr-manual").fill(`cmms:asset:${token}`);
  await page.getByRole("button", { name: "Open" }).click();
  await expect(page).toHaveURL(/\/assets\//);
  await expect(page.getByRole("heading", { name: /PM1-WIRE-UTW-DR1-GBX/ })).toBeVisible();
});

test("condition reading above warning limit raises an alert", async ({ page }) => {
  await login(page, "reliability");
  await page.goto("/pdm");
  await page.getByRole("cell", { name: "TMP-DR1-DS" }).click();
  await page.getByTestId("reading-input").fill("79");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("reading-result")).toContainText("Warning");
  await page.getByRole("tab", { name: "Alerts" }).click();
  await expect(page.getByRole("cell", { name: /warning high/ }).first()).toBeVisible();
});

test("KPI dashboard shows unavailable KPIs with their reason and drill-down", async ({ page }) => {
  await login(page, "manager");
  await page.goto("/kpis");
  await expect(page.getByTestId("kpi-oee")).toContainText("Not available");
  await page.getByTestId("kpi-overdue_work_orders").click();
  await expect(page.getByText("Formula:")).toBeVisible();
});
