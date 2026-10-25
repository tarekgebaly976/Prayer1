# Roles and permissions

_Generated from `app/core/permissions.py`. Enforced server-side on every endpoint; the UI only hides what the server would refuse._

| Permission | Description | System Administrator | Maintenance Manager | Maintenance Planner | Mechanical Supervisor | Electrical/Automation Supervisor | Reliability Engineer | Engineer | Technician | Storekeeper | Production User | Management Viewer |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `plant.admin` | Administer plant settings, users, numbering, workflow | ✓ |  |  |  |  |  |  |  |  |  |  |
| `user.manage` | Create/disable users and memberships | ✓ |  |  |  |  |  |  |  |  |  |  |
| `audit.view` | View audit logs | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `asset.view` | View assets | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `asset.edit` | Create and edit assets, BOMs, meters | ✓ | ✓ | ✓ |  |  | ✓ | ✓ |  |  |  |  |
| `asset.import` | Bulk import assets | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |
| `request.create` | Submit work requests | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |
| `request.triage` | Triage work requests | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `wo.view` | View work orders | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `wo.create` | Create work orders | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `wo.edit` | Edit work order details | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `wo.approve` | Approve work orders | ✓ | ✓ |  | ✓ | ✓ |  |  |  |  |  |  |
| `wo.plan` | Plan and schedule work orders | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `wo.assign` | Assign technicians (including bulk assignment) | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `wo.execute` | Start work, record labor/checklists/findings | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ |  |  |  |
| `wo.review` | Inspect/test and review completed work | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `wo.safety_signoff` | Sign off LOTO/permit safety requirements | ✓ | ✓ |  | ✓ | ✓ |  |  |  |  |  |  |
| `wo.close` | Technically close work orders | ✓ | ✓ |  | ✓ | ✓ |  |  |  |  |  |  |
| `wo.close_emergency` | Close emergency work orders | ✓ | ✓ |  | ✓ | ✓ |  |  |  |  |  |  |
| `wo.cancel` | Cancel work orders | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `pm.view` | View PM plans | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |
| `pm.manage` | Create and edit PM plans and job plans | ✓ | ✓ | ✓ |  |  | ✓ |  |  |  |  |  |
| `pm.approve_deferral` | Approve PM deferrals and cancellations | ✓ | ✓ |  | ✓ | ✓ |  |  |  |  |  |  |
| `pm.run_scheduler` | Run the PM scheduler on demand | ✓ | ✓ | ✓ |  |  |  |  |  |  |  |  |
| `lube.view` | View lubrication | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |
| `lube.manage` | Manage lubrication points, routes, lubricants | ✓ | ✓ | ✓ |  |  | ✓ |  |  |  |  |  |
| `lube.approve_alternative` | Approve lubricant alternatives (compatibility verified) | ✓ | ✓ |  |  |  | ✓ |  |  |  |  |  |
| `lube.execute` | Record lubrication tasks | ✓ | ✓ |  | ✓ | ✓ |  |  | ✓ |  |  |  |
| `shift.view` | View shifts and rosters | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |
| `shift.manage` | Manage shift patterns, teams and rosters | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `handover.create` | Write shift handovers | ✓ | ✓ |  | ✓ | ✓ |  | ✓ | ✓ |  |  |  |
| `handover.confirm` | Confirm shift handovers | ✓ | ✓ |  | ✓ | ✓ |  |  |  |  |  |  |
| `inventory.view` | View spare parts and stock | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |
| `inventory.manage` | Manage part master data | ✓ | ✓ |  |  |  |  |  |  | ✓ |  |  |
| `inventory.transact` | Receive, issue, return stock | ✓ | ✓ |  |  |  |  |  |  | ✓ |  |  |
| `inventory.adjust` | Stock adjustments | ✓ | ✓ |  |  |  |  |  |  | ✓ |  |  |
| `inventory.reserve` | Reserve materials for work orders | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  | ✓ |  |  |
| `purchase.manage` | Manage purchase requisitions / PO references | ✓ | ✓ | ✓ |  |  |  |  |  | ✓ |  |  |
| `pdm.view` | View condition monitoring | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ |
| `pdm.manage` | Manage measurement points and limits | ✓ | ✓ |  |  |  | ✓ |  |  |  |  |  |
| `pdm.record` | Record condition readings | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `pdm.alert_manage` | Acknowledge/resolve condition alerts | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |  |  |  |  |
| `shutdown.view` | View shutdowns | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |
| `shutdown.manage` | Plan and update shutdowns | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `kpi.view` | View KPI dashboards | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  | ✓ | ✓ |
| `kpi.manage` | Maintain production records, budgets, KPI settings | ✓ | ✓ | ✓ |  |  | ✓ |  |  |  |  |  |
| `report.export` | Export reports | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  | ✓ |
| `attachment.upload` | Upload attachments | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
