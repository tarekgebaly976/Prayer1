# Test report

All results below were produced by actually executing the tests on 2026-10-25 in the development container
(4 vCPU, PostgreSQL 16 on the same host). Nothing here is extrapolated.

## Summary

| Suite | Executed | Passed | Failed | Notes |
|---|---|---|---|---|
| Backend unit + API integration (pytest, real PostgreSQL 16, app runs as least-privilege role) | 60 | 60 | 0 | line coverage **84 %** (`app/`) |
| Browser E2E (Playwright, Chromium) — local `next start` + `uvicorn` | 8 | 8 | 0 | 7 desktop + 1 Pixel 7 emulation |
| Browser E2E — **Docker Compose stack over HTTPS (Caddy)**, final images | 8 | 8 | 0 | same suite, `https://localhost` |
| Backup → restore drill (throw-away PostgreSQL container) | 1 | 1 | 0 | 74 tables, 739 rows, 0 mismatches, 4 s |
| Migration up → down → up + model/schema drift check | 1 | 1 | 0 | part of pytest (`test_zz_migrations.py`) |
| Read-after-write across 2 API worker processes | 40 | 40 | 0 | regression for defect D4 below |
| Load test (20 concurrent users, 40 s) | 1 | 1 | 0 | see Performance |

| Static analysis | Result |
|---|---|
| ruff (lint incl. bandit-style security rules) | clean |
| ESLint (next config) | clean |
| TypeScript `strict` + `noUncheckedIndexedAccess` | clean |
| mypy (backend) | **78 findings, not gating** — mostly `Optional` narrowing after `db.get()` and float/Decimal assignment to ORM columns; none found to be a runtime defect so far (one variable-shadowing finding was fixed). Tracked as tech debt. |
| pip-audit (backend lockfile) | no known vulnerabilities |
| npm audit (production deps) | 0 vulnerabilities (after upgrading Next.js to 16.4.3 for critical advisories) |

## Coverage by requirement area

| Area | Tests |
|---|---|
| Authentication & sessions | HttpOnly/Secure/SameSite cookie, lockout + generic errors (no user enumeration), CSRF, logout revocation, revocation on disable, password policy, security headers, unknown-field rejection, health checks |
| Authorization & tenancy | cross-plant header denied, cross-plant object ids 404/422, permission matrix per role, department-restricted membership, independent numbering per plant, UI+API admin denial (E2E) |
| Asset hierarchy | level ordering, department consistency, duplicate codes, subtree move with path rewrite, ancestors, QR lookup, status history, import preview/errors/duplicates/all-or-nothing commit, CSV export formula-injection |
| Work orders | full lifecycle request→closure (API and **UI E2E incl. phone viewport**), emergency fast-track and closure permission, LOTO gate, test-result gate, failure-code/root-cause gate, configurable transitions, cancellation reason, optimistic locking, bulk assignment, assignment conflicts (overlap, leave), PDF report |
| PM scheduling | month-end arithmetic, idempotent generation, **6 concurrent scheduler runs → no duplicates**, floating basis next-due, checklist completion gate, deferral four-eyes approval, meter-based trigger, meter monotonicity |
| Lubrication | route generation idempotent, unapproved substitute rejected, approved alternative accepted, quantity variance warning, completion gate, next-due, QR, missed-task notification once, compliance KPI |
| Shifts | pattern roster generation preserving leave, roster conflicts, manpower supply, handover submit/lock/confirm, self-confirmation forbidden, notifications |
| Inventory | moving-average valuation, reserve/issue/return with WO costing, stockout recording, negative stock prevention, adjustment rules, **25 concurrent issues on 10 units → exactly 10 succeed, stock 0**, append-only ledger, PO receipt/over-receipt, aging/excess, parts import duplicates |
| Condition monitoring | warning/critical evaluation, escalation without duplicate alerts, notification, acknowledge → WO → resolve, auto-WO on critical, limit validation, future timestamps rejected, unknown without limits, gateway token auth/dedup/revocation |
| KPIs | MTTR, MTBF, availability, breakdown downtime, cost/ton, budget vs actual, OEE, emergency %, planned %, cost by department, PM compliance, overdue, backlog (hours & weeks) — **asserted against hand-computed values**; unavailable states with reasons; drill-down; trend; XLSX/PDF export |
| Shutdowns | CPM critical path, float, planned dates, cycle detection, readiness %, weighted progress, delay, pre-startup check gate |
| Files | type/magic validation (exe, mismatched PDF, SVG, HTML-in-text rejected), size limit, cross-plant download 404, upload permission, uploader-only delete, soft delete |
| Notifications | dedupe, outbox `disabled` without SMTP, read/unread, cross-user isolation, breakdown request alerts |
| i18n / PWA | Arabic RTL switch persisted per user (E2E), manifest, service worker, offline indicator (E2E) |

## Performance (measured)

Data set: 100,027 assets, 50,001 work orders (synthetic, `LT-` prefix, demo plant). API: 2 uvicorn workers.
Same host also ran PostgreSQL, the Next.js server and the full Docker Compose stack.

```
users=20 duration=40s requests=3036 throughput=75.6 req/s errors=0 expected_403=184
endpoint                    n   p50 ms   p95 ms   p99 ms  err  403
wo_list_page              415      190      418      546    0    0
wo_search                 424      166      370      500    0    0
wo_detail                 434      272      528      706    0    0
asset_search              430      140      327      475    0    0
asset_children_100k       433      200      381      502    0    0
dashboard                 415      221      454      557    0    0
kpis_month                485      472     1037     1221    0  184
```
The 403s are technicians calling the KPI endpoint without `kpi.view` (expected). These figures describe this test
environment only; they are not a production capacity claim. Targets proposed for production acceptance: p95 < 1 s for
list/detail endpoints and < 2 s for the KPI dashboard at 50 concurrent users on the target infrastructure.

## Defects found by testing and fixed

| # | Found by | Defect | Fix |
|---|---|---|---|
| D1 | integration tests | Self-deadlock: stockout recorded in a second session while the request held `FOR UPDATE` row locks (FK check needs `FOR KEY SHARE`) | all row locks changed to `FOR NO KEY UPDATE` |
| D2 | integration tests | `rowcount` is −1 for ORM-executed `INSERT … ON CONFLICT`: duplicate-detection logic wrong (could double-queue e-mails, wrong roster counts) | switched to `RETURNING` |
| D3 | integration tests | parts import crashed (selected column treated as entity); missing DB grants after schema recreate | fixed; grants now applied by migration 0002 |
| D4 | load test | **Read-your-writes race**: DB session committed after the response was sent → first request after login 401 across workers | `Depends(get_db, scope="function")` everywhere + regression test |
| D5 | load test | Asset tree endpoint unpaginated (100k children → 60 s timeouts) | paginated tree API + UI "more" |
| D6 | load test | Backlog/overdue KPIs materialised every open WO (7–8 s each) | SQL aggregates + capped drill-down |
| D7 | load test | substring search scanned 100k rows | `pg_trgm` GIN indexes (migration 0003) |
| D8 | E2E | brittle selectors / locale leaking between tests | test fixes |
| D9 | dependency audit | Next.js 16.4.0 critical advisories | upgraded to 16.4.3 |
| D10 | review | Availability showed 100 % when no downtime was recorded, without caveat | explicit data-completeness note in KPI result and UI |

## Outstanding defects / not tested
* `app/worker.py` scheduling loop is exercised manually (jobs ran and recorded `job_runs` in the local and Compose
  environments) but has no automated test; the job functions themselves are covered.
* SMTP delivery not tested against a real mail server (no provider configured); retry logic is code-reviewed only.
* S3/GCS storage backend not tested against a real bucket (no credentials); local backend tested.
* Real mobile devices and real camera QR scanning not tested (Chromium device emulation + manual code entry only).
* Screen-reader/accessibility audit not performed.
* No penetration test.
* GitHub Actions CI workflow committed but not yet executed on GitHub.

## Security findings
No open findings from the automated checks above. Accepted risks and follow-ups are listed in SECURITY.md
(`'unsafe-inline'` scripts in CSP, no MFA/SSO yet, per-process rate limiting, no RLS, no malware scanning, no pentest).
