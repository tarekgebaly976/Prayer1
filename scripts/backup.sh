#!/usr/bin/env bash
# Logical backup of the CMMS database + attachment storage.
#   scripts/backup.sh [backup_dir]            (Docker Compose deployment; run from repo root)
# Produces: cmms_<ts>.dump (pg_dump custom format), storage_<ts>.tar.gz, SHA256SUMS, manifest.json.
# Store backups OUTSIDE the host (object storage with encryption + versioning). Never commit them.
# Off-host copy: if BACKUP_UPLOAD_URL (an object-storage pre-authenticated request URL for a bucket, ending in /o/)
# is set in the environment or in the env file, each backup is also uploaded there (see scripts/set-backup-upload.sh).
set -euo pipefail
DIR="${1:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE=(docker compose -f deploy/docker-compose.yml --env-file "${ENV_FILE:-deploy/.env}")
TS="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DIR"
umask 077

echo "[backup] dumping database"
"${COMPOSE[@]}" exec -T db pg_dump -U cmms_owner -d cmms -Fc --no-acl > "$DIR/cmms_$TS.dump"
echo "[backup] archiving attachment storage"
"${COMPOSE[@]}" exec -T api tar -C /app/var -czf - storage > "$DIR/storage_$TS.tar.gz"
REV="$("${COMPOSE[@]}" exec -T db psql -U cmms_owner -d cmms -Atc 'SELECT version_num FROM alembic_version')"
ROWS="$("${COMPOSE[@]}" exec -T db psql -U cmms_owner -d cmms -Atc "SELECT json_object_agg(relname, n) FROM (SELECT c.relname, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I', c.relname), false, true, '')))[1]::text::bigint AS n FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace WHERE ns.nspname='public' AND c.relkind='r') t")"
printf '{"timestamp":"%s","migration":"%s","row_counts":%s}\n' "$TS" "$REV" "$ROWS" > "$DIR/manifest_$TS.json"
( cd "$DIR" && sha256sum "cmms_$TS.dump" "storage_$TS.tar.gz" "manifest_$TS.json" > "SHA256SUMS_$TS" )
pg_restore --list "$DIR/cmms_$TS.dump" > /dev/null 2>&1 || "${COMPOSE[@]}" exec -T db pg_restore --list < "$DIR/cmms_$TS.dump" > /dev/null
echo "[backup] verified dump is readable"
find "$DIR" -type f -mtime +"$RETENTION_DAYS" \( -name 'cmms_*.dump' -o -name 'storage_*.tar.gz' -o -name 'manifest_*.json' -o -name 'SHA256SUMS_*' \) -delete
URL="${BACKUP_UPLOAD_URL:-$(grep -s '^BACKUP_UPLOAD_URL=' "${ENV_FILE:-deploy/.env}" | cut -d= -f2- || true)}"
if [[ -n "$URL" ]]; then
  for f in "cmms_$TS.dump" "storage_$TS.tar.gz" "manifest_$TS.json" "SHA256SUMS_$TS"; do
    curl -fsS --retry 3 -T "$DIR/$f" "${URL%/}/${TS:0:8}/$f" > /dev/null
  done
  echo "[backup] uploaded off-host copy to object storage (${TS:0:8}/)"
fi
echo "[backup] done: $DIR/cmms_$TS.dump ($(du -h "$DIR/cmms_$TS.dump" | cut -f1)), migration $REV"
