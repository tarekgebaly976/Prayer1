# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Login always fails with "Invalid email or password" | wrong password, inactive account, or membership disabled | Admin → Users → check *Active*; reset by creating a new password via admin (or `bootstrap` for the first admin) |
| "Account temporarily locked" (429) | 5 failed attempts | wait 15 min (`CMMS_LOGIN_LOCKOUT_MINUTES`) — lockouts are in the audit log (`auth.lockout`) |
| Logged out right after login / every request 401 | session cookie not stored: site served over **http** with `CMMS_COOKIE_SECURE=true` | serve via HTTPS (Caddy) or, for local http only, set `CMMS_COOKIE_SECURE=false` |
| 403 "CSRF token missing or invalid" | stale tab after logout/login elsewhere | reload the page |
| 403 "No access to this plant" | user lacks membership for the selected plant | Admin → Users (in that plant) |
| Work order won't move to *In progress* | LOTO/permit sign-off missing | supervisor: Checklist tab → "Sign off LOTO / permit" |
| Can't complete a work order | message lists the missing items: required checklist items, test result, failure codes, root cause (emergency), pending lubrication tasks | complete them; these guards are intentional |
| PM work orders not generated | worker not running, plan inactive, or occurrence not yet inside the lead window | Admin → Background jobs; PM → "Run scheduler now"; check plan *lead days* |
| Duplicate PM work order | not possible: DB unique constraints. If you see two, they belong to different occurrences (check due dates) | — |
| "Insufficient stock" on reserve/issue | available = on hand − reserved | receive stock, cancel old reservations, or check the warehouse |
| Lubricant rejected on lube task | not the specified lubricant and no approved alternative | reliability engineer: Lubrication → Approve alternative (with compatibility evidence) |
| KPI shows "Not available" | required source data missing (reason shown) | enter production records/budgets, roster, downtime events as indicated |
| Upload rejected 415 | extension not allowed or content doesn't match extension | use PDF/PNG/JPEG/WEBP/XLSX/DOCX/DWG/DXF/CSV/TXT |
| `/api/v1/health/ready` returns 503 | database unreachable | check DB container/instance, credentials, network |
| API logs "permission denied for table …" | migrations not applied with grants | run `alembic upgrade head` as the owner role (re-applies grants) |
| Docker build fails with certificate errors behind a corporate proxy | proxy re-signs TLS | build with `deploy/docker-compose.build-proxy.yml` and `EXTRA_CA_FILE` |
| Emails not sent | SMTP not configured (outbox status `disabled`) | set `CMMS_SMTP_*`; check Admin → Background jobs |
