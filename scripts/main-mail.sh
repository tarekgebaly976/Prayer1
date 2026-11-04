#!/usr/bin/env bash
# E-mail for the main (plant) system at /opt/cmms, with the same sender as the website (deploy/.env.site, Resend).
#
#   sudo bash scripts/main-mail.sh reset-only   only "forgot password" links and "password changed" e-mails
#   sudo bash scripts/main-mail.sh all          also emergency breakdowns, critical alerts and daily summaries
#   sudo bash scripts/main-mail.sh off          no e-mail at all ("ask your administrator" on the sign-in page)
#   sudo bash scripts/main-mail.sh status
#
# Restarts only the main system's API and worker (a few seconds). The test copy and the demo never send e-mail.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash scripts/main-mail.sh ${1:-status}"; exit 1; }
ENV=deploy/.env
SENV=deploy/.env.site
REAL=(docker compose -f deploy/docker-compose.yml --env-file "$ENV")

getenv() { grep -s "^$1=" "$2" | tail -n1 | cut -d= -f2- || true; }
setenv() {  # setenv KEY VALUE FILE (file keeps its permissions)
  local tmp; tmp="$(mktemp)"
  grep -sv "^$1=" "$3" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > "$3"; rm -f "$tmp"
}

status() {
  local host notif; host="$(getenv CMMS_SMTP_HOST "$ENV")"; notif="$(getenv CMMS_EMAIL_NOTIFICATIONS "$ENV")"
  if [[ -z "$host" ]]; then echo "E-mail: off"; return; fi
  echo "E-mail: on, from $(getenv CMMS_SMTP_FROM "$ENV") via $host"
  [[ "${notif:-true}" == false ]] && echo "Sends: password reset only" || echo "Sends: password reset, emergencies, critical alerts, daily summaries"
}

restart() {
  echo "Restarting the main system's API and worker…"
  "${REAL[@]}" up -d api worker >/dev/null
  status
}

case "${1:-status}" in
  reset-only|all)
    [[ -n "$(getenv SITE_SMTP_HOST "$SENV")" ]] || { echo "The website has no mail sender yet: sudo bash scripts/site.sh resend noreply@<domain>"; exit 1; }
    for k in HOST PORT USER PASSWORD FROM; do setenv "CMMS_SMTP_$k" "$(getenv "SITE_SMTP_$k" "$SENV")" "$ENV"; done
    setenv CMMS_EMAIL_NOTIFICATIONS "$([[ $1 == all ]] && echo true || echo false)" "$ENV"
    restart ;;
  off)
    for k in HOST USER PASSWORD FROM; do setenv "CMMS_SMTP_$k" "" "$ENV"; done
    restart ;;
  status) status ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
