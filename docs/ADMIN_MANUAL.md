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
currency and calendars. Add a plant with `bootstrap --org-code <existing org> --plant-code <new>` and add memberships.
A user may hold one role per plant. System administrators see all plants of their organisation.

## Integrations
* **Industrial gateway (OPC UA / MQTT / SCADA historian):** Administration → Integration tokens → create (shown once).
  Configure measurement points' *external tag* (e.g. `ns=2;s=PM1.DR1.VIB`). The gateway POSTs
  `{"readings":[{"tag","value","measured_at"}]}` to `/api/v1/integrations/readings` with `Authorization: Bearer <token>`.
  Duplicate readings (same tag+timestamp) are ignored. The token can only write readings; revoke it any time.
  Keep the gateway on the OT network with outbound HTTPS only. The CMMS never sends commands to control systems.
* **E-mail:** set `CMMS_SMTP_HOST/PORT/USER/PASSWORD/FROM`. Until set, e-mails are recorded with status `disabled`.
* **ERP/Infor:** not integrated. PO numbers can be typed as external references.

## Audit and monitoring
**Audit log**: logins, lockouts, user/role changes, workflow changes, status transitions, safety sign-offs, inventory
movements, approvals, imports, attachment changes — append-only. **Background jobs**: last runs of the scheduler,
lubrication, e-mail outbox, KPI snapshots. See OPERATIONS.md for alerting.

## Data hygiene
* Sample data lives only in the separate `DEMO` organisation created by `seed-demo`; never run it in production.
* Assets are decommissioned (status), not deleted, to preserve history. Attachments are soft-deleted (retained for audit).
