#!/usr/bin/env bash
# Public demo of PlantPulse at https://demo.<PRODUCT_DOMAIN> (e.g. demo.plantpulse-cmms.com): SAMPLE data only
# (app.cli seed-demo), a blue DEMO label, no e-mail, back to the original sample data every night at 03:00 Riyadh time.
# Its own database, attachments and images; no other installation is read or changed. Visitors get the sign-in details
# by e-mail from the website's "Try the demo" form (scripts/site.sh), so the website must be running first.
#
#   sudo bash scripts/demo.sh start      build it (first time 5-15 minutes), load the sample data, start it
#   sudo bash scripts/demo.sh launch     the same, running on the server by itself (safe from a phone: closing the
#                                         terminal does not stop it); then `progress` shows how far it is
#   sudo bash scripts/demo.sh update     after `sudo git pull`: build the new version for the demo and restart it
#   sudo bash scripts/demo.sh launch-update   the same plus fresh sample data, running on the server by itself
#   sudo bash scripts/demo.sh reset      put the sample data back now (also runs every night by itself)
#   sudo bash scripts/demo.sh accounts   show the demo address, accounts and password
#   sudo bash scripts/demo.sh stop | remove | status | logs
#   (guard: runs every 10 minutes by itself; puts the shared demo password back if a visitor changed it)
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash scripts/demo.sh ${1:-start}"; exit 1; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

REAL=(docker compose -f deploy/docker-compose.yml --env-file deploy/.env)
DENV=deploy/.env.demo
SENV=deploy/.env.site
DEMO=(docker compose -p plantpulse-demo -f deploy/docker-compose.demo.yml --env-file "$DENV")
CRONFILE=/etc/cron.d/plantpulse-demo
DEMO_DOMAIN_ACCOUNTS="manager@demo.example.com planner@demo.example.com tech1@demo.example.com"

getenv() { grep -s "^$1=" "$2" | tail -n1 | cut -d= -f2- || true; }
setenv() {
  local tmp; tmp="$(mktemp)"
  grep -sv "^$1=" "$3" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > "$3"; rm -f "$tmp"
}

domain() {
  local d; d="$(getenv PRODUCT_DOMAIN deploy/.env)"
  [[ -n "$d" ]] || { echo "Start the website first: sudo bash scripts/site.sh"; exit 1; }
  echo "demo.$d"
}

ensure_env() {
  [[ -f "$DENV" ]] && return
  umask 077
  cat > "$DENV" <<ENV
DEMO_OWNER_DB_PASSWORD=$(openssl rand -hex 24)
DEMO_APP_DB_PASSWORD=$(openssl rand -hex 24)
DEMO_PASSWORD=Demo-$(openssl rand -hex 2)-$(( RANDOM % 9000 + 1000 ))
CMMS_INSTANCE_LABEL=DEMO – بيانات تجريبية
ENV
}

build_images() {
  local rev; rev="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  log "Building version ${rev} for the demo (5-15 minutes; nothing else is stopped)"
  docker build --label "cmms.version=${rev}" -t plantpulse-demo-api backend
  docker build --label "cmms.version=${rev}" -t plantpulse-demo-web frontend
  docker image prune -f >/dev/null 2>&1 || true
}

ensure_images() {
  docker image inspect plantpulse-demo-api >/dev/null 2>&1 && docker image inspect plantpulse-demo-web >/dev/null 2>&1 \
    || build_images
}

wait_api() {
  for _ in $(seq 1 90); do
    "${DEMO[@]}" exec -T demo-api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready',timeout=3)" 2>/dev/null && return 0
    sleep 4
  done
  echo "The demo did not become ready; see: sudo bash scripts/demo.sh logs"; return 1
}

seed() {
  log "Loading the sample data"
  "${DEMO[@]}" exec -T -e "CMMS_DEMO_PASSWORD=$(getenv DEMO_PASSWORD "$DENV")" demo-api python -m app.cli seed-demo --profile general
}

# Visitors share the demo accounts: put the password back if someone changed it, and lift any login lock-out.
guard() {
  "${DEMO[@]}" exec -T -e "DEMO_PW=$(getenv DEMO_PASSWORD "$DENV")" demo-api python - <<'PY'
import os
from sqlalchemy import select
from app.core.db import SessionLocal
from app.core.security import hash_password, verify_password
from app.models.identity import User
pw, fixed = os.environ["DEMO_PW"], 0
with SessionLocal() as db, db.begin():
    for u in db.execute(select(User).where(User.email.like("%@demo.example.com"))).scalars():
        try:
            ok = verify_password(u.password_hash, pw)
        except Exception:
            ok = False
        if not ok:
            u.password_hash = hash_password(pw); fixed += 1
        u.failed_login_count = 0
        u.locked_until = None
if fixed:
    print(f"demo guard: password put back for {fixed} account(s)")
PY
}

# The website e-mails these to visitors who fill in "Try the demo".
publish_to_site() {
  [[ -f "$SENV" ]] || { echo "Website not set up yet (sudo bash scripts/site.sh); the demo runs, but no e-mails go out."; return 0; }
  setenv DEMO_URL "https://$(domain)" "$SENV"
  setenv DEMO_PASSWORD "$(getenv DEMO_PASSWORD "$DENV")" "$SENV"
  chmod 600 "$SENV"
  docker compose -p plantpulse-site -f deploy/docker-compose.site.yml --env-file "$SENV" up -d >/dev/null
}

install_cron() {
  # 03:00 in Riyadh (UTC+3) expressed in this server's own time zone.
  local off sign h m hour
  off="$(date +%z)"; sign="${off:0:1}"; h=$((10#${off:1:2})); m=$((10#${off:3:2}))
  [[ "$sign" == "-" ]] && h=$((-h))
  hour=$(( ( (3 - 3 + h) % 24 + 24 ) % 24 ))
  cat > "$CRONFILE" <<CRON
# PlantPulse public demo (scripts/demo.sh): sample data back every night at 03:00 Riyadh time, password guard.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
$m $hour * * * root cd $PWD && bash scripts/demo.sh reset >> /var/log/plantpulse-demo.log 2>&1
*/10 * * * * root cd $PWD && bash scripts/demo.sh guard >> /var/log/plantpulse-demo.log 2>&1
CRON
  chmod 644 "$CRONFILE"
}

accounts() {
  local pw; pw="$(getenv DEMO_PASSWORD "$DENV")"
  echo "Demo:      https://$(domain)"
  echo "Password:  $pw   (the same for every demo account)"
  for a in $DEMO_DOMAIN_ACCOUNTS; do echo "Account:   $a"; done
}

start() {
  "${REAL[@]}" ps --status running caddy | grep -q caddy || { echo "The main system (Caddy) is not running; start it first."; exit 1; }
  docker network inspect papermill-cmms-edge >/dev/null 2>&1 || { echo "Network papermill-cmms-edge missing: update the main system first."; exit 1; }
  domain >/dev/null
  ensure_env
  ensure_images
  local fresh=0
  docker volume inspect plantpulse-demo_pgdata >/dev/null 2>&1 || fresh=1
  log "Starting the demo"
  "${DEMO[@]}" up -d
  wait_api
  if [[ $fresh == 1 ]] || ! "${DEMO[@]}" exec -T demo-db psql -U cmms_owner -d cmms -Atc "SELECT 1 FROM organizations WHERE code='DEMO'" 2>/dev/null | grep -q 1; then
    seed
  fi
  guard
  install_cron
  publish_to_site
  bash scripts/site.sh caddy
  log "Ready"
  accounts
  echo "Every night at 03:00 (Riyadh) the demo goes back to the sample data. Log: /var/log/plantpulse-demo.log"
}

reset() {
  log "Putting the demo back to the sample data ($(date -Is))"
  ensure_env; ensure_images
  "${DEMO[@]}" down -v
  "${DEMO[@]}" up -d
  wait_api
  seed
  guard
  echo "Demo reset done."
}

case "${1:-start}" in
  start) start ;;
  update) ensure_env; build_images; "${DEMO[@]}" up -d; wait_api; guard; echo "Demo updated: https://$(domain)" ;;
  update-reset) ensure_env; build_images; reset; echo "Demo updated and reloaded: https://$(domain)" ;;
  reset) reset ;;
  guard) [[ -f "$DENV" ]] && "${DEMO[@]}" ps --status running demo-api 2>/dev/null | grep -q demo-api && guard || true ;;
  launch|launch-update)
    what=start; [[ "$1" == launch-update ]] && what=update-reset
    systemctl reset-failed plantpulse-demo-setup >/dev/null 2>&1 || true
    systemd-run --unit=plantpulse-demo-setup --collect --quiet bash "$PWD/scripts/demo.sh" "$what"
    echo "Started on the server ($what). It goes on even if you close this window (5-15 minutes)."
    echo "See how far it is:  sudo bash $PWD/scripts/demo.sh progress" ;;
  progress)
    if systemctl is-active --quiet plantpulse-demo-setup; then echo "STILL RUNNING – last lines:"; else echo "FINISHED – last lines:"; fi
    journalctl -u plantpulse-demo-setup --no-pager -n 25 -o cat 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' ;;
  accounts) accounts ;;
  stop) "${DEMO[@]}" stop; rm -f "$CRONFILE"; echo "Demo stopped (data kept; start brings it back)." ;;
  remove)
    "${DEMO[@]}" down -v; rm -f "$CRONFILE"
    if [[ -f "$SENV" ]]; then
      sed -i '/^DEMO_URL=/d;/^DEMO_PASSWORD=/d' "$SENV"
      docker compose -p plantpulse-site -f deploy/docker-compose.site.yml --env-file "$SENV" up -d >/dev/null
    fi
    echo "Demo and its data removed. The website's \"Try the demo\" form now says the demo is not available." ;;
  status) "${DEMO[@]}" ps; docker image inspect -f 'Version: {{index .Config.Labels "cmms.version"}}  built {{.Created}}' plantpulse-demo-api 2>/dev/null || true ;;
  logs) "${DEMO[@]}" logs --tail 80 ;;
  *) echo "Usage: sudo bash scripts/demo.sh start|launch|progress|update|launch-update|reset|accounts|stop|remove|status|logs"; exit 2 ;;
esac
