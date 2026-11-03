#!/usr/bin/env bash
# Wipe the plant's operational data in the MAIN system (and refresh the test copy from it), then add a few invented
# examples in every section (assets + QR, PM, PdM, lubrication, corrective work orders, a request).
#
# KEPT:   organisation, plant, departments, users and passwords, roles, teams and shift set-up, failure codes,
#         workflow settings, KPI definitions, audit log.
# WIPED:  assets, BOMs, meters, PM plans and job plans, condition monitoring points/readings/alerts, lubrication,
#         work orders and requests with their history and attachments, spare parts and stock, shutdowns,
#         production records, budgets, notifications; numbering starts again at 1.
#
#   sudo bash scripts/reset-to-examples.sh WIPE-ALL-DATA      does it (a full backup is taken first)
#   sudo bash scripts/reset-to-examples.sh status             counts only, changes nothing
#   sudo bash scripts/reset-to-examples.sh undo <cmms_….dump>  puts everything back from that backup
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash scripts/reset-to-examples.sh ${1:-status}"; exit 1; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
REAL=(docker compose -f deploy/docker-compose.yml --env-file deploy/.env)
BACKUPS=/opt/cmms-backups

counts() {
  "${REAL[@]}" exec -T db psql -U cmms_owner -d cmms -Atc "
    SELECT 'organisations '||count(*) FROM organizations UNION ALL SELECT 'users         '||count(*) FROM users
    UNION ALL SELECT 'departments   '||count(*) FROM departments UNION ALL SELECT 'assets        '||count(*) FROM assets
    UNION ALL SELECT 'PM plans      '||count(*) FROM pm_plans UNION ALL SELECT 'PdM points    '||count(*) FROM measurement_points
    UNION ALL SELECT 'lube points   '||count(*) FROM lubrication_points UNION ALL SELECT 'work orders   '||count(*) FROM work_orders
    UNION ALL SELECT 'requests      '||count(*) FROM work_requests UNION ALL SELECT 'attachments   '||count(*) FROM attachments"
}

refresh_test_copy() {
  if docker volume inspect papermill-cmms-test_pgdata >/dev/null 2>&1; then
    log "Test copy: replacing its data with a fresh copy of the (now clean) main system"
    bash scripts/test-copy.sh refresh
  else
    echo "No test copy on this server: nothing to refresh."
  fi
}

case "${1:-status}" in
  status) counts ;;
  WIPE-ALL-DATA)
    "${REAL[@]}" ps --status running db api | grep -q api || { echo "The main system is not running; start it first."; exit 1; }
    log "Checking that the examples can be added (dry run, changes nothing)"
    "${REAL[@]}" exec -T -e DRY_RUN=1 api python - < backend/app/plant_examples.py \
      || { echo "The check failed: NOTHING was wiped. Send this output to the developer."; exit 1; }
    log "Before"; counts
    log "Full backup first (database + attachments, also copied off the server if set up)"
    ENV_FILE=deploy/.env bash scripts/backup.sh "$BACKUPS"
    dump="$(ls -t "$BACKUPS"/cmms_*.dump | head -1)"
    log "Wiping the operational data (users and departments are kept)"
    "${REAL[@]}" exec -T db psql -U cmms_owner -d cmms -v ON_ERROR_STOP=1 -q < deploy/sql/wipe-operational-data.sql
    "${REAL[@]}" exec -T api sh -c 'find /app/var/storage -mindepth 1 -delete' || echo "(attachment files could not all be removed)"
    log "Adding the examples"
    "${REAL[@]}" exec -T api python - < backend/app/plant_examples.py
    log "After"; counts
    refresh_test_copy
    log "Done"
    echo "Users sign in as before. To put everything back:"
    echo "  sudo bash scripts/reset-to-examples.sh undo $dump" ;;
  undo)
    dump="${2:-}"; [[ -f "$dump" ]] || { echo "Usage: sudo bash scripts/reset-to-examples.sh undo $BACKUPS/cmms_<time>.dump"; exit 2; }
    tar="${dump/cmms_/storage_}"; tar="${tar%.dump}.tar.gz"
    log "Putting back the data from $dump"
    "${REAL[@]}" stop api worker
    "${REAL[@]}" exec -T db pg_restore -U cmms_owner -d cmms --clean --if-exists --no-acl --exit-on-error < "$dump"
    "${REAL[@]}" up -d --no-build --no-deps api
    if [[ -f "$tar" ]]; then
      "${REAL[@]}" exec -T api sh -c 'find /app/var/storage -mindepth 1 -delete; tar -C /app/var -xzf -' < "$tar"
    fi
    "${REAL[@]}" up -d --no-build --force-recreate migrate api worker   # migrations re-apply the database grants
    log "Restored"; counts
    refresh_test_copy ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
