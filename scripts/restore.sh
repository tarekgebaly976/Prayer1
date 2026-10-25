#!/usr/bin/env bash
# Restore a CMMS backup into a TARGET PostgreSQL (refuses to run without explicit confirmation).
#   scripts/restore.sh <dump_file> <target_db_url_for_owner_role> [storage_tar] [storage_dir] --yes-overwrite
# The target database must exist and its owner role must match (cmms_owner); the runtime role cmms_app
# must exist (see deploy/db-init/01-roles.sh). After restore, `alembic upgrade head` re-applies grants.
set -euo pipefail
DUMP="${1:?dump file}"; TARGET="${2:?target database URL (postgresql://owner:pw@host:port/db)}"
STORAGE_TAR="${3:-}"; STORAGE_DIR="${4:-}"
[[ " $* " == *" --yes-overwrite "* ]] || { echo "Refusing: add --yes-overwrite to confirm the target will be overwritten"; exit 2; }
SUMS="$(dirname "$DUMP")/SHA256SUMS_$(basename "$DUMP" .dump | sed 's/^cmms_//')"
if [[ -f "$SUMS" ]]; then ( cd "$(dirname "$DUMP")" && sha256sum --check --ignore-missing "$(basename "$SUMS")" ); fi
echo "[restore] restoring database"
pg_restore --clean --if-exists --no-acl --exit-on-error -d "$TARGET" "$DUMP"
if [[ -n "$STORAGE_TAR" && -n "$STORAGE_DIR" ]]; then
  echo "[restore] restoring attachment storage into $STORAGE_DIR"
  mkdir -p "$STORAGE_DIR" && tar -C "$STORAGE_DIR" -xzf "$STORAGE_TAR"
fi
echo "[restore] done. Next: run 'alembic upgrade head' against the target (re-applies grants), then verify /api/v1/health/ready."
