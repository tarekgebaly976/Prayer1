# How to run the tests

## Backend (unit + API integration, real PostgreSQL)
Requires PostgreSQL with roles `cmms_owner` (owns database `cmms_test`) and `cmms_app`:
```sql
CREATE ROLE cmms_owner LOGIN PASSWORD 'dev_owner_pw';
CREATE ROLE cmms_app   LOGIN PASSWORD 'dev_app_pw';
CREATE DATABASE cmms_test OWNER cmms_owner;
```
```bash
cd backend && .venv/bin/pytest -q --cov=app          # schema is rebuilt from migrations at session start
.venv/bin/ruff check app tests alembic && .venv/bin/mypy app && .venv/bin/pip-audit -r requirements.lock
```
The harness applies all Alembic migrations as `cmms_owner`, runs the app as the least-privilege `cmms_app` role,
and uses an HTTPS test client so `Secure` cookies behave as in production. Override URLs with
`CMMS_DATABASE_URL` / `CMMS_MIGRATION_DATABASE_URL`.

## Frontend static checks
```bash
cd frontend && npm run lint && npm run typecheck && npm run build && npm audit --omit=dev
```

## End-to-end (Playwright, desktop + Pixel 7 emulation)
Needs the API seeded with demo data and the web app running:
```bash
cd backend && CMMS_DEMO_PASSWORD='Demo-Passw0rd!2026' .venv/bin/python -m app.cli seed-demo
.venv/bin/uvicorn app.main:app --port 8000 &
cd ../frontend && npm run build && BACKEND_URL=http://127.0.0.1:8000 npx next start -p 3000 &
npx playwright test                                   # E2E_PASSWORD overrides the demo password
# against the HTTPS Compose stack:
E2E_BASE_URL=https://localhost E2E_IGNORE_TLS=1 npx playwright test
```

## Restore drill and load test
```bash
ENV_FILE=deploy/.env scripts/verify_restore.sh
backend/.venv/bin/python scripts/perf/load_test.py --base http://127.0.0.1:8000 --users 20 --seconds 40
```
