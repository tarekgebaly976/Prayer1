-- Wipe all operational data (used by scripts/reset-to-examples.sh), in ONE transaction, for every plant.
-- KEPT: organizations, plants, departments, users and passwords, roles and permissions, memberships, teams and shift
-- set-up, failure codes, workflow transitions, KPI definitions, audit log.
-- TRUNCATE without CASCADE: if any other table still pointed at these rows, PostgreSQL would refuse and nothing
-- would be deleted (never more than this list).
BEGIN;
TRUNCATE TABLE
  asset_bom, asset_status_history, assets, attachments, condition_alerts, condition_readings, downtime_events,
  email_outbox, inventory_transactions, job_plan_materials, job_plan_tasks, job_plans, job_runs, kpi_snapshots,
  kpi_scorecard_values, loto_isolations, lube_routes, lube_tasks, lubricant_alternatives, lubricants,
  lubrication_points, maintenance_budgets, measurement_points, meter_readings, meters, notifications,
  package_dependencies, part_substitutes, part_usages, parts, pm_occurrences, pm_plans, production_records,
  purchase_order_lines, purchase_orders, reservations, shutdown_checks, shutdown_packages, shutdown_progress_logs,
  shutdowns, stock_levels, stockout_events, suppliers, warehouses, wo_assignments, wo_checklist_items, wo_comments,
  wo_labor, wo_services, wo_status_history, work_orders, work_requests, number_sequences, shift_handovers;
COMMIT;
