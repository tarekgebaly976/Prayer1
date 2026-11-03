# PlantPulse – maintenance management (CMMS) for industrial plants

A database-driven Computerized Maintenance Management System for industrial plants (first built with a paper mill): asset hierarchy,
preventive / predictive / corrective maintenance, lubrication, shifts and handover, spare parts, shutdowns, KPIs
and reports. Web application for desktop, tablet and phone (installable PWA), English and Arabic (RTL).

| | |
|---|---|
| Backend | Python 3.13 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · APScheduler worker |
| Frontend | Next.js 16 (App Router) · React 19 · TypeScript (strict) · Mantine 9 · i18next (EN/AR, RTL) · PWA |
| Deployment | Docker images · Docker Compose (PostgreSQL, API, worker, web, Caddy with automatic TLS) · Cloud Run template |
| Defaults | Currency SAR, timezone Asia/Riyadh (both configurable per plant) |

> **Status:** feature-complete for milestones 1–4 and most of milestone 5, verified by automated tests on a real
> PostgreSQL database, browser end-to-end tests, a containerised HTTPS deployment, and a backup/restore drill.
> Running on Oracle Cloud since 2026-10-26 (plant system), and as a product since 2026-11 (website, demo, customers). See
> [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) and [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md).

## PlantPulse as a product (live)

| | |
|---|---|
| Website | https://plantpulse-cmms.com – EN/AR, "Try the demo" and "Contact us" (`scripts/site.sh`) |
| Public demo | https://demo.plantpulse-cmms.com – sample plant, reset nightly (`scripts/demo.sh`) |
| Customers | https://&lt;name&gt;.plantpulse-cmms.com – one separate PlantPulse per customer (`scripts/customer.sh`) |
| Operator guide | [docs/PLANTPULSE-GUIDE.md](docs/PLANTPULSE-GUIDE.md) (English) · [Arabic](docs/PLANTPULSE-GUIDE-AR.md) – every command |
| Status and plan | [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) · [docs/ROADMAP.md](docs/ROADMAP.md) |

## Quick start (Docker, everything on one machine)

```bash
cp deploy/.env.example deploy/.env           # set strong DB passwords; CMMS_DOMAIN=localhost for a local trial
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
# create the first organization, plant and administrator (prompts for a password)
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api \
  python -m app.cli bootstrap --org-code ACME --org-name "Acme Paper" --plant-code PM1 --plant-name "Mill 1" --admin-email you@example.com
# optional: isolated SAMPLE data in a separate DEMO organization (never mixed with real plants)
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec -e CMMS_DEMO_PASSWORD='choose-a-strong-one' api python -m app.cli seed-demo
```
Open https://localhost (Caddy's local CA; accept or trust it). With a real domain in `CMMS_DOMAIN`, Caddy obtains a
public certificate automatically.

## Development

```bash
# backend
cd backend && uv venv .venv && uv pip install -r requirements.lock
cp .env.example .env          # local PostgreSQL with two roles: cmms_owner (migrations) and cmms_app (runtime DML only)
.venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --reload     # API docs: http://localhost:8000/api/v1/docs
.venv/bin/python -m app.worker                                                 # background scheduler
.venv/bin/pytest                                                                # 59 tests on a real database (cmms_test)
# frontend
cd frontend && npm ci && npm run dev        # http://localhost:3000 (proxies /api to :8000)
npx playwright test                          # E2E, needs API + web running with demo data (docs/TESTING.md)
```

## Documentation

| Topic | Document |
|---|---|
| Architecture, components, diagram | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Database ERD / data dictionary | [docs/ERD.md](docs/ERD.md) · [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) |
| Roles and permissions | [docs/ROLES_PERMISSIONS.md](docs/ROLES_PERMISSIONS.md) |
| KPI definitions and formulas | [docs/KPI_DEFINITIONS.md](docs/KPI_DEFINITIONS.md) |
| Security model and checklist | [docs/SECURITY.md](docs/SECURITY.md) |
| Cloud deployment, CI/CD, rollback | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Backup and restore, RPO/RTO | [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md) |
| Monitoring and operations | [docs/OPERATIONS.md](docs/OPERATIONS.md) |
| User manual / administrator manual | [docs/USER_MANUAL.md](docs/USER_MANUAL.md) · [docs/ADMIN_MANUAL.md](docs/ADMIN_MANUAL.md) |
| Testing and actual results | [docs/TESTING.md](docs/TESTING.md) · [docs/TEST_REPORT.md](docs/TEST_REPORT.md) |
| Troubleshooting | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Production readiness, acceptance criteria, limitations, roadmap | [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) |
| Project status | [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) |
| Product roadmap (website, app, operations) | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Operator guide: website, demo, customers | [English](docs/PLANTPULSE-GUIDE.md) · [Arabic](docs/PLANTPULSE-GUIDE-AR.md) |
| A customer asks for a trial (step by step + record sheet) | [docs/TRIAL-PLAYBOOK.md](docs/TRIAL-PLAYBOOK.md) |
| Excel import templates | [docs/templates/](docs/templates/) |

Generated documents (ERD, data dictionary, KPI definitions, role matrix, templates) are rebuilt with
`cd backend && .venv/bin/python ../scripts/gen_docs.py`.
