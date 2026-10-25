# Data dictionary

_Generated from the SQLAlchemy models by `scripts/gen_docs.py` — do not edit by hand._

73 tables. Primary keys are UUIDv4 unless noted. All timestamps are `timestamptz` stored in UTC; due dates are plant-local calendar `date`s. Tables marked **append-only** reject UPDATE/DELETE via trigger and the runtime role has no UPDATE/DELETE privilege on them.

## Tenancy & identity

### `organizations`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(32) | no |  |
| `name` | varchar(200) | no |  |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (code)

### `plants`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `organization_id` | uuid | no | FK → organizations.id (on delete RESTRICT) |
| `code` | varchar(32) | no |  |
| `name` | varchar(200) | no |  |
| `timezone` | varchar(64) | no |  |
| `currency` | varchar(3) | no |  |
| `default_locale` | varchar(8) | no |  |
| `allow_negative_stock` | boolean | no |  |
| `working_days` | jsonb | no |  |
| `working_hours_per_day` | double | no |  |
| `settings` | jsonb | no |  |
| `is_active` | boolean | no |  |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (organization_id, code)

Indexes: ix_plants_organization_id (organization_id)

### `plant_holidays`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `date` | date | no |  |
| `name` | varchar(120) | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, date)

Indexes: ix_plant_holidays_plant_id (plant_id)

### `departments`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(32) | no |  |
| `name` | varchar(200) | no |  |
| `name_ar` | varchar(200) | yes |  |
| `type` | enum(PM, SP, FH, WWTP, EAI, UTIL) | no |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, code)

Indexes: ix_departments_plant_id (plant_id)

### `number_sequences`

Configurable per-plant numbering, e.g. WO-PM1-000123. Allocated under row lock.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `key` | varchar(32) | no |  |
| `prefix` | varchar(32) | no |  |
| `padding` | integer | no |  |
| `next_value` | integer | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, key)

Indexes: ix_number_sequences_plant_id (plant_id)

### `integration_tokens`

Credentials for the read-only industrial data gateway (stored hashed, write-only for readings).

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `name` | varchar(120) | no |  |
| `token_hash` | varchar(64) | no |  |
| `scopes` | jsonb | no |  |
| `revoked_at` | datetime | yes |  |
| `last_used_at` | datetime | yes |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `notes` | text | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (token_hash)

Indexes: ix_integration_tokens_plant_id (plant_id)

### `users`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `organization_id` | uuid | no | FK → organizations.id (on delete RESTRICT) |
| `email` | varchar(254) | no |  |
| `full_name` | varchar(200) | no |  |
| `employee_no` | varchar(40) | yes |  |
| `password_hash` | varchar(255) | no |  |
| `is_active` | boolean | no |  |
| `is_system_admin` | boolean | no |  |
| `locale` | varchar(8) | no |  |
| `trade` | varchar(40) | yes |  |
| `hourly_rate` | double | yes |  |
| `failed_login_count` | integer | no |  |
| `locked_until` | datetime | yes |  |
| `password_changed_at` | datetime | yes |  |
| `last_login_at` | datetime | yes |  |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (email)

Indexes: ix_users_organization_id (organization_id)

### `roles`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(40) | no |  |
| `name` | varchar(120) | no |  |
| `description` | varchar(400) | yes |  |

Unique: (code)

### `permissions`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `code` | varchar(60) | no | PK |
| `description` | varchar(300) | no |  |

### `role_permissions`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `role_id` | uuid | no | PK; FK → roles.id (on delete CASCADE) |
| `permission_code` | varchar(60) | no | PK; FK → permissions.code (on delete CASCADE) |

### `memberships`

Grants a user a role within one plant, optionally restricted to one department.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `user_id` | uuid | no | FK → users.id (on delete CASCADE) |
| `plant_id` | uuid | no | FK → plants.id (on delete CASCADE) |
| `role_id` | uuid | no | FK → roles.id (on delete RESTRICT) |
| `department_id` | uuid | yes | FK → departments.id (on delete SET NULL) |
| `is_active` | boolean | no |  |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (user_id, plant_id)

Indexes: ix_memberships_plant_id (plant_id); ix_memberships_role_id (role_id); ix_memberships_user_id (user_id); ix_memberships_department_id (department_id)

### `user_sessions`

Server-side session: the browser only holds an opaque HttpOnly cookie; revocable at any time.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `user_id` | uuid | no | FK → users.id (on delete CASCADE) |
| `token_hash` | varchar(64) | no |  |
| `csrf_token` | varchar(64) | no |  |
| `created_at` | datetime | no |  |
| `expires_at` | datetime | no |  |
| `last_seen_at` | datetime | no |  |
| `revoked_at` | datetime | yes |  |
| `ip` | varchar(64) | yes |  |
| `user_agent` | varchar(300) | yes |  |

Unique: (token_hash)

Indexes: ix_user_sessions_user_id (user_id)

### `login_attempts`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `email` | varchar(254) | no |  |
| `ip` | varchar(64) | yes |  |
| `success` | boolean | no |  |
| `at` | datetime | no |  |

Indexes: ix_login_attempts_at (at); ix_login_attempts_email (email); ix_login_attempts_ip (ip)

### `user_skills`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `user_id` | uuid | no | FK → users.id (on delete CASCADE) |
| `skill` | varchar(60) | no |  |
| `level` | integer | no |  |
| `certified_until` | datetime | yes |  |

Unique: (user_id, skill)

Indexes: ix_user_skills_user_id (user_id)

## Assets

### `assets`

Asset hierarchy node: Production Line -> Unit -> Assembly -> Sub-Assembly -> Component. Plant and Department are the two levels above (separate tables). `path` is a materialised path of ancestor ids ("/<id>/<id>/") for efficient subtree queries on 100k+ rows.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `department_id` | uuid | no | FK → departments.id (on delete RESTRICT) |
| `parent_id` | uuid | yes | FK → assets.id (on delete RESTRICT) |
| `level` | enum(production_line, unit, assembly, sub_assembly, component) | no |  |
| `path` | varchar(2000) | no |  |
| `code` | varchar(60) | no |  |
| `name` | varchar(200) | no |  |
| `name_ar` | varchar(200) | yes |  |
| `description` | text | yes |  |
| `oem` | varchar(120) | yes |  |
| `model` | varchar(120) | yes |  |
| `serial_number` | varchar(120) | yes |  |
| `install_date` | date | yes |  |
| `criticality` | enum(A, B, C) | no |  |
| `status` | enum(in_service, standby, under_maintenance, out_of_service, decommissioned) | no |  |
| `location` | varchar(200) | yes |  |
| `specifications` | jsonb | no |  |
| `operating_limits` | jsonb | no |  |
| `operating_hours` | numeric(14, 2) | no |  |
| `qr_token` | varchar(32) | no |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Unique: (qr_token); (plant_id, code)

Indexes: ix_assets_department_id (department_id); ix_assets_plant_parent (plant_id, parent_id); ix_assets_plant_id (plant_id); ix_assets_path (path)

### `asset_status_history`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `asset_id` | uuid | no | FK → assets.id (on delete CASCADE) |
| `from_status` | varchar(32) | yes |  |
| `to_status` | varchar(32) | no |  |
| `changed_at` | datetime | no |  |
| `changed_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `note` | text | yes |  |

Indexes: ix_asset_status_history_asset_id (asset_id)

### `asset_bom`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `asset_id` | uuid | no | FK → assets.id (on delete CASCADE) |
| `part_id` | uuid | no | FK → parts.id (on delete RESTRICT) |
| `quantity` | numeric(14, 3) | no |  |
| `position` | varchar(120) | yes |  |
| `notes` | text | yes |  |

Unique: (asset_id, part_id)

Indexes: ix_asset_bom_part_id (part_id); ix_asset_bom_asset_id (asset_id)

### `meters`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `asset_id` | uuid | no | FK → assets.id (on delete CASCADE) |
| `name` | varchar(80) | no |  |
| `unit` | varchar(20) | no |  |
| `is_operating_hours` | boolean | no |  |
| `current_value` | numeric(16, 2) | no |  |
| `last_read_at` | datetime | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (asset_id, name)

Indexes: ix_meters_plant_id (plant_id); ix_meters_asset_id (asset_id)

### `meter_readings`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `meter_id` | uuid | no | FK → meters.id (on delete CASCADE) |
| `value` | numeric(16, 2) | no |  |
| `read_at` | datetime | no |  |
| `recorded_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `source` | varchar(20) | no |  |

Indexes: ix_meter_readings_meter_time (meter_id, read_at)

### `failure_codes`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `kind` | enum(problem, cause, remedy) | no |  |
| `code` | varchar(32) | no |  |
| `description` | varchar(200) | no |  |
| `description_ar` | varchar(200) | yes |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, kind, code)

Indexes: ix_failure_codes_plant_id (plant_id)

### `downtime_events`

Equipment downtime. `is_failure` events count toward MTBF; breakdown hours toward KPIs.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `asset_id` | uuid | no | FK → assets.id (on delete RESTRICT) |
| `work_order_id` | uuid | yes | FK → work_orders.id (on delete SET NULL) |
| `started_at` | datetime | no |  |
| `ended_at` | datetime | yes |  |
| `is_failure` | boolean | no |  |
| `is_planned` | boolean | no |  |
| `production_loss_tons` | numeric(12, 2) | yes |  |
| `reason` | text | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Indexes: ix_downtime_asset_time (asset_id, started_at); ix_downtime_events_work_order_id (work_order_id); ix_downtime_events_plant_id (plant_id)

## Work management

### `work_requests`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `number` | varchar(40) | no |  |
| `asset_id` | uuid | no | FK → assets.id (on delete RESTRICT) |
| `title` | varchar(200) | no |  |
| `description` | text | yes |  |
| `symptoms` | text | yes |  |
| `suggested_priority` | enum(P1, P2, P3, P4) | no |  |
| `is_breakdown` | boolean | no |  |
| `status` | enum(submitted, accepted, rejected) | no |  |
| `triaged_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `triaged_at` | datetime | yes |  |
| `triage_note` | text | yes |  |
| `work_order_id` | uuid | yes | FK → work_orders.id (on delete RESTRICT) |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Unique: (plant_id, number)

Indexes: ix_work_requests_asset_id (asset_id); ix_work_requests_work_order_id (work_order_id); ix_work_requests_plant_id (plant_id)

### `work_orders`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `number` | varchar(40) | no |  |
| `type` | enum(preventive, predictive, corrective, emergency, inspection, improvement, shutdown, lubrication) | no |  |
| `status` | enum(triage, awaiting_approval, approved, planned, scheduled, in_progress, on_hold, awaiting_review, completed, closed, cancelled) | no |  |
| `priority` | enum(P1, P2, P3, P4) | no |  |
| `asset_id` | uuid | no | FK → assets.id (on delete RESTRICT) |
| `department_id` | uuid | no | FK → departments.id (on delete RESTRICT) |
| `title` | varchar(200) | no |  |
| `description` | text | yes |  |
| `symptoms` | text | yes |  |
| `problem_code_id` | uuid | yes | FK → failure_codes.id (on delete RESTRICT) |
| `cause_code_id` | uuid | yes | FK → failure_codes.id (on delete RESTRICT) |
| `remedy_code_id` | uuid | yes | FK → failure_codes.id (on delete RESTRICT) |
| `supervisor_id` | uuid | yes | FK → users.id (on delete RESTRICT) |
| `due_date` | date | yes |  |
| `planned_start` | datetime | yes |  |
| `planned_end` | datetime | yes |  |
| `actual_start` | datetime | yes |  |
| `actual_end` | datetime | yes |  |
| `completed_at` | datetime | yes |  |
| `closed_at` | datetime | yes |  |
| `estimated_hours` | numeric(10, 2) | yes |  |
| `estimated_cost` | numeric(14, 2) | yes |  |
| `actual_labor_hours` | numeric(10, 2) | no |  |
| `actual_labor_cost` | numeric(14, 2) | no |  |
| `actual_material_cost` | numeric(14, 2) | no |  |
| `actual_service_cost` | numeric(14, 2) | no |  |
| `currency` | varchar(3) | no |  |
| `downtime_hours` | numeric(10, 2) | yes |  |
| `production_impact` | text | yes |  |
| `production_loss_tons` | numeric(12, 2) | yes |  |
| `requires_loto` | boolean | no |  |
| `requires_permit` | boolean | no |  |
| `permit_reference` | varchar(80) | yes |  |
| `safety_requirements` | text | yes |  |
| `safety_signed_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `safety_signed_at` | datetime | yes |  |
| `requires_testing` | boolean | no |  |
| `test_result` | text | yes |  |
| `test_passed` | boolean | yes |  |
| `tested_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `tested_at` | datetime | yes |  |
| `findings` | text | yes |  |
| `recommendations` | text | yes |  |
| `root_cause` | text | yes |  |
| `corrective_action` | text | yes |  |
| `is_repeat_failure` | boolean | no |  |
| `pm_occurrence_id` | uuid | yes | FK → pm_occurrences.id (on delete RESTRICT) |
| `condition_alert_id` | uuid | yes | FK → condition_alerts.id (on delete RESTRICT) |
| `shutdown_package_id` | uuid | yes | FK → shutdown_packages.id (on delete RESTRICT) |
| `work_request_id` | uuid | yes |  |
| `version` | integer | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Unique: (pm_occurrence_id); (plant_id, number)

Indexes: ix_work_orders_plant_id (plant_id); ix_wo_plant_created (plant_id, created_at); ix_work_orders_department_id (department_id); ix_work_orders_condition_alert_id (condition_alert_id); ix_wo_plant_status (plant_id, status); ix_work_orders_supervisor_id (supervisor_id); ix_work_orders_shutdown_package_id (shutdown_package_id); ix_wo_plant_asset (plant_id, asset_id); ix_work_orders_due_date (due_date)

### `wo_assignments`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `work_order_id` | uuid | no | FK → work_orders.id (on delete CASCADE) |
| `user_id` | uuid | no | FK → users.id (on delete RESTRICT) |
| `is_lead` | boolean | no |  |
| `assigned_at` | datetime | no |  |
| `assigned_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |

Unique: (work_order_id, user_id)

Indexes: ix_wo_assignments_user_id (user_id); ix_wo_assignments_work_order_id (work_order_id)

### `wo_status_history` — append-only

Append-only approval / status trail (UPDATE/DELETE blocked by trigger).

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `work_order_id` | uuid | no | FK → work_orders.id (on delete CASCADE) |
| `from_status` | varchar(32) | yes |  |
| `to_status` | varchar(32) | no |  |
| `changed_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `changed_at` | datetime | no |  |
| `comment` | text | yes |  |

Indexes: ix_wo_status_history_work_order_id (work_order_id)

### `wo_status_transitions`

Configurable workflow: allowed status transitions and the permission each one requires.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `from_status` | varchar(32) | no |  |
| `to_status` | varchar(32) | no |  |
| `permission` | varchar(60) | no |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, from_status, to_status)

Indexes: ix_wo_status_transitions_plant_id (plant_id)

### `wo_labor`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `work_order_id` | uuid | no | FK → work_orders.id (on delete CASCADE) |
| `user_id` | uuid | no | FK → users.id (on delete RESTRICT) |
| `work_date` | date | no |  |
| `hours` | numeric(6, 2) | no |  |
| `is_overtime` | boolean | no |  |
| `rate` | numeric(10, 2) | no |  |
| `cost` | numeric(14, 2) | no |  |
| `notes` | text | yes |  |
| `created_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Indexes: ix_wo_labor_work_order_id (work_order_id); ix_wo_labor_user_id (user_id)

### `wo_services`

Contractor / external services.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `work_order_id` | uuid | no | FK → work_orders.id (on delete CASCADE) |
| `supplier_id` | uuid | yes | FK → suppliers.id (on delete RESTRICT) |
| `description` | varchar(300) | no |  |
| `po_reference` | varchar(60) | yes |  |
| `cost` | numeric(14, 2) | no |  |
| `created_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Indexes: ix_wo_services_work_order_id (work_order_id); ix_wo_services_supplier_id (supplier_id)

### `wo_checklist_items`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `work_order_id` | uuid | no | FK → work_orders.id (on delete CASCADE) |
| `seq` | integer | no |  |
| `description` | varchar(400) | no |  |
| `kind` | enum(check, reading) | no |  |
| `is_required` | boolean | no |  |
| `unit` | varchar(20) | yes |  |
| `min_value` | numeric(14, 3) | yes |  |
| `max_value` | numeric(14, 3) | yes |  |
| `is_done` | boolean | no |  |
| `is_ok` | boolean | yes |  |
| `reading_value` | numeric(14, 3) | yes |  |
| `remark` | text | yes |  |
| `done_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `done_at` | datetime | yes |  |

Unique: (work_order_id, seq)

Indexes: ix_wo_checklist_items_work_order_id (work_order_id)

### `wo_comments`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `work_order_id` | uuid | no | FK → work_orders.id (on delete CASCADE) |
| `user_id` | uuid | no | FK → users.id (on delete RESTRICT) |
| `body` | text | no |  |
| `created_at` | datetime | no |  |
| `data` | jsonb | no |  |

Indexes: ix_wo_comments_work_order_id (work_order_id); ix_wo_comments_user_id (user_id)

## Preventive maintenance

### `job_plans`

Reusable PM task template / job plan.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(40) | no |  |
| `name` | varchar(200) | no |  |
| `description` | text | yes |  |
| `trade` | varchar(40) | yes |  |
| `estimated_hours` | numeric(8, 2) | no |  |
| `crew_size` | integer | no |  |
| `tools` | text | yes |  |
| `safety_precautions` | text | yes |  |
| `requires_loto` | boolean | no |  |
| `requires_permit` | boolean | no |  |
| `requires_testing` | boolean | no |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Unique: (plant_id, code)

Indexes: ix_job_plans_plant_id (plant_id)

### `job_plan_tasks`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `job_plan_id` | uuid | no | FK → job_plans.id (on delete CASCADE) |
| `seq` | integer | no |  |
| `description` | varchar(400) | no |  |
| `kind` | enum(check, reading) | no |  |
| `unit` | varchar(20) | yes |  |
| `min_value` | numeric(14, 3) | yes |  |
| `max_value` | numeric(14, 3) | yes |  |
| `is_required` | boolean | no |  |

Unique: (job_plan_id, seq)

Indexes: ix_job_plan_tasks_job_plan_id (job_plan_id)

### `job_plan_materials`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `job_plan_id` | uuid | no | FK → job_plans.id (on delete CASCADE) |
| `part_id` | uuid | no | FK → parts.id (on delete RESTRICT) |
| `quantity` | numeric(14, 3) | no |  |

Unique: (job_plan_id, part_id)

Indexes: ix_job_plan_materials_job_plan_id (job_plan_id); ix_job_plan_materials_part_id (part_id)

### `pm_plans`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(40) | no |  |
| `name` | varchar(200) | no |  |
| `asset_id` | uuid | no | FK → assets.id (on delete RESTRICT) |
| `job_plan_id` | uuid | no | FK → job_plans.id (on delete RESTRICT) |
| `trigger` | enum(calendar, meter, condition) | no |  |
| `wo_type` | enum(preventive, predictive, corrective, emergency, inspection, improvement, shutdown, lubrication) | no |  |
| `priority` | enum(P1, P2, P3, P4) | no |  |
| `frequency_unit` | enum(day, week, month, year) | yes |  |
| `frequency_interval` | integer | yes |  |
| `schedule_basis` | enum(fixed, floating) | no |  |
| `start_date` | date | yes |  |
| `meter_id` | uuid | yes | FK → meters.id (on delete RESTRICT) |
| `meter_interval` | numeric(14, 2) | yes |  |
| `last_meter_value` | numeric(16, 2) | yes |  |
| `horizon_days` | integer | no |  |
| `lead_days` | integer | no |  |
| `tolerance_days` | integer | no |  |
| `last_completed_date` | date | yes |  |
| `next_due_date` | date | yes |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Unique: (plant_id, code)

Indexes: ix_pm_plans_job_plan_id (job_plan_id); ix_pm_plans_plant_id (plant_id); ix_pm_plans_meter_id (meter_id); ix_pm_plans_asset_id (asset_id)

### `pm_occurrences`

One scheduled instance of a PM plan. (pm_plan_id, occurrence_key) is unique, so re-running the scheduler can never create the same occurrence twice; work_orders.pm_occurrence_id is unique, so an occurrence yields at most one WO.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `pm_plan_id` | uuid | no | FK → pm_plans.id (on delete CASCADE) |
| `occurrence_key` | varchar(64) | no |  |
| `due_date` | date | no |  |
| `original_due_date` | date | no |  |
| `due_meter` | numeric(16, 2) | yes |  |
| `status` | enum(scheduled, generated, completed, deferral_requested, deferred, cancellation_requested, cancelled) | no |  |
| `work_order_id` | uuid | yes |  |
| `completed_at` | datetime | yes |  |
| `completed_date` | date | yes |  |
| `requested_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `request_reason` | text | yes |  |
| `requested_new_date` | date | yes |  |
| `decided_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `decided_at` | datetime | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (pm_plan_id, occurrence_key)

Indexes: ix_pm_occurrences_plant_id (plant_id); ix_pm_occ_plant_due (plant_id, due_date); ix_pm_occ_status (status)

## Lubrication

### `lubricants`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(40) | no |  |
| `manufacturer` | varchar(120) | no |  |
| `product` | varchar(160) | no |  |
| `kind` | varchar(16) | no |  |
| `viscosity_grade` | varchar(40) | yes |  |
| `specification` | varchar(200) | yes |  |
| `part_id` | uuid | yes | FK → parts.id (on delete RESTRICT) |
| `is_approved` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, code)

Indexes: ix_lubricants_plant_id (plant_id); ix_lubricants_part_id (part_id)

### `lubricant_alternatives`

An alternative is usable only once compatibility has been verified and technically approved.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `lubricant_id` | uuid | no | FK → lubricants.id (on delete CASCADE) |
| `alternative_id` | uuid | no | FK → lubricants.id (on delete CASCADE) |
| `compatibility_note` | text | no |  |
| `approved_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `approved_at` | datetime | yes |  |

Unique: (lubricant_id, alternative_id)

Indexes: ix_lubricant_alternatives_lubricant_id (lubricant_id); ix_lubricant_alternatives_alternative_id (alternative_id)

### `lube_routes`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(40) | no |  |
| `name` | varchar(200) | no |  |
| `department_id` | uuid | no | FK → departments.id (on delete RESTRICT) |
| `lead_days` | integer | no |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, code)

Indexes: ix_lube_routes_department_id (department_id); ix_lube_routes_plant_id (plant_id)

### `lubrication_points`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(40) | no |  |
| `asset_id` | uuid | no | FK → assets.id (on delete RESTRICT) |
| `component` | varchar(120) | yes |  |
| `location` | varchar(200) | yes |  |
| `lubricant_id` | uuid | no | FK → lubricants.id (on delete RESTRICT) |
| `quantity` | numeric(10, 3) | no |  |
| `unit` | varchar(10) | no |  |
| `method` | varchar(120) | yes |  |
| `tools` | varchar(200) | yes |  |
| `frequency_days` | integer | yes |  |
| `hours_interval` | numeric(10, 1) | yes |  |
| `oem_recommendation` | text | yes |  |
| `route_id` | uuid | yes | FK → lube_routes.id (on delete RESTRICT) |
| `route_seq` | integer | no |  |
| `responsible_user_id` | uuid | yes | FK → users.id (on delete RESTRICT) |
| `last_done_date` | date | yes |  |
| `last_done_hours` | numeric(14, 2) | yes |  |
| `next_due_date` | date | yes |  |
| `qr_token` | varchar(32) | no |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, code); (qr_token)

Indexes: ix_lubrication_points_lubricant_id (lubricant_id); ix_lubrication_points_next_due_date (next_due_date); ix_lubrication_points_route_id (route_id); ix_lubrication_points_plant_id (plant_id); ix_lubrication_points_asset_id (asset_id); ix_lubrication_points_responsible_user_id (responsible_user_id)

### `lube_tasks`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `point_id` | uuid | no | FK → lubrication_points.id (on delete CASCADE) |
| `route_id` | uuid | yes | FK → lube_routes.id (on delete RESTRICT) |
| `work_order_id` | uuid | yes | FK → work_orders.id (on delete SET NULL) |
| `due_date` | date | no |  |
| `status` | enum(pending, done, skipped, missed) | no |  |
| `done_at` | datetime | yes |  |
| `done_date` | date | yes |  |
| `done_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `quantity_actual` | numeric(10, 3) | yes |  |
| `lubricant_used_id` | uuid | yes | FK → lubricants.id (on delete RESTRICT) |
| `condition_note` | text | yes |  |
| `missed_notified` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (point_id, due_date)

Indexes: ix_lube_tasks_route_id (route_id); ix_lube_tasks_plant_id (plant_id); ix_lube_tasks_work_order_id (work_order_id); ix_lube_tasks_point_id (point_id); ix_lube_tasks_lubricant_used_id (lubricant_used_id)

## Shifts & manpower

### `shift_definitions`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(8) | no |  |
| `name` | varchar(60) | no |  |
| `kind` | enum(day, evening, night, general) | no |  |
| `start_time` | time | no |  |
| `end_time` | time | no |  |
| `paid_hours` | numeric(4, 2) | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, code)

Indexes: ix_shift_definitions_plant_id (plant_id)

### `shift_patterns`

Rotation cycle: list of shift codes (or "OFF") per day, e.g. ["D","D","E","E","N","N","OFF","OFF"].

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(20) | no |  |
| `name` | varchar(120) | no |  |
| `cycle` | jsonb | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, code)

Indexes: ix_shift_patterns_plant_id (plant_id)

### `teams`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(20) | no |  |
| `name` | varchar(120) | no |  |
| `department_id` | uuid | yes | FK → departments.id (on delete RESTRICT) |
| `supervisor_id` | uuid | yes | FK → users.id (on delete RESTRICT) |
| `pattern_id` | uuid | yes | FK → shift_patterns.id (on delete RESTRICT) |
| `pattern_anchor_date` | date | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, code)

Indexes: ix_teams_supervisor_id (supervisor_id); ix_teams_pattern_id (pattern_id); ix_teams_department_id (department_id); ix_teams_plant_id (plant_id)

### `team_members`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `team_id` | uuid | no | FK → teams.id (on delete CASCADE) |
| `user_id` | uuid | no | FK → users.id (on delete CASCADE) |

Unique: (team_id, user_id)

Indexes: ix_team_members_team_id (team_id); ix_team_members_user_id (user_id)

### `roster_entries`

One person on one day. A person can have at most one entry per day (prevents double-rostering); overtime/callout on a day already worked are recorded as extra hours on that entry.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `user_id` | uuid | no | FK → users.id (on delete CASCADE) |
| `work_date` | date | no |  |
| `shift_id` | uuid | yes | FK → shift_definitions.id (on delete RESTRICT) |
| `kind` | enum(work, overtime, callout, leave, absence) | no |  |
| `hours` | numeric(5, 2) | no |  |
| `overtime_hours` | numeric(5, 2) | no |  |
| `callout_hours` | numeric(5, 2) | no |  |
| `team_id` | uuid | yes | FK → teams.id (on delete RESTRICT) |
| `note` | text | yes |  |
| `source` | varchar(16) | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (user_id, work_date)

Indexes: ix_roster_entries_shift_id (shift_id); ix_roster_entries_team_id (team_id); ix_roster_entries_plant_id (plant_id); ix_roster_plant_date (plant_id, work_date)

### `shift_handovers`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `department_id` | uuid | no | FK → departments.id (on delete RESTRICT) |
| `shift_date` | date | no |  |
| `shift_id` | uuid | no | FK → shift_definitions.id (on delete RESTRICT) |
| `outgoing_user_id` | uuid | no | FK → users.id (on delete RESTRICT) |
| `incoming_user_id` | uuid | yes | FK → users.id (on delete RESTRICT) |
| `summary` | text | no |  |
| `outstanding_breakdowns` | text | yes |  |
| `pending_work` | text | yes |  |
| `safety_concerns` | text | yes |  |
| `equipment_abnormalities` | text | yes |  |
| `pending_permits` | text | yes |  |
| `critical_risks` | text | yes |  |
| `open_work_order_ids` | jsonb | no |  |
| `status` | enum(draft, submitted, confirmed) | no |  |
| `submitted_at` | datetime | yes |  |
| `confirmed_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `confirmed_at` | datetime | yes |  |
| `supervisor_comment` | text | yes |  |
| `is_locked` | boolean | no |  |
| `revision` | integer | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, department_id, shift_date, shift_id)

Indexes: ix_shift_handovers_department_id (department_id); ix_shift_handovers_outgoing_user_id (outgoing_user_id); ix_shift_handovers_incoming_user_id (incoming_user_id); ix_shift_handovers_plant_id (plant_id); ix_shift_handovers_shift_id (shift_id)

## Inventory & purchasing

### `suppliers`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(40) | no |  |
| `name` | varchar(200) | no |  |
| `contact_name` | varchar(120) | yes |  |
| `email` | varchar(254) | yes |  |
| `phone` | varchar(40) | yes |  |
| `is_contractor` | boolean | no |  |
| `default_lead_time_days` | integer | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, code)

Indexes: ix_suppliers_plant_id (plant_id)

### `warehouses`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(32) | no |  |
| `name` | varchar(120) | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, code)

Indexes: ix_warehouses_plant_id (plant_id)

### `parts`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(60) | no |  |
| `description` | varchar(300) | no |  |
| `description_ar` | varchar(300) | yes |  |
| `oem_part_number` | varchar(120) | yes |  |
| `manufacturer` | varchar(120) | yes |  |
| `category` | varchar(60) | yes |  |
| `uom` | varchar(16) | no |  |
| `criticality` | enum(A, B, C) | no |  |
| `is_critical_spare` | boolean | no |  |
| `min_qty` | numeric(14, 3) | no |  |
| `max_qty` | numeric(14, 3) | no |  |
| `safety_stock` | numeric(14, 3) | no |  |
| `reorder_point` | numeric(14, 3) | no |  |
| `lead_time_days` | integer | yes |  |
| `preferred_supplier_id` | uuid | yes | FK → suppliers.id (on delete RESTRICT) |
| `unit_price` | numeric(14, 4) | no |  |
| `average_cost` | numeric(14, 4) | no |  |
| `currency` | varchar(3) | no |  |
| `is_obsolete` | boolean | no |  |
| `last_issue_at` | datetime | yes |  |
| `last_receipt_at` | datetime | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Unique: (plant_id, code)

Indexes: ix_parts_oem_pn (plant_id, oem_part_number); ix_parts_preferred_supplier_id (preferred_supplier_id); ix_parts_plant_id (plant_id)

### `part_substitutes`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `part_id` | uuid | no | FK → parts.id (on delete CASCADE) |
| `substitute_id` | uuid | no | FK → parts.id (on delete CASCADE) |
| `approved_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `notes` | text | yes |  |

Unique: (part_id, substitute_id)

Indexes: ix_part_substitutes_substitute_id (substitute_id); ix_part_substitutes_part_id (part_id)

### `stock_levels`

Current balance per part per warehouse/bin. Changed only by the inventory service, under row lock, and always together with an InventoryTransaction row.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `part_id` | uuid | no | FK → parts.id (on delete RESTRICT) |
| `warehouse_id` | uuid | no | FK → warehouses.id (on delete RESTRICT) |
| `bin` | varchar(40) | yes |  |
| `qty_on_hand` | numeric(14, 3) | no |  |
| `qty_reserved` | numeric(14, 3) | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (part_id, warehouse_id)

Indexes: ix_stock_levels_warehouse_id (warehouse_id); ix_stock_levels_plant_id (plant_id); ix_stock_levels_part_id (part_id)

### `inventory_transactions` — append-only

Append-only stock ledger (UPDATE/DELETE blocked by trigger).

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `part_id` | uuid | no | FK → parts.id (on delete RESTRICT) |
| `warehouse_id` | uuid | no | FK → warehouses.id (on delete RESTRICT) |
| `type` | enum(receipt, issue, return, adjustment, transfer_out, transfer_in) | no |  |
| `quantity` | numeric(14, 3) | no |  |
| `unit_cost` | numeric(14, 4) | no |  |
| `total_cost` | numeric(16, 2) | no |  |
| `balance_after` | numeric(14, 3) | no |  |
| `work_order_id` | uuid | yes | FK → work_orders.id (on delete RESTRICT) |
| `po_line_id` | uuid | yes | FK → purchase_order_lines.id (on delete RESTRICT) |
| `reference` | varchar(120) | yes |  |
| `reason` | text | yes |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `created_at` | datetime | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Indexes: ix_inv_txn_part_time (part_id, created_at); ix_inventory_transactions_work_order_id (work_order_id); ix_inventory_transactions_warehouse_id (warehouse_id); ix_inventory_transactions_po_line_id (po_line_id); ix_inventory_transactions_plant_id (plant_id)

### `reservations`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `work_order_id` | uuid | no | FK → work_orders.id (on delete CASCADE) |
| `part_id` | uuid | no | FK → parts.id (on delete RESTRICT) |
| `warehouse_id` | uuid | no | FK → warehouses.id (on delete RESTRICT) |
| `quantity` | numeric(14, 3) | no |  |
| `qty_issued` | numeric(14, 3) | no |  |
| `status` | enum(active, fulfilled, cancelled) | no |  |
| `needed_by` | date | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Indexes: ix_reservations_plant_id (plant_id); ix_reservations_work_order_id (work_order_id); ix_reservations_part_id (part_id); ix_reservations_warehouse_id (warehouse_id)

### `purchase_orders`

Local purchase requisition / PO reference. Not an ERP integration.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `number` | varchar(40) | no |  |
| `external_reference` | varchar(80) | yes |  |
| `supplier_id` | uuid | yes | FK → suppliers.id (on delete RESTRICT) |
| `status` | enum(draft, requested, ordered, partial, received, cancelled) | no |  |
| `expected_date` | date | yes |  |
| `currency` | varchar(3) | no |  |
| `notes` | text | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete SET NULL) |

Unique: (plant_id, number)

Indexes: ix_purchase_orders_supplier_id (supplier_id); ix_purchase_orders_plant_id (plant_id)

### `purchase_order_lines`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `purchase_order_id` | uuid | no | FK → purchase_orders.id (on delete CASCADE) |
| `part_id` | uuid | no | FK → parts.id (on delete RESTRICT) |
| `quantity` | numeric(14, 3) | no |  |
| `qty_received` | numeric(14, 3) | no |  |
| `unit_price` | numeric(14, 4) | no |  |
| `work_order_id` | uuid | yes | FK → work_orders.id (on delete RESTRICT) |

Indexes: ix_purchase_order_lines_work_order_id (work_order_id); ix_purchase_order_lines_purchase_order_id (purchase_order_id); ix_purchase_order_lines_part_id (part_id)

### `stockout_events`

Recorded when an issue/reservation request could not be met from stock (KPI: stockout rate).

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `part_id` | uuid | no | FK → parts.id (on delete RESTRICT) |
| `work_order_id` | uuid | yes | FK → work_orders.id (on delete RESTRICT) |
| `requested_qty` | numeric(14, 3) | no |  |
| `available_qty` | numeric(14, 3) | no |  |
| `created_at` | datetime | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Indexes: ix_stockout_events_work_order_id (work_order_id); ix_stockout_events_plant_id (plant_id); ix_stockout_events_part_id (part_id)

## Condition monitoring

### `measurement_points`

Rule-based condition monitoring point with transparent limits (no ML claims).

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(60) | no |  |
| `name` | varchar(200) | no |  |
| `asset_id` | uuid | no | FK → assets.id (on delete RESTRICT) |
| `technique` | enum(vibration, temperature, motor_current, power, oil_analysis, thermography, ultrasound, alignment, balancing, pressure, flow, other) | no |  |
| `unit` | varchar(20) | no |  |
| `baseline` | numeric(14, 4) | yes |  |
| `warning_low` | numeric(14, 4) | yes |  |
| `warning_high` | numeric(14, 4) | yes |  |
| `alarm_low` | numeric(14, 4) | yes |  |
| `alarm_high` | numeric(14, 4) | yes |  |
| `stale_after_hours` | integer | yes |  |
| `auto_create_wo` | boolean | no |  |
| `wo_priority_on_critical` | enum(P1, P2, P3, P4) | no |  |
| `recommended_action` | text | yes |  |
| `external_tag` | varchar(200) | yes |  |
| `last_status` | enum(normal, warning, critical, unknown) | no |  |
| `last_value` | numeric(14, 4) | yes |  |
| `last_reading_at` | datetime | yes |  |
| `is_active` | boolean | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, code)

Indexes: ix_measurement_points_asset_id (asset_id); ix_measurement_points_plant_id (plant_id)

### `condition_readings` — append-only

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `point_id` | uuid | no | FK → measurement_points.id (on delete CASCADE) |
| `value` | numeric(14, 4) | no |  |
| `measured_at` | datetime | no |  |
| `status` | enum(normal, warning, critical, unknown) | no |  |
| `source` | varchar(20) | no |  |
| `recorded_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `note` | text | yes |  |
| `created_at` | datetime | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (point_id, measured_at, source)

Indexes: ix_condition_readings_plant_id (plant_id); ix_cond_read_point_time (point_id, measured_at)

### `condition_alerts`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `point_id` | uuid | no | FK → measurement_points.id (on delete CASCADE) |
| `asset_id` | uuid | no | FK → assets.id (on delete RESTRICT) |
| `reading_id` | uuid | no | FK → condition_readings.id (on delete RESTRICT) |
| `severity` | enum(normal, warning, critical, unknown) | no |  |
| `status` | enum(open, acknowledged, wo_created, resolved) | no |  |
| `message` | text | no |  |
| `defect_description` | text | yes |  |
| `recommended_action` | text | yes |  |
| `resolution` | text | yes |  |
| `acknowledged_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `acknowledged_at` | datetime | yes |  |
| `resolved_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `resolved_at` | datetime | yes |  |
| `work_order_id` | uuid | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Indexes: ix_condition_alerts_asset_id (asset_id); ix_alert_point_status (point_id, status); ix_condition_alerts_reading_id (reading_id); ix_condition_alerts_plant_id (plant_id)

## Shutdowns

### `shutdowns`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `code` | varchar(40) | no |  |
| `name` | varchar(200) | no |  |
| `scope` | text | yes |  |
| `department_id` | uuid | yes | FK → departments.id (on delete RESTRICT) |
| `planned_start` | datetime | no |  |
| `planned_end` | datetime | no |  |
| `actual_start` | datetime | yes |  |
| `actual_end` | datetime | yes |  |
| `status` | enum(planning, ready, in_progress, completed, cancelled) | no |  |
| `budget` | numeric(16, 2) | yes |  |
| `completion_report` | text | yes |  |
| `lessons_learned` | text | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (plant_id, code)

Indexes: ix_shutdowns_department_id (department_id); ix_shutdowns_plant_id (plant_id)

### `shutdown_packages`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `shutdown_id` | uuid | no | FK → shutdowns.id (on delete CASCADE) |
| `code` | varchar(40) | no |  |
| `name` | varchar(200) | no |  |
| `asset_id` | uuid | yes | FK → assets.id (on delete RESTRICT) |
| `contractor_id` | uuid | yes | FK → suppliers.id (on delete RESTRICT) |
| `owner_id` | uuid | yes | FK → users.id (on delete RESTRICT) |
| `duration_hours` | numeric(8, 2) | no |  |
| `planned_manpower` | integer | no |  |
| `contractor_manpower` | integer | no |  |
| `planned_start` | datetime | yes |  |
| `planned_finish` | datetime | yes |  |
| `actual_start` | datetime | yes |  |
| `actual_finish` | datetime | yes |  |
| `progress_pct` | numeric(5, 2) | no |  |
| `status` | enum(not_started, in_progress, delayed, completed) | no |  |
| `material_status` | enum(not_ready, partial, ready, not_required) | no |  |
| `permit_status` | enum(not_ready, partial, ready, not_required) | no |  |
| `loto_status` | enum(not_ready, partial, ready, not_required) | no |  |
| `procurement_note` | text | yes |  |
| `delay_reason` | text | yes |  |
| `is_critical` | boolean | no |  |
| `total_float_hours` | numeric(10, 2) | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |
| `created_at` | datetime | no |  |
| `updated_at` | datetime | no |  |

Unique: (shutdown_id, code)

Indexes: ix_shutdown_packages_contractor_id (contractor_id); ix_shutdown_packages_plant_id (plant_id); ix_shutdown_packages_shutdown_id (shutdown_id); ix_shutdown_packages_owner_id (owner_id); ix_shutdown_packages_asset_id (asset_id)

### `package_dependencies`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `package_id` | uuid | no | FK → shutdown_packages.id (on delete CASCADE) |
| `predecessor_id` | uuid | no | FK → shutdown_packages.id (on delete CASCADE) |
| `lag_hours` | numeric(8, 2) | no |  |

Unique: (package_id, predecessor_id)

Indexes: ix_package_dependencies_package_id (package_id); ix_package_dependencies_predecessor_id (predecessor_id)

### `shutdown_progress_logs`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `package_id` | uuid | no | FK → shutdown_packages.id (on delete CASCADE) |
| `log_date` | date | no |  |
| `progress_pct` | numeric(5, 2) | no |  |
| `note` | text | yes |  |
| `delay_reason` | text | yes |  |
| `recorded_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `created_at` | datetime | no |  |

Indexes: ix_shutdown_progress_logs_package_id (package_id)

### `shutdown_checks`

Pre-startup inspections and commissioning checks.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `shutdown_id` | uuid | no | FK → shutdowns.id (on delete CASCADE) |
| `category` | varchar(30) | no |  |
| `description` | varchar(400) | no |  |
| `is_done` | boolean | no |  |
| `result` | text | yes |  |
| `done_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `done_at` | datetime | yes |  |

Indexes: ix_shutdown_checks_shutdown_id (shutdown_id)

## KPIs, reporting & system

### `production_records`

Daily production per department/line: needed for cost-per-ton and OEE (never estimated).

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `department_id` | uuid | no | FK → departments.id (on delete RESTRICT) |
| `asset_id` | uuid | yes | FK → assets.id (on delete RESTRICT) |
| `record_date` | date | no |  |
| `tons_produced` | numeric(12, 3) | no |  |
| `good_tons` | numeric(12, 3) | yes |  |
| `planned_production_hours` | numeric(6, 2) | yes |  |
| `run_hours` | numeric(6, 2) | yes |  |
| `ideal_rate_tph` | numeric(10, 3) | yes |  |
| `created_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, department_id, asset_id, record_date)

Indexes: ix_production_records_plant_id (plant_id); ix_production_records_department_id (department_id); ix_production_records_asset_id (asset_id)

### `maintenance_budgets`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `department_id` | uuid | yes | FK → departments.id (on delete RESTRICT) |
| `year` | integer | no |  |
| `month` | integer | no |  |
| `amount` | numeric(16, 2) | no |  |
| `currency` | varchar(3) | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, department_id, year, month)

Indexes: ix_maintenance_budgets_plant_id (plant_id); ix_maintenance_budgets_department_id (department_id)

### `kpi_definitions`

Documented KPI definitions; `config` holds tunable parameters. Plant overrides live in plant.settings.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `code` | varchar(40) | no | PK |
| `name` | varchar(120) | no |  |
| `formula` | text | no |  |
| `unit` | varchar(20) | no |  |
| `source_data` | text | no |  |
| `inclusion_rules` | text | no |  |
| `higher_is_better` | boolean | no |  |
| `config` | jsonb | no |  |

### `kpi_snapshots`

Monthly KPI values persisted by the scheduler for trend reporting.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `kpi_code` | varchar(40) | no | FK → kpi_definitions.code (on delete NO ACTION) |
| `period_start` | date | no |  |
| `period_end` | date | no |  |
| `scope_key` | varchar(80) | no |  |
| `value` | numeric(18, 4) | yes |  |
| `available` | boolean | no |  |
| `reason` | text | yes |  |
| `computed_at` | datetime | no |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (plant_id, kpi_code, period_start, scope_key)

Indexes: ix_kpi_snapshots_plant_id (plant_id)

### `notifications`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `user_id` | uuid | no | FK → users.id (on delete CASCADE) |
| `kind` | varchar(40) | no |  |
| `severity` | varchar(16) | no |  |
| `title` | varchar(200) | no |  |
| `body` | text | yes |  |
| `link` | varchar(300) | yes |  |
| `dedupe_key` | varchar(160) | yes |  |
| `created_at` | datetime | no |  |
| `read_at` | datetime | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (user_id, dedupe_key)

Indexes: ix_notifications_plant_id (plant_id); ix_notif_user_unread (user_id, read_at)

### `email_outbox`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `notification_id` | uuid | yes | FK → notifications.id (on delete SET NULL) |
| `to_address` | varchar(254) | no |  |
| `subject` | varchar(200) | no |  |
| `body` | text | no |  |
| `status` | enum(pending, sent, failed, disabled) | no |  |
| `attempts` | integer | no |  |
| `last_error` | text | yes |  |
| `next_attempt_at` | datetime | no |  |
| `sent_at` | datetime | yes |  |
| `created_at` | datetime | no |  |

Indexes: ix_email_outbox_notification_id (notification_id); ix_outbox_status (status, next_attempt_at)

### `attachments`

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `entity_type` | varchar(40) | no |  |
| `entity_id` | uuid | no |  |
| `category` | varchar(30) | no |  |
| `filename` | varchar(255) | no |  |
| `content_type` | varchar(100) | no |  |
| `size_bytes` | bigint | no |  |
| `sha256` | varchar(64) | no |  |
| `storage_key` | varchar(400) | no |  |
| `uploaded_by_id` | uuid | yes | FK → users.id (on delete NO ACTION) |
| `created_at` | datetime | no |  |
| `deleted_at` | datetime | yes |  |
| `plant_id` | uuid | no | FK → plants.id (on delete RESTRICT) |

Unique: (storage_key)

Indexes: ix_attach_entity (entity_type, entity_id); ix_attachments_plant_id (plant_id)

### `audit_logs` — append-only

Append-only (UPDATE/DELETE blocked by trigger). Bigint PK preserves insertion order.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | bigint | no | PK |
| `at` | datetime | no |  |
| `organization_id` | uuid | yes |  |
| `plant_id` | uuid | yes |  |
| `user_id` | uuid | yes |  |
| `action` | varchar(60) | no |  |
| `entity_type` | varchar(60) | yes |  |
| `entity_id` | varchar(64) | yes |  |
| `data` | jsonb | no |  |
| `ip` | varchar(64) | yes |  |

Indexes: ix_audit_entity (entity_type, entity_id); ix_audit_plant_time (plant_id, at)

### `job_runs`

Observability for background jobs.

| Column | Type | Null | Key / reference |
|---|---|---|---|
| `id` | uuid | no | PK |
| `job` | varchar(60) | no |  |
| `started_at` | datetime | no |  |
| `finished_at` | datetime | yes |  |
| `status` | varchar(16) | no |  |
| `details` | jsonb | no |  |
| `error` | text | yes |  |

Indexes: ix_job_runs_job_time (job, started_at)
