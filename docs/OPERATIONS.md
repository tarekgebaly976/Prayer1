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

## Product instances on the shared server (from 2026-11)
The Oracle Cloud server (Riyadh, A1.Flex 2 OCPU / 12 GB RAM / 45 GB disk, 4 GB swap) also runs the product website,
the public demo and the customer instances. Commands: [PLANTPULSE-GUIDE-AR.md](PLANTPULSE-GUIDE-AR.md).

| Scheduled task | When (Riyadh) | What |
|---|---|---|
| Customer backups | nightly 02:45 | verified backup of every customer, 14 days on the server, copy to Oracle Object Storage (`customers/<name>/`); log `/var/log/plantpulse-customers.log` |
| Demo reload | nightly 03:00 | sample plant regenerated relative to "today" |
| Demo password guard | every 10 min | shared demo password restored if a visitor changes it; lock-outs lifted |
| Trial reminders | automatic | e-mail to the owner 7 days / 1 day before, on the day and weekly after a trial ends |

* Health of every system: `sudo docker ps` (all `Up`); customers: `customer.sh list`; memory/disk: `free -h`, `df -h /`.
* Every Caddy change is validated in a throw-away Caddy before the running one is reloaded.
* Capacity measured 2026-11-03: ≈ 0.5 GB RAM and 1–3 GB disk per small customer ⇒ about 10 customers now; grow to
  4 OCPU / 24 GB / 200 GB (free, 2-minute restart) at about 8 live customers ⇒ about 30–40.
* Not yet in place (see [ROADMAP.md](ROADMAP.md)): external uptime monitoring (e.g. UptimeRobot) for the site, demo,
  plant CMMS and each customer.
* Oracle account: Pay As You Go, server within Always Free, budget alert €1/month. Do not create new instances,
  volumes, load balancers or databases without review.
