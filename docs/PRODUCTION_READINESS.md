# Production readiness assessment

**Verdict: ready for a supervised pilot (staging with real users) — not yet for unsupervised production.**
Blocking items before production: cloud deployment in the target account with managed PostgreSQL/backups (L),
real-device mobile testing, SSO or MFA for privileged users, and a penetration test.

## Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| A | Create asset in correct plant/department | **Done** | `test_hierarchy_example_and_rules`, `test_department_restricted_membership`; UI form |
| B | PM plan generates WO without duplication | **Done** | `test_pm_generation_is_idempotent`, `test_pm_scheduler_concurrent_runs_no_duplicates`; worker run logged WO-DMO-000001 |
| C | Assign, execute, approve, close | **Done** | `test_full_lifecycle_request_to_technical_closure`; UI E2E (planner → supervisor → technician on phone viewport → supervisor) on local and HTTPS Compose stack |
| D | Lubrication plan, route, record, next due | **Done** | `test_lubrication_route_record_and_next_due` |
| E | Shifts and handover | **Done** | `test_roster_pattern_and_handover` (API); UI built, not E2E-automated |
| F | Reserve, issue, transaction and cost | **Done** | `test_reserve_issue_against_wo_and_cost`, concurrency test |
| G | Reading → warning → follow-up WO | **Done** | `test_reading_warning_alert_and_followup_wo`; UI E2E for warning alert |
| H | KPIs against known records + drill-down | **Done** | `test_kpi.py` (hand-computed values); UI E2E drill-down |
| I | Unauthorized users / other plant blocked | **Done** | `test_rbac_tenancy.py`, file and security tests, E2E |
| J | Persistence after browser close and app restart | **Done** | E2E fresh browser context; API process restarted with data intact (count before/after: 1 closed WO) |
| K | Backup and restore in test environment | **Done** | `scripts/verify_restore.sh`: 74 tables, 0 mismatches |
| L | Deploy to selected cloud, HTTPS, desktop + mobile | **Partial** | Trial cloud deployment on an Oracle Cloud Always Free VM (me-riyadh-1, ARM) via `deploy/install-server.sh`; HTTPS at https://84-8-106-22.sslip.io with a Let's Encrypt certificate. The owner signed in and saw the dashboard in a desktop browser (2026-10-26). Remaining: real-phone test, confirm backup cron, production target with managed PostgreSQL/PITR and monitoring. |
| M | Critical workflows have automated coverage, results documented | **Done** (with gaps listed in TEST_REPORT) | 60 backend tests, 8 E2E, report in TEST_REPORT.md |

## Readiness by area
| Area | State |
|---|---|
| Functionality (modules 5–13) | Implemented end-to-end with real persistence |
| Security | Strong baseline (SECURITY.md); needs MFA/SSO, pentest, nonce CSP |
| Data integrity | Constraints, transactions, row locks, append-only ledgers, idempotent jobs — tested |
| Performance | Measured on 100k assets / 50k WOs; must be re-measured on target infra |
| Operations | Health checks, JSON logs, job tracking; alert rules defined but not configured in a monitoring product |
| Backup/DR | Scripts + passing drill; production should use managed PITR |
| Mobile | Responsive + PWA installable; **no offline data capture** |
| i18n | Full EN/AR UI with RTL; backend-generated messages and PDFs are English-only |

## Known limitations
1. **Offline work is not supported**: the PWA caches the app shell only; records require connectivity. This is
   deliberate (no silent conflict overwrites) — offline queue with conflict detection is on the roadmap.
2. Backend messages (validation errors, KPI "unavailable" reasons, notifications) and PDF reports are English only;
   PDFs do not shape Arabic text.
3. Some configuration is API-only (shift definitions, numbering prefixes); no UI form yet.
4. No ERP/Infor, SSO, MFA, or SMS integration. E-mail requires SMTP configuration.
5. Condition monitoring is rule-based (limits); no ML/failure prediction (by design until data exists).
6. Industrial gateway (OPC UA/MQTT) is an external component: only the ingestion API and token model are provided.
7. Gantt views are read-only (no drag-to-reschedule); WO scheduling calendar view not implemented (list + dates).
8. Rate limiting is per API process; use an edge/WAF limit for multi-replica deployments.
9. mypy reports 78 typing findings (non-gating).
10. Accessibility has not been audited (Mantine components are accessible by default; custom Gantt is not).

## Roadmap (suggested order)
1. Cloud deployment to staging (GCP template), monitoring alerts, PITR, real-device testing → pilot in one department.
2. OIDC SSO (Azure AD / Google) + MFA for admins and approvers; nonce-based CSP; WAF.
3. Offline technician mode (IndexedDB queue, per-record version check, conflict UI).
4. Arabic for server-generated messages and PDFs (RTL font shaping).
5. Planner calendar/Gantt with drag-and-drop scheduling and capacity view; UI for shift definitions/numbering.
6. OPC UA / MQTT gateway reference implementation; vibration spectrum attachments.
7. ERP integration (purchase requisitions/receipts) once the ERP interface is specified.
8. Reliability analytics (Weibull, bad-actor reports) when sufficient failure history exists.
