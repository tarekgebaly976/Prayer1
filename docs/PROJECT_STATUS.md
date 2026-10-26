# Project status — 2026-10-25

## Completed
* Milestone 1 — Foundation: repository, PostgreSQL schema (73 tables) with 3 Alembic migrations, least-privilege DB
  roles, Argon2 auth with server-side sessions + CSRF, RBAC (11 roles, 48 permissions), multi-plant tenancy with
  department restriction, asset hierarchy (Plant→Department→Line→Unit→Assembly→Sub-assembly→Component), QR codes,
  responsive app shell (EN/AR RTL, PWA).
* Milestone 2 — Core maintenance: work requests & triage, work-order lifecycle with configurable transitions and
  safety/testing/emergency guards, labour/materials/services costing, checklists, attachments, idempotent PM engine
  (calendar fixed/floating, meter), deferral/cancellation approvals, audit trail.
* Milestone 3 — Planning & materials: lubrication (points, routes, approved alternatives, consumption, missed alerts),
  shifts (patterns, rosters, leave/overtime/callout, manpower vs demand, handovers), inventory (ledger, reservations,
  issues/returns, moving average valuation, POs, stockouts, aging/excess).
* Milestone 4 — Reliability & management: rule-based condition monitoring with alerts/escalation/WOs and gateway
  ingestion, 20 KPIs with drill-down/trends/exports, shutdowns with CPM/Gantt/readiness, notifications + e-mail outbox,
  background worker.
* Milestone 5 (partial) — import/export (CSV/XLSX with previews and error reports, PDF/XLSX reports), Docker images,
  Compose stack with automatic TLS, CI workflow, deploy template, backup/restore scripts and drill, load test,
  security review, documentation set.

## In progress
* —

## Blocked
* **Cloud deployment (criterion L):** trial deployment done on 2026-10-26: Oracle Cloud Always Free VM (Riyadh, Ampere A1 2 OCPU/12 GB, Ubuntu 24.04), installed with `deploy/install-server.sh`, served at https://84-8-106-22.sslip.io (Let's Encrypt). The owner signed in and reached the dashboard on a desktop browser. Nightly backup cron installed (02:15 server time, UTC) after re-running the installer. Opened and signed in on a real Android phone (2026-10-26). Not yet done: a first verified backup/restore on the server, and a production deployment (managed DB/PITR, monitoring) approved by the company's IT.
* SMTP delivery and S3/GCS storage verification: need provider credentials.

## Tested
* 60/60 backend tests, 8/8 E2E (local and HTTPS Compose), restore drill, load test, read-after-write regression.
  Details: TEST_REPORT.md.

## Not yet tested
* Real phones/tablets and real camera QR scanning; real SMTP; real S3/GCS; GitHub Actions run; accessibility audit;
  penetration test; production-scale performance on target infrastructure.

## Next actions
1. Provide a GCP (or AWS/Azure) project and approval → run the one-time setup in DEPLOYMENT.md and the deploy workflow.
2. Push CI to GitHub and fix anything environment-specific in the first run.
3. Pilot with one department; collect feedback on forms and workflow transitions.
4. Implement SSO/MFA and the offline technician mode (roadmap items 2–3).
