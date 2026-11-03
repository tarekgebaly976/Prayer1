# Administrator manual

## First-time setup
1. Deploy (DEPLOYMENT.md) and run `python -m app.cli bootstrap ...` to create the organisation, first plant (with the
   six standard departments PM, SP, FH, WWTP, EAI, UTIL) and a **system administrator** (org-wide, all plants).
2. Sign in → **Administration**:
   * **Plant settings**: name, timezone (default Asia/Riyadh), currency (default SAR), working hours/day, settings JSON:
     `default_labor_rate`, `overtime_multiplier`, `repeat_failure_days`, `require_failure_codes_for`, `lube_grace_days`,
     `kpi` → `planned_types`, `emergency_basis` (`hours`|`count`), `include_planned_downtime`, `capacity_roles`.
   * **Departments** (add/rename, Arabic names), **Failure codes** (problem / cause / remedy).
   * **Users**: create named accounts, choose role (see ROLES_PERMISSIONS.md), optional department restriction,
     trade and hourly rate (used for labour costing). Disabling a user revokes their sessions immediately.
   * **Workflow**: enable/disable status transitions and change the permission each requires. Safety rules (LOTO
     sign-off, test results, emergency closure, PM cancellation approval) are enforced in code regardless.
   * **Import**: parts (CSV/XLSX). Assets are imported from the Assets page. Always *Preview* first; *Import* is
     all-or-nothing and refused while any row has errors; download the error report to fix rows. Templates:
     `docs/templates/` or the *Download template* button.
   * **History from a previous system** (Import tab, administrators): first *Work-order history* (one row per old
     work order; `external_ref` is the old number and must be unique), then *Spare-parts history* (each line points
     to a work order by `wo_external_ref`). Imported work orders are closed, read-only, numbered `MIG-<ref>` and
     marked *Migrated*; rows with `breakdown = yes` become failure downtime events so MTBF/MTTR/availability include
     them. Parts are matched to the spare-parts list by code (leading zeros ignored), otherwise kept as text; their
     cost counts as material cost in the cost KPIs. Stock levels are not changed.
3. Shifts: create shift definitions (via API `POST /api/v1/shifts/definitions`, or seeded), rotation patterns,
   teams; generate rosters from patterns; record leave/absence/overtime.

## Multi-plant
Each plant has its own assets, numbering (`WO-<PLANT>-000001`, configurable via `PUT /api/v1/numbering`), timezone,
currency and calendars. **New, empty plant / mill:** Administration → Plant settings → **New plant / mill** (System
Administrators): code, name, time zone, currency and the starting departments (paper mill, general or none). The plant
starts with departments and the work-order workflow only — no assets, plans or work orders; switch to it with the plant
switcher and load assets, parts, users and plans from the import screens. From the server shell the same is
`python -m app.cli bootstrap --org-code <existing org> --plant-code <new> … --departments paper|general|none`.
A user may hold one role per plant. System administrators see all plants of their organisation.

## Integrations
* **Industrial gateway (OPC UA / MQTT / SCADA historian):** Administration → Integration tokens → create (shown once).
  Configure measurement points' *external tag* (e.g. `ns=2;s=PM1.DR1.VIB`). The gateway POSTs
  `{"readings":[{"tag","value","measured_at"}]}` to `/api/v1/integrations/readings` with `Authorization: Bearer <token>`.
  Duplicate readings (same tag+timestamp) are ignored. The token can only write readings; revoke it any time.
  Keep the gateway on the OT network with outbound HTTPS only. The CMMS never sends commands to control systems.
* **E-mail:** set `CMMS_SMTP_HOST/PORT/USER/PASSWORD/FROM`. Until set, e-mails are recorded with status `disabled`.
* **ERP/Infor:** not integrated. PO numbers can be typed as external references.

## Roles and permissions (controlled by the administrator)
Administration → **Roles & permissions**. Pick a role, tick what it may do, **Save**. Examples:
* only managers approve work orders → untick `wo.approve` on the supervisor roles;
* only planners assign → keep `wo.assign` on Planner, untick it elsewhere;
* nobody but reliability may delete / change PdM plans → `pdm.manage` on Reliability Engineer only;
  PM plans → `pm.manage`; lubrication → `lube.manage`; closing many WOs at once → `wo.bulk_close`.

Rules: only a **System Administrator** changes roles; the System Administrator role always has everything (cannot lock
yourself out). Changes apply to every user with that role in every plant at their next page load, and are kept across
updates. An edited built-in role shows *Built-in (edited)* and can go back with **Reset to default**. **New role**
creates your own role (optionally copying another), e.g. "Area Engineer"; give it to users in Users → Edit. A custom
role can be deleted once nobody has it. Every change is in the audit log (`role.*`).

Administration → **Workflow** decides which permission each work-order step needs (e.g. *Approved* needs `wo.approve`)
and can switch a step off.

## Removing / replacing PM, PdM and lubrication plans
* **Remove selected** (PM → Plans, Condition monitoring → Points, Lubrication → Points; needs `pm.manage`,
  `pdm.manage`, `lube.manage`): items never used are **deleted**; items with history (work orders, readings,
  lubrication done) are **deactivated** — nothing new is generated, waiting dates are cancelled, history stays, and the
  code gets `~OFF` so the same code can be imported again. Open work orders they created stay open (bulk close/cancel
  them if not needed). PM → Plans → *Show removed / inactive* lists them.
* **Import plan → Replace existing plans of the equipment in this file**: first removes (same rule) the current plans of
  every asset in the file — PM plans for a PM file; points and PdM rounds for a PdM file; lubrication points for a
  lubrication file — then imports the file. Preview shows how many will go; if the file has errors nothing changes.
  Equipment not in the file is not touched.

## Roles and trades
* **Role** = what someone may do in the system (Technician, Supervisor, Planner …).
* **Trade** = the work they do: Mechanical, Electrical, Instrumentation, Machinist, Welder, Fitter, Pipe fitter,
  Rigger, Hydraulic, Lubrication, HVAC, Crane operator, Painter, Civil, Operations, General – or type any other trade
  (it then appears in the list). A welder or a machinist is a **Technician** with trade *Welder* / *Machinist*.
* When assigning work, the **Trade** filter next to the technician list shows only that trade. Job plans carry a
  trade too; PM plan codes use its short code (MACH, WELD, FIT, PIPE, RIG …).

## Re-organising departments
Administration → **Departments / Failure codes**:
* **Edit** a department: change code, name, Arabic name, type, or untick *Active* to retire an empty one.
* **Move equipment**: pick production lines or units and a target department. Everything below them moves, with
  all their work orders (open and history); PM plans follow their equipment. **Check** shows the counts, **Move now**
  applies. A unit either becomes a production line of its own (default) or goes under a chosen line of the target
  department. Afterwards give users of the old area the new department in Users.
* Example – one UTIL line "UT – Utilities & Power House" with units WTP and PH: move unit WTP to WWTP (own line),
  move unit PH to UTIL (own line), rename WWTP to "Water & Wastewater Treatment (WTP + WWTP)" and UTIL to
  "PH – Power House", then retire the empty UT line.

## Daily summary e-mail
Administration → **Daily summary** (permission `plant.admin`):
* **Send the summary e-mail** – plant on/off switch (off by default).
* **Send time** – plant-local time (plant timezone). The worker checks every 5 minutes and sends once per send day.
* **Frequency** – Every day, Working days (the plant working calendar), Weekly (one day) or Custom days.
  "Completed / closed" covers the time since the previous send day (yesterday when daily, the last week when weekly).
* **Recipients** – Administration → Users → **Daily summary** switch (permission `user.manage`). Users cannot turn it
  on or off themselves. A user limited to departments gets only those departments; a user with no department
  (planners, managers) gets the whole plant plus each department that has something to report.
* Contents: work orders due today, overdue, completed / closed, open breakdowns (emergency WOs), PM compliance (month
  to date), open critical condition alerts, and the 10 most overdue work orders.
* **Preview** shows what a chosen user would receive today; nothing is sent.
* Delivery uses the normal notifications (in-app + e-mail outbox) and is never repeated for the same user and day.
  A test copy (`CMMS_INSTANCE_LABEL` set) never sends. Links use `CMMS_PUBLIC_URL` (set from `CMMS_DOMAIN` in Docker Compose).

## Audit and monitoring
**Audit log**: logins, lockouts, user/role changes, workflow changes, status transitions, safety sign-offs, inventory
movements, approvals, imports, attachment changes — append-only. **Background jobs**: last runs of the scheduler,
lubrication, e-mail outbox, KPI snapshots. See OPERATIONS.md for alerting.

## Data hygiene
* Sample data lives only in the separate `DEMO` organisation created by `seed-demo`; never run it in production.
* Assets are decommissioned (status), not deleted, to preserve history. Attachments are soft-deleted (retained for audit).

## PlantPulse as a product (website, demo, customer instances)
Since 2026-11 the same server also runs PlantPulse as a product for other plants. The plant's own CMMS
(https://84-8-106-22.sslip.io and its test copy) is unchanged by this. Every command, step by step, is in the
**Arabic operator guide: [PLANTPULSE-GUIDE-AR.md](PLANTPULSE-GUIDE-AR.md)**. Status: [PROJECT_STATUS.md](PROJECT_STATUS.md);
plan: [ROADMAP.md](ROADMAP.md) and the checklist [ACTION_PLAN_2026-11.md](ACTION_PLAN_2026-11.md).

| What | Address | Managed by | Notes |
|---|---|---|---|
| Product website | https://plantpulse-cmms.com | `scripts/site.sh` | EN/AR; "Try the demo" and "Contact us" forms; submissions: `site.sh requests` |
| Public demo | https://demo.plantpulse-cmms.com | `scripts/demo.sh` | separate system, blue **DEMO** label, sample paper mill reloaded every night 03:00 Riyadh |
| Customer instances | https://&lt;name&gt;.plantpulse-cmms.com | `scripts/customer.sh` | one separate PlantPulse per customer: own database, attachments, users, HTTPS |

* **Website forms.** "Try the demo": the visitor receives the demo address and accounts by e-mail at once, in the
  language they used; the owner is notified. "Contact us": the owner receives the request; the visitor gets a
  confirmation with demo access. Mail is sent from `noreply@plantpulse-cmms.com` via Resend (SPF/DKIM/DMARC verified on
  Cloudflare); replies go to `plantpulse.cmms@gmail.com`.
* **Instance labels.** Red **TEST** = the plant's test copy; blue **DEMO** = the public demo. Neither is a real system.
* **New customer.** `customer.sh new <name> <admin-email> <Company> [--trial 30] [--departments general|paper|none] [--lang ar|en]`.
  Nothing is e-mailed to the customer until the owner has checked the system and previewed the welcome e-mail
  (`welcome <name> --preview`, then `welcome <name>`).
* **Trials.** The owner is reminded 7 days and 1 day before the end, on the end day and weekly after. Nothing stops
  automatically: `activate` (paid), `extend <name> <days>` or `stop` (bilingual "paused" page, data kept; `start` resumes).
* **Backups and updates.** Nightly verified backups per customer (02:45 Riyadh), 14 days on the server plus a copy in
  Oracle Object Storage; `restore` takes a safety backup first. `launch-update-all` moves every running customer to a
  new version. Safe update order: test copy → demo → customers → the plant's real system last.
* **Capacity.** About 0.5 GB RAM per small customer ⇒ about 10 customers on the current VM (2 OCPU / 12 GB);
  free upgrade to 4 OCPU / 24 GB ⇒ about 30–40. `customer.sh new` refuses when the server is short of memory.
* Never put passwords or API keys (Resend `re_…`, pre-authenticated URLs) in documents, chats or screenshots.
