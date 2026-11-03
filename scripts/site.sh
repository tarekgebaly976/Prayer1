#!/usr/bin/env bash
# PlantPulse product website at https://<PRODUCT_DOMAIN> (default plantpulse-cmms.com, www.<domain> redirects to it):
# the landing page (site/public) and the "Request a demo" form, which saves every request and e-mails it.
# It is a separate small container; the CMMS (real system and test copy) and their data are not touched. The only
# change to the running system is that Caddy is restarted once (2-3 seconds) when it first learns the new address.
#
#   sudo bash scripts/site.sh start       start it (asks once for the e-mail that receives demo requests)
#   sudo bash scripts/site.sh update      after `sudo git pull`: show the new page text/pictures, restart the form
#   sudo bash scripts/site.sh requests    list who asked for a demo or took the demo (default: last 20; `requests 100`)
#   sudo bash scripts/site.sh test-mail   send a test e-mail to the address that receives demo requests
#   sudo bash scripts/site.sh mail        change that address / the mail server (then restarts the form)
#   sudo bash scripts/site.sh resend noreply@your-domain [receiver]   send from your own domain via resend.com
#   sudo bash scripts/site.sh gmail sender@gmail.com [receiver@example.com]
#                                         the same for a Gmail sender with one question only (the App password;
#                                         or give it on stdin), then sends a test e-mail; handy from a phone
#   sudo bash scripts/site.sh stop | status | logs
#
# Optional: PRODUCT_DOMAIN=other-domain.com sudo bash scripts/site.sh start   (first start only; stored in deploy/.env)
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash scripts/site.sh ${1:-start}"; exit 1; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

REAL=(docker compose -f deploy/docker-compose.yml --env-file deploy/.env)
SENV=deploy/.env.site
SITE=(docker compose -p plantpulse-site -f deploy/docker-compose.site.yml --env-file "$SENV")

getenv() { grep -s "^$1=" "$2" | tail -n1 | cut -d= -f2- || true; }
setenv() {  # setenv KEY VALUE FILE
  local tmp; tmp="$(mktemp)"
  grep -sv "^$1=" "$3" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > "$3"; rm -f "$tmp"
}

ensure_domain() {
  [[ -f deploy/.env ]] || { echo "deploy/.env not found: install the CMMS first (deploy/install-server.sh)."; exit 1; }
  local cur; cur="$(getenv PRODUCT_DOMAIN deploy/.env)"
  if [[ -z "$cur" ]]; then
    cur="${PRODUCT_DOMAIN:-plantpulse-cmms.com}"
    setenv PRODUCT_DOMAIN "$cur" deploy/.env
    echo "Website address saved in deploy/.env: PRODUCT_DOMAIN=$cur"
  fi
  DOMAIN="$cur"
}

ask_smtp() {
  local host port user pass from
  read -rp "Mail server (SMTP host, e.g. smtp.gmail.com; Enter to skip): " host || true
  [[ -n "${host:-}" ]] || return 0
  read -rp "Port [587]: " port || true
  read -rp "User name (usually the sending e-mail): " user || true
  read -rsp "Password (for Gmail an App password): " pass || true; echo
  read -rp "From address [${user}]: " from || true
  setenv SITE_SMTP_HOST "$host" "$SENV"; setenv SITE_SMTP_PORT "${port:-587}" "$SENV"
  setenv SITE_SMTP_USER "$user" "$SENV"; setenv SITE_SMTP_PASSWORD "$pass" "$SENV"
  setenv SITE_SMTP_FROM "${from:-$user}" "$SENV"
}

# ask_mail [change]: the address that receives demo requests and the website's own mail server (never the CMMS's).
ask_mail() {
  umask 077; touch "$SENV"
  local to ans yn
  to="$(getenv CONTACT_TO "$SENV")"
  read -rp "E-mail that receives demo requests [${to:-none}]: " ans || true
  if [[ -n "${ans:-}" ]]; then to="$ans"; fi
  setenv CONTACT_TO "$to" "$SENV"
  if [[ -n "$(getenv SITE_SMTP_HOST "$SENV")" && "${1:-}" == change ]]; then
    read -rp "Change the mail server ($(getenv SITE_SMTP_HOST "$SENV"))? [y/N] " yn || true
    if [[ "${yn:-n}" =~ ^[yY] ]]; then ask_smtp; fi
  elif [[ -z "$(getenv SITE_SMTP_HOST "$SENV")" ]]; then
    echo "Requests are always saved on the server (sudo bash scripts/site.sh requests); a mail server also e-mails them."
    ask_smtp
  fi
  chmod 600 "$SENV"
}

ensure_env() {
  [[ -f "$SENV" ]] && return
  log "Setting up the demo request e-mail"
  if [[ -t 0 ]]; then ask_mail; else umask 077; : > "$SENV"; fi
}

check_dns() {
  local ip name addr
  ip="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
  [[ -n "$ip" ]] || return 0
  for name in "$DOMAIN" "www.$DOMAIN"; do
    addr="$(getent ahostsv4 "$name" 2>/dev/null | awk 'NR==1{print $1}')"
    if [[ "$addr" != "$ip" ]]; then
      echo "WARNING: $name points to '${addr:-nothing}', not to this server ($ip)."
      echo "         Add an A record $name -> $ip (Cloudflare: DNS only, grey cloud). HTTPS starts once it does."
    fi
  done
}

# Caddy must know the website address. Restart only Caddy (not the CMMS) and only when its address list changed.
caddy_current() {
  local want_env have_env same_file
  want_env="$DOMAIN"
  have_env="$("${REAL[@]}" exec -T caddy printenv PRODUCT_DOMAIN 2>/dev/null | tr -d '\r' || true)"
  same_file=0
  "${REAL[@]}" exec -T caddy cat /etc/caddy/Caddyfile 2>/dev/null | cmp -s - deploy/Caddyfile && same_file=1
  "${REAL[@]}" exec -T caddy test -d /etc/caddy/caddy.d 2>/dev/null || same_file=0   # customer folder mounted
  [[ "$have_env" == "$want_env" && $same_file == 1 ]]
}

# Check deploy/Caddyfile (and deploy/caddy.d) in a throw-away Caddy before the running one is touched: a mistake in
# the file must never take the sites down. Used here and by scripts/customer.sh.
validate_caddy() {
  mkdir -p deploy/caddy.d
  local img; img="$(grep -m1 'image: caddy:' deploy/docker-compose.yml | awk '{print $2}')"
  docker run --rm -e "CMMS_DOMAIN=$(getenv CMMS_DOMAIN deploy/.env)" -e "PRODUCT_DOMAIN=$DOMAIN" \
    -v "$PWD/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" -v "$PWD/deploy/caddy.d:/etc/caddy/caddy.d:ro" \
    "${img:-caddy:2.10.2-alpine}" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/tmp/caddy-validate.log 2>&1 \
    || { echo "The Caddy configuration has an error, so Caddy was NOT changed:"; tail -5 /tmp/caddy-validate.log; return 1; }
}

update_caddy() {
  if caddy_current; then echo "Caddy already serves https://$DOMAIN"; return; fi
  validate_caddy || exit 1
  log "Restarting Caddy so it serves https://$DOMAIN (the CMMS keeps running; 2-3 seconds without HTTPS)"
  "${REAL[@]}" up -d --no-deps --no-build --force-recreate caddy
}

wait_site() {
  for _ in $(seq 1 30); do
    "${SITE[@]}" exec -T site python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3)" 2>/dev/null && return 0
    sleep 2
  done
  echo "The website container did not answer; see: sudo bash scripts/site.sh logs"; return 1
}

start() {
  "${REAL[@]}" ps --status running caddy | grep -q caddy || { echo "The CMMS is not running; start it first."; exit 1; }
  docker network inspect papermill-cmms-edge >/dev/null 2>&1 || {
    echo "Update the real system first (it adds the connection the website needs):"
    echo "  cd /opt/cmms && sudo git pull && sudo bash deploy/install-server.sh"; exit 1; }
  ensure_domain
  ensure_env
  log "Starting the website"
  "${SITE[@]}" up -d
  wait_site
  update_caddy
  check_dns
  log "Ready"
  echo "Website:        https://$DOMAIN   (www.$DOMAIN redirects there)"
  echo "Demo requests:  e-mailed to $(getenv CONTACT_TO "$SENV"); list them: sudo bash scripts/site.sh requests"
  [[ -n "$(getenv SITE_SMTP_HOST "$SENV")" ]] || echo "                (no mail server set: sudo bash scripts/site.sh mail)"
}

requests() {
  local n="${1:-20}"
  "${SITE[@]}" exec -T site python - "$n" <<'PY'
import json, sys
from pathlib import Path
p = Path("/data/demo-requests.jsonl")
rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
print(f"{len(rows)} request(s) in total" + (f", last {int(sys.argv[1])}:" if rows else "."))
for r in rows[-int(sys.argv[1]):]:
    tag = "TOOK THE DEMO" if r.get("kind") == "demo-access" else "DEMO REQUEST"
    print(f"\n{r['received_at']}  [{tag}]  {r['company']}  –  {r['name']} <{r['email']}>  {r.get('phone') or ''}")
    extra = ", ".join(x for x in (r.get('industry'), r.get('team_size') and f"team {r['team_size']}", r.get('lang')) if x)
    if extra: print(f"  {extra}")
    if r.get("message"): print("  " + r["message"].replace("\n", "\n  "))
PY
}

case "${1:-start}" in
  start) start ;;
  update)
    ensure_domain; ensure_env
    log "Updating the website (page and form)"
    "${SITE[@]}" up -d --force-recreate
    wait_site; update_caddy
    echo "Website: https://$DOMAIN" ;;
  requests) requests "${2:-20}" ;;
  test-mail)
    "${SITE[@]}" exec -T site python /app/server.py test-mail \
      && echo "Test e-mail sent to $(getenv CONTACT_TO "$SENV")." \
      || { echo "Sending failed (details above). Change the settings with: sudo bash scripts/site.sh mail"; exit 1; } ;;
  mail)
    [[ -t 0 ]] || { echo "Run this in an interactive terminal (ssh -t)."; exit 1; }
    ensure_domain; ask_mail change
    "${SITE[@]}" up -d --force-recreate; wait_site
    echo "Saved. Check it with: sudo bash scripts/site.sh test-mail" ;;
  gmail)
    sender="${2:-}"; receiver="${3:-${2:-}}"
    [[ "$sender" == *@* && "$receiver" == *@* ]] || { echo "Usage: sudo bash scripts/site.sh gmail sender@gmail.com [receiver]"; exit 2; }
    if [[ -t 0 ]]; then
      read -rsp "Paste the Gmail App password (16 letters; nothing shows while you paste), then Enter: " pass || true; echo
    else
      pass="$(head -c 200)"
    fi
    pass="$(printf '%s' "$pass" | tr -d ' \t\r\n' | tr 'A-Z' 'a-z')"
    [[ "$pass" =~ ^[a-z]{16}$ ]] || { echo "That is not a Gmail App password (it has exactly 16 letters, e.g. abcd efgh ijkl mnop). Nothing changed."; exit 2; }
    ensure_domain; umask 077; touch "$SENV"
    setenv CONTACT_TO "$receiver" "$SENV"
    setenv SITE_SMTP_HOST smtp.gmail.com "$SENV"; setenv SITE_SMTP_PORT 587 "$SENV"
    setenv SITE_SMTP_USER "$sender" "$SENV"; setenv SITE_SMTP_PASSWORD "$pass" "$SENV"; setenv SITE_SMTP_FROM "$sender" "$SENV"
    chmod 600 "$SENV"
    log "Mail settings saved: demo requests go to $receiver, sent through $sender"
    "${SITE[@]}" up -d --force-recreate; wait_site
    log "Sending a test e-mail to $receiver"
    "${SITE[@]}" exec -T site python /app/server.py test-mail \
      && echo "Test e-mail sent. Look in $receiver (also Spam)." \
      || { echo "Sending failed (details above): check the App password and try again."; exit 1; } ;;
  resend)
    # Send from your own domain (e.g. noreply@plantpulse-cmms.com) through Resend (resend.com), after the domain is
    # verified there. Replies still go to CONTACT_TO. Optional third argument: a new address for the notifications.
    sender="${2:-}"; receiver="${3:-}"
    [[ "$sender" == *@* ]] || { echo "Usage: sudo bash scripts/site.sh resend noreply@your-domain [receiver]"; exit 2; }
    if [[ -t 0 ]]; then
      read -rsp "Paste the Resend API key (starts with re_; nothing shows while you paste), then Enter: " pass || true; echo
    else
      pass="$(head -c 300)"
    fi
    pass="$(printf '%s' "$pass" | tr -d ' \t\r\n')"
    [[ "$pass" =~ ^re_[A-Za-z0-9_]{10,}$ ]] || { echo "That is not a Resend API key (it starts with re_). Nothing changed."; exit 2; }
    ensure_domain; umask 077; touch "$SENV"
    [[ -n "$receiver" ]] && setenv CONTACT_TO "$receiver" "$SENV"
    [[ -n "$(getenv CONTACT_TO "$SENV")" ]] || { echo "Give the address that receives the requests as third argument."; exit 2; }
    setenv SITE_SMTP_HOST smtp.resend.com "$SENV"; setenv SITE_SMTP_PORT 587 "$SENV"
    setenv SITE_SMTP_USER resend "$SENV"; setenv SITE_SMTP_PASSWORD "$pass" "$SENV"; setenv SITE_SMTP_FROM "$sender" "$SENV"
    chmod 600 "$SENV"
    log "Mail settings saved: sent from $sender, requests go to $(getenv CONTACT_TO "$SENV")"
    "${SITE[@]}" up -d --force-recreate; wait_site
    log "Sending a test e-mail to $(getenv CONTACT_TO "$SENV")"
    "${SITE[@]}" exec -T site python /app/server.py test-mail \
      && echo "Test e-mail sent. Look in $(getenv CONTACT_TO "$SENV") (also Spam)." \
      || { echo "Sending failed (details above): is the domain verified in Resend, and the key right?"; exit 1; } ;;
  caddy-reload)  # used by scripts/customer.sh: pick up deploy/caddy.d without a restart, after a check
    ensure_domain
    if ! caddy_current; then update_caddy; exit 0; fi
    validate_caddy || exit 1
    "${REAL[@]}" exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null && echo "Caddy reloaded." ;;
  caddy) ensure_domain; update_caddy ;;  # used by scripts/demo.sh after it adds demo.<domain>
  stop) "${SITE[@]}" stop; echo "Website stopped (https://$(getenv PRODUCT_DOMAIN deploy/.env) answers 502). Requests are kept." ;;
  status) "${SITE[@]}" ps; echo "Address: https://$(getenv PRODUCT_DOMAIN deploy/.env)" ;;
  logs) "${SITE[@]}" logs --tail 100 site ;;
  *) echo "Usage: sudo bash scripts/site.sh start|update|requests [n]|test-mail|mail|gmail|resend|stop|status|logs"; exit 2 ;;
esac
