#!/usr/bin/env bash
# Store the object-storage upload URL for nightly backups and test it with a fresh backup.
#   sudo bash scripts/set-backup-upload.sh          (run from the repo root on the server, e.g. /opt/cmms)
# The URL is a secret (anyone holding it can write to the bucket): it is read without echo and kept only in
# deploy/.env (mode 600, not in git).
set -euo pipefail
ENV_FILE="${ENV_FILE:-deploy/.env}"
[[ -f "$ENV_FILE" ]] || { echo "Run from the CMMS folder (missing $ENV_FILE)"; exit 1; }
read -rsp "Paste the bucket pre-authenticated request URL (ends with /o/), then Enter: " URL; echo
URL="$(printf %s "$URL" | tr -d '[:space:]' | sed -e 's/^\x1b\[200~//' -e 's/\x1b\[201~$//')"  # stray spaces / bracketed-paste marks
[[ "$URL" == https://*/o/ ]] || { echo "That does not look like a bucket PAR URL ending with /o/"; exit 1; }
grep -v '^BACKUP_UPLOAD_URL=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
echo "BACKUP_UPLOAD_URL=$URL" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"; chmod 600 "$ENV_FILE"
echo "Saved. Running a backup now to test the upload..."
ENV_FILE="$ENV_FILE" bash scripts/backup.sh /opt/cmms-backups
