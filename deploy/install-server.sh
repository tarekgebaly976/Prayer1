#!/usr/bin/env bash
# One-command installer for a single Linux server (tested target: Oracle Cloud Always Free, Ubuntu 22.04/24.04,
# Ampere ARM or x86). Installs Docker, fetches the CMMS, generates secrets, starts the stack with HTTPS and creates
# the first administrator.
#
#   curl -fsSL <raw URL of this file> -o install.sh && sudo bash install.sh
#
# Optional environment variables:
#   GITHUB_TOKEN   read-only token if the repository is private
#   REPO           default: tarekgebaly976/Prayer1        BRANCH  default: ccr-82ee8296-9m776u
#   CMMS_DOMAIN    your domain; default: <public-ip>.sslip.io (free hostname -> real Let's Encrypt certificate)
#   ADMIN_EMAIL    first administrator e-mail (prompted if missing)
#   SEED_DEMO=1    also load the separate DEMO organisation with sample data
set -euo pipefail

REPO="${REPO:-tarekgebaly976/Prayer1}"
BRANCH="${BRANCH:-ccr-82ee8296-9m776u}"
DIR=/opt/cmms

[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash install.sh"; exit 1; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

log "Installing Docker and tools"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
export DEBIAN_FRONTEND=noninteractive
echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | debconf-set-selections
apt-get update -qq && apt-get install -y -qq git openssl curl iptables-persistent >/dev/null 2>&1 || apt-get install -y -qq git openssl curl
systemctl enable --now docker

log "Opening ports 80 and 443 in the server firewall"
# Oracle Ubuntu images ship iptables rules that reject everything except SSH.
for p in 80 443; do
  iptables -C INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null || iptables -I INPUT 5 -p tcp --dport "$p" -m state --state NEW -j ACCEPT
done
command -v netfilter-persistent >/dev/null && netfilter-persistent save >/dev/null 2>&1 || true

log "Fetching the application ($REPO@$BRANCH)"
URL="https://github.com/$REPO.git"
[[ -n "${GITHUB_TOKEN:-}" ]] && URL="https://x-access-token:${GITHUB_TOKEN}@github.com/$REPO.git"
if [[ -d "$DIR/.git" ]]; then
  git -C "$DIR" fetch -q origin "$BRANCH" && git -C "$DIR" checkout -q "$BRANCH" && git -C "$DIR" reset -q --hard "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$URL" "$DIR"
fi
git -C "$DIR" remote set-url origin "https://github.com/$REPO.git"   # do not keep the token on disk
cd "$DIR"

if [[ ! -f deploy/.env ]]; then
  log "Generating configuration and database passwords"
  IP="$(curl -fsS https://api.ipify.org || curl -fsS https://ifconfig.me)"
  DOMAIN="${CMMS_DOMAIN:-${IP//./-}.sslip.io}"
  umask 077
  cat > deploy/.env <<EOF
CMMS_ENVIRONMENT=production
CMMS_DOMAIN=$DOMAIN
CMMS_OWNER_DB_PASSWORD=$(openssl rand -hex 24)
CMMS_APP_DB_PASSWORD=$(openssl rand -hex 24)
CMMS_STORAGE_BACKEND=local
EOF
fi
DOMAIN="$(grep '^CMMS_DOMAIN=' deploy/.env | cut -d= -f2)"
COMPOSE=(docker compose -f deploy/docker-compose.yml --env-file deploy/.env)

log "Building and starting (first build takes 5-15 minutes on a small server)"
"${COMPOSE[@]}" up -d --build

log "Waiting for the application"
for _ in $(seq 1 120); do
  "${COMPOSE[@]}" exec -T api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready',timeout=3)" 2>/dev/null && break
  sleep 5
done

USERS="$("${COMPOSE[@]}" exec -T db psql -U cmms_owner -d cmms -Atc "SELECT count(*) FROM users" 2>/dev/null || echo 0)"
if [[ "${USERS//[^0-9]/}" == "0" ]]; then
  log "Creating the first administrator"
  ADMIN_EMAIL="${ADMIN_EMAIL:-}"
  [[ -n "$ADMIN_EMAIL" ]] || read -rp "Administrator e-mail: " ADMIN_EMAIL
  read -rp "Organisation code (e.g. ACME): " ORG
  read -rp "Organisation name: " ORGNAME
  read -rp "Plant code (e.g. PM1): " PLANT
  read -rp "Plant name: " PLANTNAME
  echo "Password: at least 12 characters with 3 of: lowercase, uppercase, digit, symbol"
  "${COMPOSE[@]}" exec api python -m app.cli bootstrap --org-code "$ORG" --org-name "$ORGNAME" \
    --plant-code "$PLANT" --plant-name "$PLANTNAME" --admin-email "$ADMIN_EMAIL"
else
  echo "Administrator already exists. To set a new password:"
  echo "  cd $DIR && sudo ${COMPOSE[*]} exec api python -m app.cli reset-password --email <admin e-mail>"
fi

if [[ "${SEED_DEMO:-0}" == 1 ]]; then
  log "Loading sample data (separate DEMO organisation)"
  echo "Choose a password for the demo users:"
  "${COMPOSE[@]}" exec api python -m app.cli seed-demo
fi

log "Scheduling nightly backups (02:15 server time, kept 14 days in /opt/cmms-backups)"
CRON="15 2 * * * cd $DIR && ENV_FILE=deploy/.env scripts/backup.sh /opt/cmms-backups >> /var/log/cmms-backup.log 2>&1"
{ crontab -l 2>/dev/null | grep -v 'scripts/backup.sh' || true; echo "$CRON"; } | crontab -

log "Done"
echo "Open:  https://$DOMAIN"
echo "If the page does not load, add ingress rules for TCP 80 and 443 (source 0.0.0.0/0) to the subnet's"
echo "security list in the Oracle console: Networking > Virtual cloud networks > your VCN > Security Lists."
echo "Update later with:  sudo bash $DIR/deploy/install-server.sh"
