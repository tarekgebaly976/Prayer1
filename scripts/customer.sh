#!/usr/bin/env bash
# One PlantPulse per customer, on this server: https://<name>.<PRODUCT_DOMAIN> (e.g. acme.plantpulse-cmms.com) with its
# own database, attachments, settings and users. Customers never share data with each other, the demo or any other
# installation on the server. All customers run the same version (images plantpulse-app-api / -web).
#
#   sudo bash scripts/customer.sh new <name> <admin-email> ["Company name"] [options]
#        options: --plant "Plant name"  --plant-code CODE  --departments general|paper|none
#                 --currency SAR  --timezone Asia/Riyadh  --lang ar|en (welcome e-mail, default ar)
#                 --no-mail (the system sends no e-mail at all)  --trial 30 (a 30-day trial)
#        Nothing is e-mailed to the customer yet: check the system, then send the welcome e-mail yourself (below).
#        e.g.     sudo bash scripts/customer.sh new acme it@acme.com "Acme Paper Co" --departments paper
#   sudo bash scripts/customer.sh list
#   sudo bash scripts/customer.sh show <name>               address, admin e-mail and first password
#   sudo bash scripts/customer.sh welcome <name> --preview  show the welcome e-mail, send nothing
#   sudo bash scripts/customer.sh welcome <name>            after your check: send it to the administrator
#                                                           (add --lang en / --lang ar to change the language)
#   sudo bash scripts/customer.sh reset-password <name> <e-mail>   new random password for that user
#   sudo bash scripts/customer.sh backup <name>             now; all customers are also backed up every night
#   sudo bash scripts/customer.sh restore <name> <file.dump>
#   sudo bash scripts/customer.sh update <name>             restart that customer on the current version
#   sudo bash scripts/customer.sh launch-update-all         after `sudo git pull`: build the new version and move
#                                                           every customer to it, on the server by itself; then
#   sudo bash scripts/customer.sh progress
#   sudo bash scripts/customer.sh mail-sync                 after changing the website's mail sender (site.sh resend):
#                                                           give every customer the same settings
#   sudo bash scripts/customer.sh stop <name>               pause: the customer sees a "paused" page, data kept
#   sudo bash scripts/customer.sh start <name>              back on
#   sudo bash scripts/customer.sh extend <name> <days>      longer trial (also restarts a paused trial)
#   sudo bash scripts/customer.sh activate <name>           paid: no trial end any more
#   sudo bash scripts/customer.sh remind <name> --preview   reminder e-mail to the customer (trial ending), not sent
#   sudo bash scripts/customer.sh remind <name>             after your check: send it
#   Trials: you get an e-mail 7 days and 1 day before the end and on the day; nothing stops by itself.
#   sudo bash scripts/customer.sh logs <name>
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
# PlantPulse customers (scripts/customer.sh): nightly backups (kept 14 days in $BACKUPS), daily trial reminders 09:05 Riyadh
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
$(( (45 + m) % 60 )) $hour * * * root cd $PWD && bash scripts/customer.sh backup-all >> /var/log/plantpulse-customers.log 2>&1
$(( (5 + m) % 60 )) $(( ( (9 - 3 + h) % 24 + 24 ) % 24 )) * * * root cd $PWD && bash scripts/customer.sh trial-check >> /var/log/plantpulse-customers.log 2>&1
CRON
  chmod 644 "$CRONFILE"
}

caddy_set() {  # caddy_set <name> customer|paused: route <name>.<domain>, checked before Caddy is touched
  local f="deploy/caddy.d/c-$1.caddy" old=""
  [[ -f "$f" ]] && old="$(cat "$f")"
  printf '%s.%s {\n\timport %s %s\n}\n' "$1" "$(domain)" "$2" "$1" > "$f"
  if ! bash scripts/site.sh caddy-reload; then
    if [[ -n "$old" ]]; then printf '%s\n' "$old" > "$f"; else rm -f "$f"; fi
    echo "Caddy was not changed."; return 1
  fi
}
caddy_add() { caddy_set "$1" customer || { echo "The customer's containers run, but the address is not served yet."; return 1; }; }

today() { TZ=Asia/Riyadh date +%F; }
days_left() { echo $(( ( $(date -d "$1" +%s) - $(date -d "$(today)" +%s) ) / 86400 )); }

setval() {  # setval <file> KEY VALUE
  sed -i "/^$2=/d" "$1"; echo "$2=$3" >> "$1"
}

# E-mail through the website's sender; JSON built here so names and dates need no quoting.
send_mail_json() {  # send_mail_json <to or ""> <to-name> <subject> <preview 0|1>  (body lines on stdin)
  M_TO="$1" M_NAME="$2" M_SUBJECT="$3" M_PREVIEW="$4" python3 -c '
import json, os, sys
print(json.dumps({"to": os.environ["M_TO"], "to_name": os.environ["M_NAME"], "subject": os.environ["M_SUBJECT"],
                  "body": sys.stdin.read().rstrip("\n").split("\n"), "preview": os.environ["M_PREVIEW"] == "1"}))' \
  | docker compose -p plantpulse-site -f deploy/docker-compose.site.yml --env-file deploy/.env.site exec -T site python /app/server.py mail
}

plan_text() {  # one-line plan for list/show
  local f; f="$(cenv "$1")"
  if [[ "$(getenv PLAN "$f")" == trial ]]; then
    local u d; u="$(getenv TRIAL_UNTIL "$f")"; d="$(days_left "$u")"
    if (( d < 0 )); then echo "trial ENDED $u"; elif (( d == 0 )); then echo "trial ends TODAY"; else echo "trial to $u (${d}d)"; fi
  else
    echo "active"
  fi
}

pause() {
  need "$1"
  log "Pausing $1: the address shows a 'paused' page; all data is kept"
  caddy_set "$1" paused || true
  C "$1" stop
  setval "$(cenv "$1")" STATUS paused
  echo "$1 paused. Back on with: sudo bash scripts/customer.sh start $1"
}

resume() {
  need "$1"
  C "$1" up -d; wait_api "$1"
  caddy_set "$1" customer || true
  setval "$(cenv "$1")" STATUS running
  echo "$1 running: https://$(getenv CUSTOMER_DOMAIN "$(cenv "$1")")"
}

# remind <name> [lang] [preview]: tell the customer's administrator that the trial ends (only when you run it)
remind() {
  need "$1"; local f; f="$(cenv "$1")"
  [[ "$(getenv PLAN "$f")" == trial ]] || { echo "$1 is not on a trial."; return 1; }
  local lang="${2:-$(getenv WELCOME_LANG "$f")}" pv="${3:-0}" u d co url
  u="$(getenv TRIAL_UNTIL "$f")"; d="$(days_left "$u")"; co="$(getenv ORG_NAME "$f")"; url="https://$(getenv CUSTOMER_DOMAIN "$f")"
  if [[ "${lang:-ar}" == ar ]]; then
    local when
    if (( d > 10 )); then when="بعد $d يوماً"; elif (( d > 2 )); then when="بعد $d أيام"; elif (( d == 2 )); then when="بعد يومين"
    elif (( d == 1 )); then when="غداً"; else when="اليوم"; fi
    { echo "مرحباً،"; echo
      if (( d >= 0 )); then echo "نود تذكيركم بأن فترة تجربة نظام PlantPulse الخاص بـ $co تنتهي $when ($u)."
      else echo "انتهت فترة تجربة نظام PlantPulse الخاص بـ $co يوم $u."; fi
      echo "  العنوان: $url"; echo
      echo "بياناتكم وكل ما أدخلتموه محفوظ بالكامل."
      echo "للاستمرار بدون انقطاع، فقط رد على هذا الإيميل وسنتواصل معكم لترتيب الاشتراك."
      echo "وإذا احتجتم وقتاً إضافياً للتجربة، أخبرونا."; echo
      echo "PlantPulse – إدارة الصيانة للمنشآت الصناعية"
    } | send_mail_json "$(getenv ADMIN_EMAIL "$f")" "$co" "تجربة PlantPulse لـ $co: تنتهي $u" "$pv"
  else
    local when; if (( d > 1 )); then when="in $d days"; elif (( d == 1 )); then when="tomorrow"; elif (( d == 0 )); then when="today"; else when="on"; fi
    { echo "Hello,"; echo
      if (( d >= 0 )); then echo "A reminder that the PlantPulse trial for $co ends $when ($u)."
      else echo "The PlantPulse trial for $co ended on $u."; fi
      echo "  Address: $url"; echo
      echo "Your data and everything you have entered is kept."
      echo "To continue without interruption, just reply to this e-mail and we will arrange the subscription."
      echo "Need more time to try it? Let us know."; echo
      echo "PlantPulse – maintenance management for industrial plants"
    } | send_mail_json "$(getenv ADMIN_EMAIL "$f")" "$co" "Your PlantPulse trial for $co ends $u" "$pv"
  fi
  if [[ "$pv" == 1 ]]; then echo "Nothing was sent. To send it: sudo bash scripts/customer.sh remind $1${2:+ --lang $2}"
  else setval "$f" CUSTOMER_REMINDED "$(date -Is)"; fi
}

# Daily (cron): e-mail YOU when a trial ends in 7 days, 1 day, today, or ended (then weekly). Nothing is stopped.
trial_check() {
  local f n u d co last
  shopt -s nullglob
  for f in "$CDIR"/*.env; do
    n="$(basename "$f" .env)"
    [[ "$(getenv PLAN "$f")" == trial ]] || continue
    u="$(getenv TRIAL_UNTIL "$f")"; d="$(days_left "$u")"; co="$(getenv ORG_NAME "$f")"
    [[ $d == 7 || $d == 1 || $d == 0 || ( $d -lt 0 && $(( (-d) % 7 )) == 0 ) ]] || continue
    last="$(getenv OWNER_REMINDED "$f")"; [[ "$last" == "$(today)" ]] && continue
    local s; if (( d > 0 )); then s="ends in $d day(s)"; elif (( d == 0 )); then s="ends TODAY"; else s="ENDED $(( -d )) day(s) ago"; fi
    { echo "Trial of $co ($n) $s: $u"
      echo "Address: https://$(getenv CUSTOMER_DOMAIN "$f")   Status: $(getenv STATUS "$f" | sed 's/^$/running/')"
      echo; echo "Nothing has been stopped. Your choice (in Cloud Shell):"; echo
      echo "  Paid, keep it on:"; echo "    ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh activate $n"
      echo "  Longer trial (e.g. 14 days):"; echo "    ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh extend $n 14"
      echo "  Pause it (customer sees a 'paused' page, data kept):"; echo "    ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh stop $n"
      echo "  Remind the customer (look first, then send):"
      echo "    ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remind $n --preview"
      echo "    ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remind $n"
    } | send_mail_json "" "" "PlantPulse: trial of $co $s ($u)" 0 && setval "$f" OWNER_REMINDED "$(today)"
  done
}

new() {
  local name="${1:-}" email="${2:-}" org="" plant="Main plant" pcode="MAIN" depts="general" cur="SAR" tz="Asia/Riyadh" mail=1
  local lang=ar trial=0
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
      --no-mail) mail=0; shift ;;
      --lang) lang="$2"; shift 2 ;;
      --trial) trial="$2"; shift 2 ;;
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
    if [[ "$trial" =~ ^[1-9][0-9]*$ ]]; then echo "PLAN=trial"; echo "TRIAL_UNTIL=$(date -d "$(today) + $trial days" +%F)"; else echo "PLAN=active"; fi
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
  log "Ready – nothing has been sent to the customer yet"
  show "$name"
  echo "The certificate for the address is issued on first use; the first page load can take ~20 seconds."
  echo
  echo "Next: 1) open the address and sign in with the details above to check it"
  echo "      2) see the welcome e-mail:   sudo bash scripts/customer.sh welcome $name --preview"
  echo "      3) send it when you approve: sudo bash scripts/customer.sh welcome $name"
}

# welcome <name> [en|ar]: e-mail the administrator the address and first password, through the website's mail sender.
welcome() {  # welcome <name> <lang or ""> <preview 0|1>
  need "$1"; local f; f="$(cenv "$1")"
  local lang="${2:-$(getenv WELCOME_LANG "$f")}" preview="${3:-0}"
  W_PREVIEW="$preview" W_NAME="$1" W_EMAIL="$(getenv ADMIN_EMAIL "$f")" W_COMPANY="$(getenv ORG_NAME "$f")" W_URL="https://$(getenv CUSTOMER_DOMAIN "$f")" \
  W_PW="$(getenv INITIAL_ADMIN_PASSWORD "$f")" W_LANG="${lang:-ar}" python3 -c '
import json, os
print(json.dumps({"name": os.environ["W_NAME"], "email": os.environ["W_EMAIL"], "company": os.environ["W_COMPANY"],
                  "url": os.environ["W_URL"], "password": os.environ["W_PW"], "lang": os.environ["W_LANG"],
                  "preview": os.environ["W_PREVIEW"] == "1"}))' \
  | docker compose -p plantpulse-site -f deploy/docker-compose.site.yml --env-file deploy/.env.site exec -T site python /app/server.py welcome \
  || { echo "Welcome e-mail not sent (website mail not set up?). Send the details above yourself."; return 1; }
  if [[ "$preview" == 0 ]]; then
    sed -i '/^WELCOME_SENT=/d' "$f"; echo "WELCOME_SENT=$(date -Is)" >> "$f"
  else
    echo "Nothing was sent. To send it: sudo bash scripts/customer.sh welcome $1${2:+ --lang $2}"
  fi
}

show() {
  need "$1"; local f; f="$(cenv "$1")"
  echo "Customer:   $1  ($(getenv ORG_NAME "$f"))"
  echo "Address:    https://$(getenv CUSTOMER_DOMAIN "$f")"
  echo "Admin:      $(getenv ADMIN_EMAIL "$f")"
  echo "Password:   $(getenv INITIAL_ADMIN_PASSWORD "$f")   (first password; useless once changed)"
  echo "Created:    $(getenv CREATED "$f")"
  echo "Plan:       $(plan_text "$1")    Status: $(getenv STATUS "$f" | sed 's/^$/running/')"
  echo "Welcome:    $(w="$(getenv WELCOME_SENT "$f")"; echo "${w:-not sent yet (customer.sh welcome $1 --preview)}")"
  echo "E-mail:     $([[ -n "$(getenv SMTP_HOST "$f")" ]] && echo "on, from $(getenv SMTP_FROM "$f")" || echo off)"
}

list() {
  shopt -s nullglob
  local files=("$CDIR"/*.env) n run
  echo "Version on the server: $(version)    Memory available: $(free -m | awk '/^Mem:/{print $7}') MB"
  [[ ${#files[@]} -gt 0 ]] || { echo "No customers yet. Create one: sudo bash scripts/customer.sh new <name> <admin-email> \"Company\""; return; }
  printf '%-14s %-36s %-8s %-27s %s\n' NAME ADDRESS RUNNING PLAN COMPANY
  for f in "${files[@]}"; do
    n="$(basename "$f" .env)"
    run="$(C "$n" ps --status running -q 2>/dev/null | wc -l)"
    if [[ "$(getenv STATUS "$f")" == paused ]]; then run="paused"; else run="$run/4"; fi
    printf '%-14s %-36s %-8s %-27s %s\n' "$n" "https://$(getenv CUSTOMER_DOMAIN "$f")" "$run" "$(plan_text "$n")" "$(getenv ORG_NAME "$f")"
  done
}

backup() {
  need "$1"; local dir="$BACKUPS/$1" stamp paused=0; stamp="$(date +%F-%H%M)"
  mkdir -p "$dir"; chmod 700 "$BACKUPS" "$dir"
  if [[ "$(getenv STATUS "$(cenv "$1")")" == paused ]]; then  # only the database, only for the backup
    paused=1; C "$1" up -d --wait db >/dev/null 2>&1
  fi
  C "$1" exec -T db pg_dump -U cmms_owner -d cmms -Fc > "$dir/$stamp.dump"
  docker run --rm -v "plantpulse-c-$1_storage:/s:ro" --entrypoint sh postgres:16.10-alpine -c 'tar czf - -C /s .' > "$dir/$stamp.storage.tgz"
  C "$1" exec -T db pg_restore --list < "$dir/$stamp.dump" >/dev/null || { echo "$1: BACKUP UNREADABLE ($dir/$stamp.dump)"; return 1; }
  [[ $paused == 1 ]] && C "$1" stop db >/dev/null 2>&1
  find "$dir" -type f -mtime +14 -delete
  echo "$1: backup $dir/$stamp.dump ($(du -h "$dir/$stamp.dump" | cut -f1)), attachments $(du -h "$dir/$stamp.storage.tgz" | cut -f1)"
  # Off-server copy: the same object-storage bucket as the main system's backups (scripts/set-backup-upload.sh),
  # under customers/<name>/.
  local url; url="$(getenv BACKUP_UPLOAD_URL deploy/.env)"
  if [[ -n "$url" ]]; then
    curl -fsS --retry 3 -T "$dir/$stamp.dump" "${url%/}/customers/$1/$stamp.dump" >/dev/null \
      && curl -fsS --retry 3 -T "$dir/$stamp.storage.tgz" "${url%/}/customers/$1/$stamp.storage.tgz" >/dev/null \
      && echo "$1: copied off the server (object storage customers/$1/)" \
      || { echo "$1: OFF-SERVER COPY FAILED (the local backup is fine)"; return 1; }
  else
    echo "$1: no off-server copy (BACKUP_UPLOAD_URL not set: sudo bash scripts/set-backup-upload.sh)"
  fi
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
  need "$1"
  if [[ "$(getenv STATUS "$(cenv "$1")")" == paused ]]; then echo "$1 is paused: left as is (it gets the new version on start)."; return 0; fi
  log "Moving $1 to version $(version)"
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
  welcome)
    n="${2:-}"; shift 2 || true; l=""; pv=0
    while [[ $# -gt 0 ]]; do case "$1" in --lang) l="${2:-}"; shift 2 ;; --preview) pv=1; shift ;; *) shift ;; esac; done
    welcome "$n" "$l" "$pv" ;;
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
  stop|pause) pause "${2:-}" ;;
  start|resume) resume "${2:-}" ;;
  extend)
    need "${2:-}"; [[ "${3:-}" =~ ^[1-9][0-9]*$ ]] || { echo "Usage: sudo bash scripts/customer.sh extend <name> <days>"; exit 2; }
    f="$(cenv "$2")"; u="$(getenv TRIAL_UNTIL "$f")"
    [[ -z "$u" || "$(days_left "$u")" -lt 0 ]] && u="$(today)"
    setval "$f" PLAN trial; setval "$f" TRIAL_UNTIL "$(date -d "$u + $3 days" +%F)"; sed -i '/^OWNER_REMINDED=/d' "$f"
    echo "$2: trial now until $(getenv TRIAL_UNTIL "$f")."
    if [[ "$(getenv STATUS "$f")" == paused ]]; then resume "$2"; fi ;;
  activate)
    need "${2:-}"; f="$(cenv "$2")"; setval "$f" PLAN active; sed -i '/^TRIAL_UNTIL=/d;/^OWNER_REMINDED=/d' "$f"
    echo "$2 is now an active (paid) customer: no trial end."
    if [[ "$(getenv STATUS "$f")" == paused ]]; then resume "$2"; fi ;;
  remind)
    n="${2:-}"; shift 2 || true; l=""; pv=0
    while [[ $# -gt 0 ]]; do case "$1" in --lang) l="${2:-}"; shift 2 ;; --preview) pv=1; shift ;; *) shift ;; esac; done
    remind "$n" "$l" "$pv" ;;
  trial-check) trial_check ;;
  logs) need "${2:-}"; C "$2" logs --tail 60 ;;
  *) sed -n '2,25p' "$0"; exit 2 ;;
esac
