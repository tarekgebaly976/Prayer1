#!/usr/bin/env bash
# One PlantPulse per customer, on this server: https://<name>.<PRODUCT_DOMAIN> (e.g. acme.plantpulse-cmms.com) with its
# own database, attachments, settings and users. Customers never share data with each other, the demo or any other
# installation on the server. All customers run the same version (images plantpulse-app-api / -web).
#
#   sudo bash scripts/customer.sh new <name> <admin-email> ["Company name"] [options]
#        options: --plant "Plant name"  --plant-code CODE  --departments general|paper|none
#                 --currency SAR  --timezone Asia/Riyadh  --lang ar|en (welcome e-mail, default ar)
#                 --no-welcome (no e-mail to the administrator)  --no-mail (the system sends no e-mail at all)
#        e.g.     sudo bash scripts/customer.sh new acme it@acme.com "Acme Paper Co" --departments paper
#   sudo bash scripts/customer.sh list
#   sudo bash scripts/customer.sh show <name>               address, admin e-mail and first password
#   sudo bash scripts/customer.sh welcome <name> [--lang en]   send the welcome e-mail (again) to the administrator
#   sudo bash scripts/customer.sh reset-password <name> <e-mail>   new random password for that user
#   sudo bash scripts/customer.sh backup <name>             now; all customers are also backed up every night
#   sudo bash scripts/customer.sh restore <name> <file.dump>
#   sudo bash scripts/customer.sh update <name>             restart that customer on the current version
#   sudo bash scripts/customer.sh launch-update-all         after `sudo git pull`: build the new version and move
#                                                           every customer to it, on the server by itself; then
#   sudo bash scripts/customer.sh progress
#   sudo bash scripts/customer.sh mail-sync                 after changing the website's mail sender (site.sh resend):
#                                                           give every customer the same settings
#   sudo bash scripts/customer.sh stop <name> | start <name> | logs <name>
#   sudo bash scripts/customer.sh remove <name>             final backup, then deletes that customer
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash scripts/customer.sh ${1:-list}"; exit 1; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

REAL=(docker compose -f deploy/docker-compose.yml --env-file deploy/.env)
CDIR=deploy/customers
BACKUPS=/opt/plantpulse-backups
CRONFILE=/etc/cron.d/plantpulse-customers
RESERVED=" www demo test api app admin mail smtp send rsend resend status docs blog help support www2 dev staging "

getenv() { grep -s "^$1=" "$2" | tail -n1 | cut -d= -f2- || true; }
domain() {
  local d; d="$(getenv PRODUCT_DOMAIN deploy/.env)"
  [[ -n "$d" ]] || { echo "Set up the website first: sudo bash scripts/site.sh"; exit 1; }
  echo "$d"
}
cenv() { echo "$CDIR/$1.env"; }
C() { docker compose -p "plantpulse-c-$1" -f deploy/docker-compose.customer.yml --env-file "$(cenv "$1")" "${@:2}"; }
exists() { [[ -f "$(cenv "$1")" ]]; }
need() { exists "$1" || { echo "No customer called '$1'. See: sudo bash scripts/customer.sh list"; exit 1; }; }

valid_name() {
  local n="$1"
  [[ "$n" =~ ^[a-z][a-z0-9-]{0,28}[a-z0-9]$ ]] || { echo "Name must be 2-30 characters: lowercase letters, digits and -, e.g. acme or al-safi"; exit 2; }
  [[ "$RESERVED" != *" $n "* ]] || { echo "'$n' is reserved; choose another name."; exit 2; }
}

wait_api() {
  for _ in $(seq 1 90); do
    C "$1" exec -T api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready',timeout=3)" 2>/dev/null && return 0
    sleep 4
  done
  echo "$1 did not become ready; see: sudo bash scripts/customer.sh logs $1"; return 1
}

build_images() {
  local rev; rev="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  log "Building version ${rev} for the customers (5-15 minutes; everything keeps running)"
  docker build --label "cmms.version=${rev}" -t plantpulse-app-api backend
  docker build --label "cmms.version=${rev}" -t plantpulse-app-web frontend
  docker image prune -f >/dev/null 2>&1 || true
}

ensure_images() {
  docker image inspect plantpulse-app-api >/dev/null 2>&1 && docker image inspect plantpulse-app-web >/dev/null 2>&1 && return
  if docker image inspect plantpulse-demo-api >/dev/null 2>&1 && docker image inspect plantpulse-demo-web >/dev/null 2>&1; then
    log "Using the demo's version for the customers (no build needed)"
    docker tag plantpulse-demo-api plantpulse-app-api
    docker tag plantpulse-demo-web plantpulse-app-web
  else
    build_images
  fi
}

version() { docker image inspect -f '{{index .Config.Labels "cmms.version"}}' plantpulse-app-api 2>/dev/null || echo -; }

new_password() { echo "Pp-$(openssl rand -hex 5)-$(openssl rand -hex 3 | tr 'a-f' 'A-F')"; }

install_cron() {
  # Every night at 02:45 Riyadh time (UTC+3), in this server's own time zone.
  local off sign h m hour
  off="$(date +%z)"; sign="${off:0:1}"; h=$((10#${off:1:2})); m=$((10#${off:3:2}))
  [[ "$sign" == "-" ]] && h=$((-h))
  hour=$(( ( (2 - 3 + h) % 24 + 24 ) % 24 ))
  cat > "$CRONFILE" <<CRON
# PlantPulse customers (scripts/customer.sh): nightly backups, kept 14 days in $BACKUPS
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
$(( (45 + m) % 60 )) $hour * * * root cd $PWD && bash scripts/customer.sh backup-all >> /var/log/plantpulse-customers.log 2>&1
CRON
  chmod 644 "$CRONFILE"
}

caddy_add() {  # caddy_add <name>: route <name>.<domain> to the customer, checked before Caddy is touched
  printf '%s.%s {\n\timport customer %s\n}\n' "$1" "$(domain)" "$1" > "deploy/caddy.d/c-$1.caddy"
  if ! bash scripts/site.sh caddy-reload; then
    rm -f "deploy/caddy.d/c-$1.caddy"
    echo "Caddy was not changed. The customer's containers run, but the address is not served yet."; return 1
  fi
}

new() {
  local name="${1:-}" email="${2:-}" org="" plant="Main plant" pcode="MAIN" depts="general" cur="SAR" tz="Asia/Riyadh" mail=1
  local lang=ar welcome_mail=1
  [[ -n "$name" && "$email" == *@* ]] || { sed -n '6,10p' "$0"; exit 2; }
  shift 2
  # Company and plant names may be several words without quotes (quotes get lost through ssh): every word up to
  # the next --option belongs to the name.
  while [[ $# -gt 0 && "$1" != --* ]]; do org="${org:+$org }$1"; shift; done
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --plant) plant=""; shift; while [[ $# -gt 0 && "$1" != --* ]]; do plant="${plant:+$plant }$1"; shift; done ;;
      --plant-code) pcode="$2"; shift 2 ;;
      --departments) depts="$2"; shift 2 ;;
      --currency) cur="$2"; shift 2 ;;
      --timezone) tz="$2"; shift 2 ;;
      --no-mail) mail=0; welcome_mail=0; shift ;;
      --no-welcome) welcome_mail=0; shift ;;
      --lang) lang="$2"; shift 2 ;;
      *) echo "Unknown option $1"; exit 2 ;;
    esac
  done
  valid_name "$name"
  exists "$name" && { echo "Customer '$name' already exists: https://$name.$(domain)"; exit 1; }
  [[ "$depts" =~ ^(general|paper|none)$ ]] || { echo "--departments must be general, paper or none"; exit 2; }
  org="${org:-$name}"
  local dom; dom="$(domain)"
  "${REAL[@]}" ps --status running caddy | grep -q caddy || { echo "The main system (Caddy) is not running."; exit 1; }
  local avail; avail=$(free -m | awk '/^Mem:/{print $7}')
  if (( avail < 1200 )); then
    echo "Only ${avail} MB of memory available; a customer needs about 600 MB plus room for updates."
    echo "Free memory first (e.g. sudo bash scripts/test-copy.sh stop) or make the server bigger."; exit 1
  fi

  log "Creating customer $name ($org) at https://$name.$dom"
  mkdir -p "$CDIR"; chmod 700 "$CDIR"
  local pw; pw="$(new_password)"
  umask 077
  {
    echo "CUSTOMER=$name"
    echo "CUSTOMER_DOMAIN=$name.$dom"
    echo "ORG_NAME=$org"
    echo "ADMIN_EMAIL=$email"
    echo "INITIAL_ADMIN_PASSWORD=$pw"
    echo "CREATED=$(date -Is)"
    echo "WELCOME_LANG=$lang"
    echo "OWNER_DB_PASSWORD=$(openssl rand -hex 24)"
    echo "APP_DB_PASSWORD=$(openssl rand -hex 24)"
    if [[ $mail == 1 && -n "$(getenv SITE_SMTP_HOST deploy/.env.site)" ]]; then  # same sender as the website
      echo "SMTP_HOST=$(getenv SITE_SMTP_HOST deploy/.env.site)"
      echo "SMTP_PORT=$(getenv SITE_SMTP_PORT deploy/.env.site)"
      echo "SMTP_USER=$(getenv SITE_SMTP_USER deploy/.env.site)"
      echo "SMTP_PASSWORD=$(getenv SITE_SMTP_PASSWORD deploy/.env.site)"
      echo "SMTP_FROM=$(getenv SITE_SMTP_FROM deploy/.env.site)"
    fi
  } > "$(cenv "$name")"
  ensure_images
  C "$name" up -d
  wait_api "$name"
  log "Creating the organisation, plant and first administrator"
  local code; code="$(echo "$name" | tr -d '-' | tr 'a-z' 'A-Z' | cut -c1-32)"
  C "$name" exec -T -e "CMMS_ADMIN_PASSWORD=$pw" api python -m app.cli bootstrap --org-code "$code" --org-name "$org" \
    --plant-code "$pcode" --plant-name "$plant" --admin-email "$email" --timezone "$tz" --currency "$cur" --departments "$depts"
  log "Publishing https://$name.$dom"
  caddy_add "$name" || true
  install_cron
  if [[ $welcome_mail == 1 ]]; then log "Welcome e-mail to $email"; welcome "$name" || true; fi
  log "Ready"
  show "$name"
  echo "The certificate for the address is issued on first use; the first page load can take ~20 seconds."
  echo "The administrator should change the password after signing in (profile menu > Change password)."
}

# welcome <name> [en|ar]: e-mail the administrator the address and first password, through the website's mail sender.
welcome() {
  need "$1"; local f; f="$(cenv "$1")"
  local lang="${2:-$(getenv WELCOME_LANG "$f")}"
  W_NAME="$1" W_EMAIL="$(getenv ADMIN_EMAIL "$f")" W_COMPANY="$(getenv ORG_NAME "$f")" W_URL="https://$(getenv CUSTOMER_DOMAIN "$f")" \
  W_PW="$(getenv INITIAL_ADMIN_PASSWORD "$f")" W_LANG="${lang:-ar}" python3 -c '
import json, os
print(json.dumps({"name": os.environ["W_NAME"], "email": os.environ["W_EMAIL"], "company": os.environ["W_COMPANY"],
                  "url": os.environ["W_URL"], "password": os.environ["W_PW"], "lang": os.environ["W_LANG"]}))' \
  | docker compose -p plantpulse-site -f deploy/docker-compose.site.yml --env-file deploy/.env.site exec -T site python /app/server.py welcome \
  || { echo "Welcome e-mail not sent (website mail not set up?). Send the details above yourself."; return 1; }
}

show() {
  need "$1"; local f; f="$(cenv "$1")"
  echo "Customer:   $1  ($(getenv ORG_NAME "$f"))"
  echo "Address:    https://$(getenv CUSTOMER_DOMAIN "$f")"
  echo "Admin:      $(getenv ADMIN_EMAIL "$f")"
  echo "Password:   $(getenv INITIAL_ADMIN_PASSWORD "$f")   (first password; useless once changed)"
  echo "Created:    $(getenv CREATED "$f")"
  echo "E-mail:     $([[ -n "$(getenv SMTP_HOST "$f")" ]] && echo "on, from $(getenv SMTP_FROM "$f")" || echo off)"
}

list() {
  shopt -s nullglob
  local files=("$CDIR"/*.env) n run
  echo "Version on the server: $(version)    Memory available: $(free -m | awk '/^Mem:/{print $7}') MB"
  [[ ${#files[@]} -gt 0 ]] || { echo "No customers yet. Create one: sudo bash scripts/customer.sh new <name> <admin-email> \"Company\""; return; }
  printf '%-16s %-38s %-8s %s\n' NAME ADDRESS RUNNING COMPANY
  for f in "${files[@]}"; do
    n="$(basename "$f" .env)"
    run="$(C "$n" ps --status running -q 2>/dev/null | wc -l)"
    printf '%-16s %-38s %-8s %s\n' "$n" "https://$(getenv CUSTOMER_DOMAIN "$f")" "$run/4" "$(getenv ORG_NAME "$f")"
  done
}

backup() {
  need "$1"; local dir="$BACKUPS/$1" stamp; stamp="$(date +%F-%H%M)"
  mkdir -p "$dir"; chmod 700 "$BACKUPS" "$dir"
  C "$1" exec -T db pg_dump -U cmms_owner -d cmms -Fc > "$dir/$stamp.dump"
  docker run --rm -v "plantpulse-c-$1_storage:/s:ro" --entrypoint sh postgres:16.10-alpine -c 'tar czf - -C /s .' > "$dir/$stamp.storage.tgz"
  find "$dir" -type f -mtime +14 -delete
  echo "$1: backup $dir/$stamp.dump ($(du -h "$dir/$stamp.dump" | cut -f1)), attachments $(du -h "$dir/$stamp.storage.tgz" | cut -f1)"
}

restore() {
  local name="${1:-}" file="${2:-}"
  need "$name"; [[ -f "$file" ]] || { echo "Backup file not found: $file  (see ls $BACKUPS/$name)"; exit 1; }
  if [[ "${3:-}" != --yes ]]; then
    [[ -t 0 ]] || { echo "Add --yes to confirm (this replaces all of $name's current data)."; exit 1; }
    read -rp "This REPLACES all current data of $name with $file. Type the name to confirm: " ok
    [[ "$ok" == "$name" ]] || { echo "Cancelled."; exit 1; }
  fi
  log "Safety backup of the current data first"; backup "$name"
  log "Restoring $name from $file"
  C "$name" stop api worker web
  C "$name" exec -T db pg_restore -U cmms_owner -d cmms --clean --if-exists --no-owner --role=cmms_owner < "$file"
  local tgz="${file%.dump}.storage.tgz"
  if [[ -f "$tgz" ]]; then
    docker run --rm -i -v "plantpulse-c-${name}_storage:/s" --entrypoint sh postgres:16.10-alpine -c 'rm -rf /s/* && tar xzf - -C /s' < "$tgz"
  fi
  C "$name" up -d --force-recreate; wait_api "$name"
  echo "$name restored from $file."
}

update_one() {
  need "$1"; log "Moving $1 to version $(version)"
  C "$1" up -d --force-recreate; wait_api "$1"
}

remove() {
  local name="${1:-}"; need "$name"
  if [[ "${2:-}" != --yes ]]; then
    [[ -t 0 ]] || { echo "Add --yes to confirm."; exit 1; }
    read -rp "This DELETES customer $name and all its data (a final backup is kept). Type the name to confirm: " ok
    [[ "$ok" == "$name" ]] || { echo "Cancelled."; exit 1; }
  fi
  log "Final backup"; backup "$name"
  rm -f "deploy/caddy.d/c-$name.caddy"; bash scripts/site.sh caddy-reload || true
  C "$name" down -v
  mv "$(cenv "$name")" "$BACKUPS/$name/settings-removed-$(date +%F).env"
  echo "Customer $name removed. Its last backup and settings are in $BACKUPS/$name"
}

mail_sync() {  # copy the website's mail sender (deploy/.env.site) to one customer and restart its app if it changed
  need "$1"; local f before after k; f="$(cenv "$1")"
  [[ -n "$(getenv SMTP_HOST "$f")" ]] || { echo "$1: e-mail is off (--no-mail), left as is."; return 0; }
  before="$(grep '^SMTP_' "$f" | sort)"
  for k in HOST PORT USER PASSWORD FROM; do
    sed -i "/^SMTP_$k=/d" "$f"; echo "SMTP_$k=$(getenv "SITE_SMTP_$k" deploy/.env.site)" >> "$f"
  done
  after="$(grep '^SMTP_' "$f" | sort)"
  if [[ "$before" != "$after" ]]; then C "$1" up -d api worker >/dev/null 2>&1; echo "$1: mail settings updated."; else echo "$1: already up to date."; fi
}

each() {  # each <function>: run for every customer, continue on errors
  shopt -s nullglob; local f rc=0
  for f in "$CDIR"/*.env; do "$1" "$(basename "$f" .env)" || rc=1; done
  return $rc
}

case "${1:-list}" in
  new) shift; new "$@" ;;
  list) list ;;
  show) show "${2:-}" ;;
  welcome) l=""; [[ "${3:-}" == --lang ]] && l="${4:-}"; welcome "${2:-}" "$l" ;;
  reset-password)
    need "${2:-}"; [[ "${3:-}" == *@* ]] || { echo "Usage: sudo bash scripts/customer.sh reset-password <name> <e-mail>"; exit 2; }
    pw="$(new_password)"
    C "$2" exec -T -e "CMMS_NEW_PASSWORD=$pw" api python -m app.cli reset-password --email "$3"
    echo "New password for $3 at https://$(getenv CUSTOMER_DOMAIN "$(cenv "$2")"):  $pw" ;;
  backup) backup "${2:-}" ;;
  mail-sync) [[ -n "$(getenv SITE_SMTP_HOST deploy/.env.site)" ]] || { echo "The website has no mail sender set."; exit 1; }; each mail_sync ;;
  backup-all) echo "== $(date -Is)"; each backup ;;
  restore) restore "${2:-}" "${3:-}" "${4:-}" ;;
  remove) remove "${2:-}" "${3:-}" ;;
  update) update_one "${2:-}" ;;
  build) build_images ;;
  update-all) build_images; each update_one; echo "All customers on version $(version)." ;;
  launch-update-all)
    systemctl reset-failed plantpulse-customers-update >/dev/null 2>&1 || true
    systemd-run --unit=plantpulse-customers-update --collect --quiet bash "$PWD/scripts/customer.sh" update-all
    echo "Started on the server: building the new version and moving every customer to it (5-15 minutes)."
    echo "See how far it is:  sudo bash $PWD/scripts/customer.sh progress" ;;
  progress)
    if systemctl is-active --quiet plantpulse-customers-update; then echo "STILL RUNNING – last lines:"; else echo "FINISHED – last lines:"; fi
    journalctl -u plantpulse-customers-update --no-pager -n 25 -o cat 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' ;;
  stop) need "${2:-}"; C "$2" stop; echo "$2 stopped (data kept)." ;;
  start) need "${2:-}"; C "$2" up -d; wait_api "$2"; echo "$2 running: https://$(getenv CUSTOMER_DOMAIN "$(cenv "$2")")" ;;
  logs) need "${2:-}"; C "$2" logs --tail 60 ;;
  *) sed -n '2,25p' "$0"; exit 2 ;;
esac
