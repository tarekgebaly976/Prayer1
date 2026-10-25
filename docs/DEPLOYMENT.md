# Deployment, CI/CD and rollback

> **Status:** The Docker Compose deployment (with TLS via Caddy) has been built and run in a test environment and
> verified with the full E2E suite over HTTPS. **No public cloud deployment has been performed** because no cloud
> credentials were available; the cloud steps below are instructions and an unexecuted pipeline template.

## Environments
| Environment | Purpose | Data |
|---|---|---|
| development | local `uvicorn` + `next dev`, local PostgreSQL | demo data via `seed-demo` |
| staging | same images as production, separate project/database/bucket | anonymised copy or demo data; restore drills run here |
| production | plant use | real data only; demo organisation never seeded |

Configuration differs only by environment variables / secrets (`CMMS_ENVIRONMENT`, DB URLs, storage, SMTP, domain).
Backend variables are documented in `backend/.env.example` and `app/core/config.py`; Compose variables in `deploy/.env.example`.

## Option A — single VM / on-premises server with Docker Compose (verified)
1. Linux host with Docker Engine ≥ 24 and Compose v2; DNS record for `CMMS_DOMAIN`; ports 80/443 open.
2. `cp deploy/.env.example deploy/.env`, set strong passwords (`openssl rand -base64 32`), `CMMS_DOMAIN`, `CMMS_ENVIRONMENT=production`.
3. `docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build`
   (the `migrate` service runs `alembic upgrade head` before API/worker start).
4. Bootstrap the first administrator (README). Caddy obtains a Let's Encrypt certificate automatically.
5. Schedule `scripts/backup.sh` (BACKUP_RESTORE.md) and ship backups off the host.

Behind a TLS-intercepting egress proxy, build with `docker-compose.build-proxy.yml` (supplies a CA bundle as a BuildKit
secret; it is never stored in an image layer).

## Option B — Google Cloud (recommended managed setup; template provided, not executed)
Chosen because it is the simplest fully managed path for a container monolith + PostgreSQL: Cloud Run (API, web,
worker with min-instances = 1), Cloud SQL for PostgreSQL 16 (automated backups + PITR, private IP, encryption at rest),
Cloud Storage for attachments (accessed through the S3-compatible XML API with HMAC keys: `CMMS_STORAGE_BACKEND=s3`,
`CMMS_S3_ENDPOINT_URL=https://storage.googleapis.com`), Secret Manager, Artifact Registry, Cloud Logging/Monitoring,
external HTTPS load balancer with a Google-managed certificate (and Cloud Armor for WAF/rate limiting). AWS
(ECS Fargate + RDS + S3 + ALB/ACM) and Azure (Container Apps + Flexible Server + Blob) map one-to-one.

One-time setup (run by someone with project-owner rights — **this incurs charges; requires approval**):
```bash
gcloud config set project <PROJECT>
gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories create cmms --repository-format=docker --location=<REGION>
gcloud sql instances create cmms-prod --database-version=POSTGRES_16 --region=<REGION> --tier=db-custom-2-7680 \
  --availability-type=REGIONAL --backup --enable-point-in-time-recovery --retained-backups-count=14 --deletion-protection
gcloud sql databases create cmms --instance=cmms-prod
gcloud sql users create cmms_owner --instance=cmms-prod --password=<from secret manager>
gcloud sql users create cmms_app   --instance=cmms-prod --password=<from secret manager>
# grant: run deploy/db-init/01-roles.sh equivalent SQL as cmms_owner (database owner) once
gcloud storage buckets create gs://<PROJECT>-cmms-attachments --location=<REGION> --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://<PROJECT>-cmms-attachments --versioning
# secrets: cmms-db-url, cmms-migration-db-url, cmms-smtp-password, S3/HMAC keys
```
Then configure the GitHub environment (`vars`: GCP_PROJECT, GCP_REGION, GCP_ARTIFACT_REPO, CLOUDSQL_INSTANCE,
ATTACHMENT_BUCKET, API_INTERNAL_URL; `secrets`: GCP_WIF_PROVIDER, GCP_DEPLOY_SA, GCP_RUNTIME_SA) and run
`.github/workflows/deploy.yml` manually. Put the HTTPS load balancer in front with path routing `/api/*` → API service,
`/*` → web service, so the browser sees one origin.

## CI/CD
* `.github/workflows/ci.yml` (on push/PR): backend lint, type-check (report), tests on PostgreSQL 16 with coverage,
  `pip-audit`; frontend lint, strict type-check, `npm audit`, production build; E2E (Playwright desktop + mobile)
  against a freshly migrated and seeded stack; Docker image builds.
  _The workflow file is committed but has not yet run on GitHub at the time of writing._
* `.github/workflows/deploy.yml` (manual, per environment, protected): build & push images tagged with the commit SHA,
  run migrations as a Cloud Run job, deploy API/worker/web.

## Releases, migrations and rollback
* Migrations are forward-compatible by policy: add columns/tables first, deploy code, remove old columns in a later
  release. Every migration has a `downgrade()`; 0001–0003 are tested up/down in CI (`test_zz_migrations.py`).
* **Rollback (Cloud Run):** `gcloud run services update-traffic cmms-api-production --to-revisions <previous>=100`
  (same for web/worker). Images are immutable and tagged by commit SHA.
* **Rollback (Compose):** `git checkout <previous tag>` → `docker compose ... up -d --build`. If a migration must be
  reverted: `docker compose exec api alembic downgrade <revision>` **after a fresh backup**.
* **Data rollback:** restore from backup / PITR (BACKUP_RESTORE.md). Never run downgrade migrations that drop data in
  production without a verified backup.
