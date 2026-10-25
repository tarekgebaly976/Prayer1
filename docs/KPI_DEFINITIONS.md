# KPI definitions and formulas

_Generated from `app/core/kpi_definitions.py` (the same text is served by `GET /api/v1/kpis/definitions` and shown in the dashboard drill-down)._

General rules:

* KPIs are computed **only from recorded data**. When the inputs are missing, the KPI is returned as `available: false` with a human-readable `reason`; no value is estimated or defaulted.
* Division by zero never occurs: a zero denominator makes the KPI unavailable.
* Periods are plant-local calendar dates `[start, end]` (inclusive); timestamps are compared in UTC after conversion.
* Scope filters: whole plant, one department, or one asset subtree. Department-restricted users always get their department.
* Every KPI response includes numerator, denominator and drill-down records (capped at 500 rows) for verification.
* Tunable parameters live in `plant.settings.kpi` (e.g. `planned_types`, `emergency_basis`, `include_planned_downtime`, `capacity_roles`, `lube_tolerance_days`) and `plant.settings.repeat_failure_days`.

## 1. PM Compliance (`pm_compliance`)

* **Formula:** PM occurrences completed on time ÷ eligible PM occurrences due in the period × 100
* **Unit:** %
* **Source data:** pm_occurrences (due_date, status, completed_date), pm_plans.tolerance_days
* **Inclusion / exclusion rules:** Eligible = due_date within period and status ≠ cancelled (approved cancellations excluded). On time = completed_date ≤ due_date + plan tolerance. Approved deferrals use the deferred due date. Occurrences whose tolerance window has not yet passed and are still open are excluded until late or completed.
* **Reporting period:** Selected period, by plant-local due date
* **Missing / invalid data:** Unavailable when no eligible occurrences.

## 2. Schedule Compliance (`schedule_compliance`)

* **Formula:** Work orders completed by their planned finish ÷ work orders scheduled to start in the period × 100
* **Unit:** %
* **Source data:** work_orders (planned_start, planned_end, completed_at, status)
* **Inclusion / exclusion rules:** Includes WOs with planned_start in the period, excluding cancelled. Planned finish defaults to end of the planned start day.
* **Reporting period:** Selected period by planned_start
* **Missing / invalid data:** Unavailable when nothing was scheduled.

## 3. Planned Maintenance % (`planned_maintenance_pct`)

* **Formula:** Labor hours on planned work types ÷ total maintenance labor hours × 100
* **Unit:** %
* **Source data:** wo_labor (work_date, hours) joined to work_orders.type
* **Inclusion / exclusion rules:** Planned types (configurable plant.settings.kpi.planned_types): preventive, predictive, inspection, lubrication, shutdown, improvement. Unplanned: corrective, emergency.
* **Reporting period:** Labor work_date within period
* **Missing / invalid data:** Unavailable when no labor recorded.

## 4. Work Order Backlog (`backlog`)

* **Formula:** Σ max(estimated hours − booked hours, 0) over approved/planned/scheduled/in-progress/on-hold WOs; weeks = hours ÷ (technicians × working hours/day × working days/week)
* **Unit:** h (and weeks)
* **Source data:** work_orders, memberships (technician role), plant working calendar
* **Inclusion / exclusion rules:** WOs without an estimate are excluded and counted separately. Triage and awaiting-approval excluded.
* **Reporting period:** Current snapshot (as of now)
* **Missing / invalid data:** Weeks unavailable if technician capacity is zero.

## 5. Overdue Work Orders (`overdue_work_orders`)

* **Formula:** Count of open work orders with due_date < today (plant timezone)
* **Unit:** count
* **Source data:** work_orders (status, due_date)
* **Inclusion / exclusion rules:** Open statuses only; WOs without a due date are never overdue.
* **Reporting period:** Current snapshot
* **Missing / invalid data:** Always available (0 if none).

## 6. Emergency Maintenance % (`emergency_pct`)

* **Formula:** Labor hours on emergency WOs ÷ total labor hours × 100 (or count basis if plant.settings.kpi.emergency_basis = 'count')
* **Unit:** %
* **Source data:** wo_labor, work_orders.type
* **Inclusion / exclusion rules:** Emergency = WO type 'emergency'.
* **Reporting period:** Labor work_date (or WO creation date for count basis)
* **Missing / invalid data:** Unavailable with no labor/WOs.

## 7. MTBF (`mtbf`)

* **Formula:** (Observed hours − merged downtime hours) ÷ number of failure events starting in the period
* **Unit:** h
* **Source data:** downtime_events (is_failure, is_planned, started_at, ended_at)
* **Inclusion / exclusion rules:** Scope treated as one series system (selected asset subtree, department, or plant). Overlapping downtime is merged. Planned downtime excluded unless include_planned_downtime. Observed time stops at 'now' for the current period.
* **Reporting period:** Selected period
* **Missing / invalid data:** Unavailable when there are zero failures (MTBF exceeds observed time).

## 8. MTTR (`mttr`)

* **Formula:** Σ (ended_at − started_at) of failure downtime events ended in the period ÷ number of such events
* **Unit:** h
* **Source data:** downtime_events
* **Inclusion / exclusion rules:** Failure events with an end time; unplanned only.
* **Reporting period:** By ended_at
* **Missing / invalid data:** Unavailable when no completed repairs.

## 9. Equipment Availability (`availability`)

* **Formula:** Operating time ÷ (operating time + downtime) × 100
* **Unit:** %
* **Source data:** downtime_events
* **Inclusion / exclusion rules:** Same system model as MTBF; planned downtime excluded by default.
* **Reporting period:** Selected period
* **Missing / invalid data:** Unavailable before the period starts.

## 10. OEE (`oee`)

* **Formula:** Availability (run ÷ planned hours) × Performance (tons ÷ (run hours × ideal t/h)) × Quality (good ÷ total tons)
* **Unit:** %
* **Source data:** production_records
* **Inclusion / exclusion rules:** Only records with planned hours, run hours, ideal rate and good tons; incomplete records counted as excluded.
* **Reporting period:** record_date within period
* **Missing / invalid data:** Unavailable without complete production data — never estimated.

## 11. Maintenance Cost per Ton (`cost_per_ton`)

* **Formula:** Maintenance cost (labor + materials net of returns + contractor services) ÷ tonnes produced
* **Unit:** currency/t
* **Source data:** wo_labor.cost, inventory_transactions (issue/return linked to WOs), wo_services, production_records
* **Inclusion / exclusion rules:** Transaction-date basis. Same department/asset scope for cost and tonnage.
* **Reporting period:** Selected period
* **Missing / invalid data:** Unavailable if no tonnage recorded.

## 12. Maintenance Cost by Department and Asset (`cost_by_department`)

* **Formula:** Σ maintenance cost grouped by WO department and asset
* **Unit:** currency
* **Source data:** As cost per ton
* **Inclusion / exclusion rules:** Top 15 assets returned; full WO list in drill-down.
* **Reporting period:** Selected period
* **Missing / invalid data:** 0 when no costs.

## 13. Repeat Failure Rate (`repeat_failure_rate`)

* **Formula:** Completed corrective/emergency WOs flagged repeat ÷ all completed corrective/emergency WOs × 100
* **Unit:** %
* **Source data:** work_orders.is_repeat_failure
* **Inclusion / exclusion rules:** Repeat = same asset and same problem code completed within plant.settings.repeat_failure_days (default 30).
* **Reporting period:** completed_at in period
* **Missing / invalid data:** Unavailable when none completed.

## 14. Breakdown Downtime (`breakdown_downtime`)

* **Formula:** Merged hours of unplanned failure downtime within the period (clipped to period)
* **Unit:** h
* **Source data:** downtime_events
* **Inclusion / exclusion rules:** Failure, unplanned events.
* **Reporting period:** Selected period
* **Missing / invalid data:** 0 when none.

## 15. Lubrication Compliance (`lubrication_compliance`)

* **Formula:** Lubrication tasks done within due date + tolerance ÷ tasks due in the period × 100
* **Unit:** %
* **Source data:** lube_tasks
* **Inclusion / exclusion rules:** Skipped and missed tasks count as non-compliant; pending tasks within tolerance excluded.
* **Reporting period:** due_date in period
* **Missing / invalid data:** Unavailable when no tasks due.

## 16. PdM Alerts by Severity (`pdm_alerts`)

* **Formula:** Count of condition alerts raised in the period, by severity; plus currently open by severity
* **Unit:** count
* **Source data:** condition_alerts
* **Inclusion / exclusion rules:** Rule-based limit alerts only.
* **Reporting period:** created_at in period
* **Missing / invalid data:** 0 when none.

## 17. Spare Parts Stockout Rate (`stockout_rate`)

* **Formula:** Stockout events ÷ (successful issues + stockout events) × 100
* **Unit:** %
* **Source data:** stockout_events, inventory_transactions(type=issue)
* **Inclusion / exclusion rules:** A stockout is recorded whenever a reservation or issue cannot be met from free stock.
* **Reporting period:** Selected period
* **Missing / invalid data:** Unavailable with no demand.

## 18. Labor Utilization (`labor_utilization`)

* **Formula:** Labor hours booked to work orders ÷ rostered available hours (work + overtime + callout) × 100
* **Unit:** %
* **Source data:** wo_labor, roster_entries
* **Inclusion / exclusion rules:** Leave and absence excluded from available hours.
* **Reporting period:** Selected period
* **Missing / invalid data:** Unavailable without a roster.

## 19. Maintenance Budget vs. Actual (`budget_vs_actual`)

* **Formula:** Actual maintenance cost ÷ budget for the months in the period × 100 (variance = budget − actual)
* **Unit:** %
* **Source data:** maintenance_budgets, cost basis as cost per ton
* **Inclusion / exclusion rules:** Plant-level budgets have department_id NULL; department scope uses department budgets.
* **Reporting period:** Calendar months overlapping the period
* **Missing / invalid data:** Unavailable when no budget; warning if some months lack budget.

## 20. Shutdown Progress (`shutdown_progress`)

* **Formula:** Σ(package duration × progress %) ÷ Σ package duration, for the most recent shutdown overlapping the period
* **Unit:** %
* **Source data:** shutdown_packages
* **Inclusion / exclusion rules:** Cancelled shutdowns excluded.
* **Reporting period:** Shutdowns overlapping period
* **Missing / invalid data:** Unavailable when no shutdown or no packages.
