# Security model and operational checklist

## Controls implemented (and where they are tested)

| Requirement | Implementation | Test evidence |
|---|---|---|
| Authentication | Local accounts, Argon2id (`argon2-cffi` defaults), automatic rehash on login | `test_auth_security.py` |
| Password policy | ≥ 12 chars, 3 of 4 character classes | `test_password_policy_on_user_create` |
| Brute force | Per-account lockout (5 failures → 15 min), per-IP failure ceiling, login rate limit, constant-time path for unknown users, generic error | `test_wrong_password_generic_error_and_lockout` |
| Sessions | Opaque random token in **HttpOnly, Secure, SameSite=Lax** cookie; only SHA-256 digest stored; 12 h absolute / 120 min idle expiry; revoked on logout, password change, membership disable | `test_logout_revokes_server_session`, `test_disabling_membership_revokes_sessions` |
| No tokens in localStorage | Session never reachable from JS; localStorage only holds the selected plant id (UI preference) | code review (`frontend/src/lib/session.tsx`) |
| CSRF | Double-submit token bound to the server session, required on every non-GET request | `test_csrf_required_for_mutations` |
| Authorization | Permission check on every endpoint (`require(...)`), plant membership, department restriction, field-level rules (technicians may only edit execution fields of work they are assigned) | `test_rbac_tenancy.py`, `test_workorders.py`, E2E "technician cannot reach administration" |
| Tenant isolation | `plant_id` on every tenant row, enforced in queries; cross-plant ids return 404/422 | `test_cross_plant_*`, `test_two_plants_independent_numbering`, file test |
| Segregation of duties | PM deferral/cancellation and handover confirmation cannot be approved by the requester; emergency closure needs `wo.close_emergency`; safety sign-off before work starts on LOTO/permit jobs | `test_deferral_needs_supervisor_and_four_eyes`, `test_supervisor_cannot_confirm_own_handover`, lifecycle tests |
| Input validation | Pydantic models with `extra="forbid"` (mass-assignment protection), length/range checks, DB constraints | `test_unknown_fields_rejected` |
| SQL injection | SQLAlchemy parameterised queries only; no string-built SQL on user input | `ruff` rule S608 (only static DDL in migrations is exempted) |
| XSS | React output encoding; no `dangerouslySetInnerHTML`; CSP; uploaded files served as attachments with `nosniff` and sandbox CSP; SVG/HTML uploads rejected | `test_file_upload_validation_and_authorization` |
| File uploads | Extension allow-list + magic-byte check, size limit (25 MB), server-generated storage keys, authorization on entity, private storage, signed URLs (S3/GCS) | same |
| Spreadsheet export | Formula injection neutralised in CSV/XLSX exports | `test_export_csv_formula_injection_neutralised` |
| Audit | Append-only `audit_logs` (trigger + revoked UPDATE/DELETE for the app role) for logins, lockouts, user/role changes, status transitions, safety sign-off, inventory movements, approvals, imports | `test_audit_log_append_only`, `test_ledger_is_append_only` |
| Least-privilege DB | `cmms_owner` runs migrations; runtime uses `cmms_app` with DML only and no UPDATE/DELETE on ledgers | all tests run as `cmms_app` |
| Secrets | Only from environment / secret manager; `.env` files git-ignored; templates contain no secrets | repository review |
| Transport | Caddy TLS 1.3, HTTP→HTTPS 308, HSTS | verified with curl/openssl on the Compose stack |
| Security headers | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, `Cache-Control: no-store` on API | `test_security_headers`, curl |
| CORS | Not needed (single origin); only enabled if `CMMS_CORS_ORIGINS` is explicitly set | config |
| Rate limiting | Per-IP sliding window in each API process (300/min API, 20/min login) | config; **add edge/WAF limits when running multiple replicas** |
| Industrial integration | Separate revocable write-only token per gateway; cannot read data or call user APIs; no outbound control commands exist | `test_gateway_ingestion_token_and_dedup` |
| Dependency scanning | `pip-audit` and `npm audit` in CI | last run: **no known vulnerabilities** (see TEST_REPORT) |

### Dependency note
npm packages were pinned to releases at least two weeks old, **except Next.js 16.4.3** (published 2026-10-24), adopted
because 16.0.0–16.4.0 are affected by critical advisories (GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr,
GHSA-p3m5-59mp-jv5r). The image-optimisation endpoint is additionally disabled (`images.unoptimized`).

## Product: one instance per customer (from 2026-11)
* Each customer gets a **separate PlantPulse**: own database, attachments, settings and users, own address
  `https://<name>.plantpulse-cmms.com` with automatic HTTPS. No customer can see another customer's data or the plant's.
* The first administrator gets a random password; **nothing is e-mailed to a customer until the owner approves** the
  welcome e-mail (`customer.sh welcome <name> --preview` first).
* Memory limits per customer container; creation refused when the server is short of memory.
* The public demo is a separate system (blue DEMO label) with sample data only and no e-mail from the app.
* Website forms: honeypot field, rate limits, at most 3 e-mails per address per day.
* Mail domain `plantpulse-cmms.com` verified with SPF, DKIM and DMARC (Resend, DNS on Cloudflare).
* Secrets (Resend API key, Object Storage pre-authenticated URL, database passwords) stay on the server; never in
  documents, chats or screenshots.

## Server network security (Oracle Cloud) – checked 2026-11-04
Checked by the owner on the live server (Oracle console + Cloud Shell, read-only). Nothing was changed.

**Oracle Security List** (`Default Security List for vcn-20261025-1650`, VCN `10.0.0.0/16`), ingress rules:

| Port / protocol | Source | Purpose |
|---|---|---|
| TCP 22 | 0.0.0.0/0 | SSH (administration from Cloud Shell, whose address changes) |
| TCP 80 | 0.0.0.0/0 | HTTP, redirected to HTTPS by Caddy |
| TCP 443 | 0.0.0.0/0 | HTTPS (plant CMMS, website, demo, customers) |
| ICMP | 0.0.0.0/0 | Oracle default (network error messages) |
| ICMP (2 rules) | 10.0.0.0/16 | Oracle default, inside the VCN only |

No Network Security Groups are used. No other port is open.

**On the server:**
* SSH: `passwordauthentication no` (key only), `permitrootlogin without-password` (root never by password; Oracle's
  Ubuntu image directs root to the `ubuntu` user).
* Host firewall (iptables): `deploy/install-server.sh` opens TCP 80/443 on top of the Oracle image rules (SSH only)
  and saves them with `iptables-persistent`. The live rule list was not captured in this check.
* Listening ports: 22 (SSH), 80/443 (Caddy), 53 on `127.0.0.54` only (local DNS), 111 (`rpcbind`, an OS service).
  Port 111 is **not reachable from the internet** (not in the Security List).
* PostgreSQL publishes no port; only Caddy publishes 80/443 (`deploy/docker-compose.yml`).
* Cloudflare is **DNS only** (no proxy / WAF in front of the server).

Optional hardening (not urgent): `PermitRootLogin no`; stop `rpcbind` (port 111) if nothing uses it; Cloudflare
proxy/WAF if traffic grows. Re-check this section after any change to the Security List or the installer.

## Known security limitations / follow-ups
1. CSP allows `'unsafe-inline'` scripts (Next.js bootstrap). Follow-up: nonce-based CSP via middleware.
2. No SSO/MFA yet. For production, front the app with the corporate IdP (OIDC) or add TOTP MFA for admin roles.
3. In-process rate limiting is per replica; add a WAF/load-balancer limit in cloud deployments.
4. PostgreSQL row-level security is not enabled; isolation relies on application checks (tested).
5. Attachments are not malware-scanned; add ClamAV or a cloud scanning service before accepting files from outside the company.
6. No formal penetration test has been performed.

## Operational security checklist (before go-live)
- [ ] Generate unique strong DB passwords; store in a secret manager; rotate quarterly.
- [ ] `CMMS_ENVIRONMENT=production` (disables OpenAPI docs), `CMMS_COOKIE_SECURE=true`.
- [ ] Database not publicly reachable (private IP / Cloud SQL connector); TLS to DB.
- [ ] Attachment bucket private, uniform access, versioning + encryption enabled.
- [ ] Bootstrap one system administrator; create named accounts for everyone else; no shared accounts.
- [ ] Review role matrix (`ROLES_PERMISSIONS.md`) with maintenance management; restrict department where appropriate.
- [ ] Configure alerting on failed jobs, 5xx rate, login lockouts (see OPERATIONS.md).
- [ ] Backups scheduled, copied off-site, restore drill passed in the target environment.
- [ ] Industrial gateway on the OT side of the firewall, outbound-only HTTPS, one token per gateway.
- [ ] Penetration test and remediation.
