# Backup and restore

## Recovery objectives (targets)

| Objective | Target | How it is met |
|---|---|---|
| **RPO** (max data loss) | **≤ 15 minutes** with managed PostgreSQL point-in-time recovery; **≤ 24 hours** for the Docker Compose deployment using nightly logical backups | Cloud SQL / RDS PITR (continuous WAL archiving, 7–35 day retention). Compose: `scripts/backup.sh` via cron; increase frequency or add WAL archiving if 24 h is too long. |
| **RTO** (time to restore service) | **≤ 4 hours** | Restore drill of the current data set took 4 s for restore + migration; most of the RTO budget is for provisioning, verification and DNS. Re-measure with production-size data. |

These are targets, not measured production figures. The restore drill below is the only measured result.

## What is backed up
1. **Database** — `pg_dump -Fc` (custom format, compressed) including schema, data, triggers and sequences.
2. **Attachment storage** — tarball of the storage volume (local backend). For S3/GCS, enable bucket versioning and
   cross-region replication instead.
3. **Manifest** — migration revision and per-table row counts, plus SHA-256 checksums for all files.

Secrets are **not** in backups; they live in the secret manager.

## Procedures

```bash
# Backup (Compose deployment, from the repository root)
scripts/backup.sh /secure/backups            # RETENTION_DAYS=14 by default
# copy the directory off the host to encrypted, versioned object storage, e.g.
#   gsutil -m cp -r /secure/backups gs://acme-cmms-backups/   (bucket with CMEK + retention policy)

# Restore into a target database (refuses without --yes-overwrite; verifies checksums when present)
scripts/restore.sh /secure/backups/cmms_<ts>.dump postgresql://cmms_owner:***@host:5432/cmms \
   /secure/backups/storage_<ts>.tar.gz /restore/storage --yes-overwrite
CMMS_MIGRATION_DATABASE_URL=... alembic upgrade head      # re-applies grants and any newer migrations
curl https://<host>/api/v1/health/ready

# Restore drill in a throw-away container (non-production)
ENV_FILE=deploy/.env scripts/verify_restore.sh
```

Cron example (Compose host): `15 1 * * * cd /opt/cmms && scripts/backup.sh /secure/backups >> /var/log/cmms-backup.log 2>&1`

## Restore drill result (executed 2026-10-25 on the Compose stack)
```
tables compared: 74; rows in source: 610; mismatches: 0; restore+migrate time: 4 s; app-role read work_orders=1
RESTORE DRILL PASSED
```
The drill: takes a fresh backup → starts an empty PostgreSQL 16 container with the role-init script → `pg_restore`
→ `alembic upgrade head` → compares every table's row count with the manifest → verifies the least-privilege
runtime role can read restored data.

## Managed PostgreSQL (recommended for production)
* Enable automated daily backups + PITR; retention ≥ 14 days; deletion protection on.
* Run the logical backup weekly as well (portable, protects against provider-level issues).
* Quarterly: restore the latest backup into staging, run `scripts/verify_restore.sh`-equivalent checks and the E2E suite.

## Off-host copy to Oracle Object Storage (single-server install)
1. Console → Storage → Buckets → *Create bucket* (Standard tier, private). Always Free includes 20 GB.
2. Open the bucket → *Pre-authenticated requests* → *Create*: target *Bucket*, access *Permit object writes*,
   expiry far in the future. Copy the URL (it ends with `/o/`) — it is a secret, do not share it.
3. On the server: `cd /opt/cmms && sudo bash scripts/set-backup-upload.sh`, paste the URL (not echoed). It is stored in
   `deploy/.env` and a test backup is uploaded immediately; afterwards every nightly backup is uploaded to
   `<yyyymmdd>/` in the bucket.
4. Optional: a bucket lifecycle rule deleting objects older than 30 days keeps usage under the free 20 GB.
