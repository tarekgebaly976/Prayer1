#!/usr/bin/env bash
# Backup/restore drill (non-production): takes a fresh backup of the Compose stack, restores it into a
# throw-away PostgreSQL container, runs migrations against it, and compares per-table row counts.
set -euo pipefail
cd "$(dirname "$0")/.."
WORK="$(mktemp -d)"; NAME="cmms-restore-drill-$$"; PW="$(openssl rand -hex 12)"
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT
scripts/backup.sh "$WORK" >/dev/null
DUMP="$(ls "$WORK"/cmms_*.dump)"; MANIFEST="$(ls "$WORK"/manifest_*.json)"
docker run -d --name "$NAME" -e POSTGRES_USER=cmms_owner -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=cmms -e CMMS_APP_DB_PASSWORD="$PW" \
  -v "$PWD/deploy/db-init:/docker-entrypoint-initdb.d:ro" postgres:16.10-alpine >/dev/null
for _ in $(seq 1 60); do docker exec "$NAME" pg_isready -U cmms_owner -d cmms >/dev/null 2>&1 && break; sleep 1; done
sleep 2
docker cp "$DUMP" "$NAME:/tmp/restore.dump"
START=$(date +%s)
docker exec "$NAME" pg_restore --clean --if-exists --no-acl --exit-on-error -U cmms_owner -d cmms /tmp/restore.dump
docker run --rm --network "container:$NAME" -e CMMS_MIGRATION_DATABASE_URL="postgresql+psycopg://cmms_owner:$PW@127.0.0.1:5432/cmms" \
  -e CMMS_DATABASE_URL="postgresql+psycopg://cmms_app:$PW@127.0.0.1:5432/cmms" papermill-cmms-api alembic upgrade head >/dev/null 2>&1
SECS=$(( $(date +%s) - START ))
RESTORED="$(docker exec "$NAME" psql -U cmms_owner -d cmms -Atc "SELECT json_object_agg(relname, n) FROM (SELECT c.relname, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I', c.relname), false, true, '')))[1]::text::bigint AS n FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace WHERE ns.nspname='public' AND c.relkind='r') t")"
APPCHECK="$(docker exec -e PGPASSWORD="$PW" "$NAME" psql -h 127.0.0.1 -U cmms_app -d cmms -Atc 'SELECT count(*) FROM work_orders')"
python3 - "$MANIFEST" "$RESTORED" "$SECS" "$APPCHECK" <<'PY'
import json, sys
src = json.load(open(sys.argv[1]))["row_counts"]; dst = json.loads(sys.argv[2])
diff = {k: (src.get(k), dst.get(k)) for k in set(src) | set(dst) if src.get(k) != dst.get(k)}
print(f"tables compared: {len(src)}; rows in source: {sum(src.values())}; mismatches: {len(diff)}; restore+migrate time: {sys.argv[3]} s; app-role read work_orders={sys.argv[4]}")
if diff:
    print("MISMATCH", diff); sys.exit(1)
print("RESTORE DRILL PASSED")
PY
