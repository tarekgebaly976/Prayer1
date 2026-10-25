# Operations: monitoring, logging, jobs

## Health checks
| Endpoint | Meaning | Use |
|---|---|---|
| `GET /api/v1/health/live` | Process is up | container liveness |
| `GET /api/v1/health/ready` | Database reachable; returns current migration revision; 503 if DB down | load balancer readiness, uptime monitor |
| Web `GET /login` | Next.js serving | container health |

## Logs
API and worker log **JSON lines** to stdout (`ts, level, logger, msg, request_id, path, method, status, duration_ms, job`).
Every response carries `X-Request-Id`; unhandled errors are logged with stack traces and return only the request id
to the client. Ship stdout to Cloud Logging / CloudWatch / Loki.

## What to monitor (and suggested alerts)
| Signal | Source | Alert |
|---|---|---|
| Availability | uptime check on `/api/v1/health/ready` over HTTPS | 2 consecutive failures |
| API errors | log-based metric `status>=500` | > 1 % of requests over 5 min |
| Latency | `duration_ms` p95 per path | p95 > 2 s for 10 min |
| DB connectivity / capacity | ready endpoint, managed DB metrics (CPU, connections, storage) | storage > 80 %, connections > 80 % |
| Background jobs | `job_runs` table (also Admin → Background jobs) | any `failed`, or no `pm_scheduler` success in 1 h |
| Email delivery | `email_outbox` status counts (Admin → Background jobs) | `failed` > 0 |
| Storage usage | bucket/volume metrics | > 80 % |
| Backups | backup job log / managed backup status | missing daily backup |
| Security events | audit actions `auth.lockout`, `user.update`, `integration_token.*`, 401/403 spikes | lockout bursts, token changes |

SQL for job health:
```sql
SELECT job, max(started_at) FILTER (WHERE status='success') AS last_success,
       count(*) FILTER (WHERE status='failed' AND started_at > now()-interval '24 hours') AS failures_24h
FROM job_runs GROUP BY job;
```

## Background jobs
| Job | Schedule | Idempotency |
|---|---|---|
| `pm_scheduler` | every 15 min | unique occurrence keys + unique WO per occurrence + advisory locks |
| `lubrication` | hourly | unique task per (point, due date) |
| `pdm_stale` | hourly | status update only |
| `email_outbox` | every minute | row-level `SKIP LOCKED`, max 5 attempts with exponential backoff |
| `kpi_snapshot` | daily 00:17 UTC | upsert per (plant, KPI, month) |
| `housekeeping` | daily 01:07 UTC | deletes expired sessions (>30 d) and login attempts (>90 d) |

Run exactly **one** worker replica per environment (a second replica is safe — advisory locks make it skip — but wasteful).

## Routine tasks
* Add a plant: `python -m app.cli bootstrap --org-code <existing> ... --plant-code <new>` then assign memberships in Admin.
* Re-sync roles after an upgrade: automatic at API/worker start (`sync_rbac`), or `python -m app.cli sync-rbac`.
* Manual PM run: PM page → "Run scheduler now" (permission `pm.run_scheduler`) or `python -m app.cli run-scheduler`.

## Capacity (measured, not a production claim)
See TEST_REPORT.md → Performance. Re-run `scripts/perf/load_test.py` against staging with production-like data
before go-live.
