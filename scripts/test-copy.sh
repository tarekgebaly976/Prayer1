#!/usr/bin/env bash
# Test copy of the CMMS on the same server, at https://test.<domain>: a separate database and attachment store,
# filled with a copy of the real data, a red "TEST" label on every page, and no e-mail. Nothing done in the test
# copy reaches the real system. The real system is only read (pg_dump), never stopped or changed.
#
#   sudo bash scripts/test-copy.sh start     create it from the real data (or start it again if it exists)
#   sudo bash scripts/test-copy.sh update    try a NEW VERSION in the test copy only: builds the code now in this
#                                            folder (after `sudo git pull`) for the test copy; the real system keeps
#                                            running its version until deploy/install-server.sh is run
#   sudo bash scripts/test-copy.sh same-as-real   put the test copy back on the real system's version
#   sudo bash scripts/test-copy.sh refresh   throw the test data away and copy the real data again
#   sudo bash scripts/test-copy.sh stop      stop it (keeps its data; start brings it back)
#   sudo bash scripts/test-copy.sh remove    stop it and delete its data
#   sudo bash scripts/test-copy.sh status
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash scripts/test-copy.sh ${1:-start}"; exit 1; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

REAL=(docker compose -f deploy/docker-compose.yml --env-file deploy/.env)
TENV=deploy/.env.test
TEST=(docker compose -p papermill-cmms-test -f deploy/docker-compose.test.yml --env-file "$TENV")
DOMAIN="$(grep -s '^CMMS_DOMAIN=' deploy/.env | cut -d= -f2)"

ensure_env() {
  [[ -f "$TENV" ]] && return
  umask 077
  cat > "$TENV" <<ENV
CMMS_TEST_OWNER_DB_PASSWORD=$(openssl rand -hex 24)
CMMS_TEST_APP_DB_PASSWORD=$(openssl rand -hex 24)
CMMS_INSTANCE_LABEL=TEST – نسخة تجربة
ENV
}

copy_real_data() {
  log "Copying the real database into the test copy (the real system keeps running)"
  "${TEST[@]}" up --no-start
  "${TEST[@]}" up -d --wait test-db
  "${REAL[@]}" exec -T db pg_dump -U cmms_owner -d cmms -Fc \
    | "${TEST[@]}" exec -T test-db pg_restore -U cmms_owner -d cmms --exit-on-error
  # Log nobody in from the copy, and drop integration tokens so no plant system can write here by mistake.
  "${TEST[@]}" exec -T test-db psql -U cmms_owner -d cmms -qc "DELETE FROM user_sessions; DELETE FROM integration_tokens;" >/dev/null
  log "Copying attachments"
  docker run --rm -v papermill-cmms_storage:/from:ro -v papermill-cmms-test_storage:/to --entrypoint sh postgres:16.10-alpine \
    -c 'cp -a /from/. /to/ 2>/dev/null || true'
}

# The test copy runs its own images. Until `update` builds a newer version they are the real system's images.
same_as_real_images() {
  docker tag papermill-cmms-api papermill-cmms-test-api
  docker tag papermill-cmms-web papermill-cmms-test-web
}

ensure_images() {
  docker image inspect papermill-cmms-test-api >/dev/null 2>&1 && docker image inspect papermill-cmms-test-web >/dev/null 2>&1 \
    || same_as_real_images
}

build_test_images() {
  local rev; rev="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  log "Building version ${rev} for the test copy only (the real system keeps running its version; takes 5-15 minutes)"
  docker build --label "cmms.version=${rev}" -t papermill-cmms-test-api backend
  docker build --label "cmms.version=${rev}" -t papermill-cmms-test-web frontend
  docker image prune -f >/dev/null 2>&1 || true
}

versions() {
  local real test
  real="$(docker image inspect -f '{{index .Config.Labels "cmms.version"}} {{.Created}}' papermill-cmms-api 2>/dev/null || echo '-')"
  test="$(docker image inspect -f '{{index .Config.Labels "cmms.version"}} {{.Created}}' papermill-cmms-test-api 2>/dev/null || echo '-')"
  echo "Real system version: ${real:0:40}"
  echo "Test copy version:   ${test:0:40}"
}

start() {
  "${REAL[@]}" ps --status running db | grep -q db || { echo "The real system is not running; start it first."; exit 1; }
  docker network inspect papermill-cmms-edge >/dev/null 2>&1 || {
    echo "Update the real system first (it adds the connection the test copy needs):"
    echo "  cd /opt/cmms && sudo git pull && sudo bash deploy/install-server.sh"; exit 1; }
  ensure_env
  ensure_images
  if ! docker volume inspect papermill-cmms-test_pgdata >/dev/null 2>&1; then
    copy_real_data
  fi
  log "Starting the test copy"
  "${TEST[@]}" up -d
  for _ in $(seq 1 60); do
    "${TEST[@]}" exec -T test-api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready',timeout=3)" 2>/dev/null && break
    sleep 5
  done
  log "Ready"
  versions
  echo "Test copy:  https://test.${DOMAIN}   (same users and passwords as the real system on the day it was copied)"
  echo "Real system unchanged:  https://${DOMAIN}"
}

case "${1:-start}" in
  start) start ;;
  update) build_test_images; start
    echo "When the new version is good: cd /opt/cmms && sudo bash deploy/install-server.sh  (updates the real system)" ;;
  same-as-real) same_as_real_images; start ;;
  refresh)
    log "Deleting the test copy's data"
    "${TEST[@]}" down -v 2>/dev/null || true
    start ;;
  stop) "${TEST[@]}" stop; echo "Test copy stopped (data kept)." ;;
  remove) "${TEST[@]}" down -v; echo "Test copy and its data removed. The real system is untouched." ;;
  status) "${TEST[@]}" ps; versions ;;
  *) echo "Usage: sudo bash scripts/test-copy.sh start|update|same-as-real|refresh|stop|remove|status"; exit 2 ;;
esac
