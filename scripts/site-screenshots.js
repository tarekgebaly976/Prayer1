#!/usr/bin/env node
// Phone screenshots for the website (site/public/img/<dir>/*.webp, 540 x 960) from a LOCAL copy of the app with the
// public demo's sample plant. Never point it at a real system.
//
//   cd backend && CMMS_DEMO_PASSWORD='Demo-Passw0rd!2026' .venv/bin/python -m app.cli seed-demo --profile general
//   .venv/bin/uvicorn app.main:app --port 8000 &                     # no CMMS_INSTANCE_LABEL: no DEMO badge on the shots
//   cd ../frontend && npm run build && BACKEND_URL=http://127.0.0.1:8000 npx next start -p 3000 &
//   node scripts/site-screenshots.js site/public/img/v4               # needs Playwright (require('playwright'))
//
// The file names are those used in site/public/index.html; put new shots in a NEW folder (v4, v5 …) and change the
// paths in index.html, so phones do not keep showing cached old images.
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = process.env.APP_URL ?? "http://127.0.0.1:3000";
const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Passw0rd!2026";
const out = path.resolve(process.argv[2] ?? "site/public/img/v4");
const PHONE = { viewport: { width: 405, height: 720 }, deviceScaleFactor: 4 / 3, isMobile: true, hasTouch: true }; // → 540 x 960

async function session(browser, who, lang = "en") {
  const ctx = await browser.newContext(PHONE);
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.waitForLoadState("networkidle");
  await page.locator('input[name="email"]').fill(`${who}@demo.example.com`);
  await page.locator('input[name="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  // Same language every time (the preference is stored per user on the server).
  await page.locator('[aria-label="Language"], [aria-label="اللغة"], [aria-label="ভাষা"]').first().click();
  await page.getByRole("menuitem", { name: lang === "ar" ? "العربية" : "English" }).click();
  await page.waitForTimeout(800);
  const plant = await page.evaluate(async () => (await (await fetch("/api/v1/auth/me")).json()).plants[0].plant_id);
  const api = async (url) => (await page.request.get(`${BASE}/api/v1${url}`, { headers: { "X-Plant-Id": plant } })).json();
  return { ctx, page, api };
}

async function settle(page) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(1200); // charts animate
}

/** PNG from Playwright → WebP via the browser's own encoder (no extra tools). */
async function save(browser, png, name) {
  const page = await browser.newPage();
  const b64 = png.toString("base64");
  const webp = await page.evaluate(async (data) => {
    const img = new Image();
    img.src = `data:image/png;base64,${data}`;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.width; c.height = img.height;
    c.getContext("2d").drawImage(img, 0, 0);
    return c.toDataURL("image/webp", 0.82).split(",")[1];
  }, b64);
  await page.close();
  fs.writeFileSync(path.join(out, `${name}.webp`), Buffer.from(webp, "base64"));
  console.log(`  ${name}.webp`);
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  const shot = async (page, name) => { await settle(page); await save(browser, await page.screenshot(), name); };

  // Maintenance manager: dashboard, equipment, request, work order, PM, condition monitoring, KPIs
  const m = await session(browser, "manager");
  await m.page.goto(`${BASE}/`); await shot(m.page, "dashboard");

  const asset = (await m.api("/assets?q=L1-MIX-M1-DRV-BRG-DE&limit=5")).items.find((a) => a.code === "L1-MIX-M1-DRV-BRG-DE");
  await m.page.goto(`${BASE}/assets/${asset.id}`); await shot(m.page, "asset");
  await m.page.getByText("QR label", { exact: false }).first().scrollIntoViewIfNeeded();
  await m.page.evaluate(() => window.scrollBy(0, 160)); await shot(m.page, "asset-qr");
  await m.page.evaluate(() => window.scrollTo(0, 0));
  await m.page.getByRole("button", { name: "New work request" }).first().click();
  const dlg = m.page.getByRole("dialog");
  await dlg.locator('input[name="req-title"]').fill("Abnormal noise at mixer drive-end bearing");
  await dlg.getByLabel("Description").fill("Loud grinding noise since morning shift, housing hot to touch.");
  await shot(m.page, "request");
  await m.page.keyboard.press("Escape");

  const wo = (await m.api("/work-orders?q=WO-DMO-000100&limit=1")).items[0];
  await m.page.goto(`${BASE}/work-orders/${wo.id}`); await shot(m.page, "wo");

  await m.page.goto(`${BASE}/pm`); await shot(m.page, "pm");

  await m.page.goto(`${BASE}/pdm`); await settle(m.page);
  await m.page.getByTestId("table-cards").getByText("VIB-MIX-DE", { exact: true }).click();
  await shot(m.page, "pdm-trend");
  await m.page.keyboard.press("Escape");

  await m.page.goto(`${BASE}/kpis`); await settle(m.page);
  // The last six months (the default is the month so far, often too little data for a picture).
  const from = new Date(); from.setMonth(from.getMonth() - 6);
  await m.page.getByLabel("From", { exact: true }).fill(from.toISOString().slice(0, 10));
  await settle(m.page);
  await m.page.getByTestId("kpi-mtbf").click();
  await m.page.getByRole("dialog").locator(".recharts-wrapper").first().scrollIntoViewIfNeeded();
  await shot(m.page, "kpi-trend");
  await m.page.keyboard.press("Escape");
  await m.page.getByRole("tab", { name: /failure/i }).click(); await settle(m.page);
  await m.page.locator(".recharts-wrapper").first().scrollIntoViewIfNeeded();
  await m.page.evaluate(() => window.scrollBy(0, 120)); await shot(m.page, "pareto");
  await m.page.goto(`${BASE}/`);
  await m.ctx.close();

  // Technician: own work list
  const tech = await session(browser, "tech1");
  await tech.page.goto(`${BASE}/my-work`); await shot(tech.page, "mywork");
  await tech.ctx.close();

  // Arabic interface (manager), then back to English so the demo account stays as it was
  const ar = await session(browser, "manager", "ar");
  await ar.page.goto(`${BASE}/`); await shot(ar.page, "dashboard-ar");
  await ar.page.locator('[aria-label="اللغة"]').first().click();
  await ar.page.getByRole("menuitem", { name: "English" }).click();
  await ar.ctx.close();

  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
