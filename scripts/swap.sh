#!/usr/bin/env bash
# Add a swap file (default 4 GB) so the server does not kill a database or the app when memory runs short, e.g. while
# a new version is being built. Safe to run while everything is running, and safe to run again (it does nothing then).
#
#   sudo bash scripts/swap.sh          # 4 GB
#   sudo bash scripts/swap.sh 6        # another size in GB
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash scripts/swap.sh"; exit 1; }
GB="${1:-4}"
FILE=/swapfile

if swapon --show=NAME --noheadings | grep -qx "$FILE"; then
  echo "Swap is already on:"; swapon --show; free -h; exit 0
fi

free_gb=$(df --output=avail -BG / | tail -1 | tr -dc '0-9')
if (( free_gb < GB + 5 )); then
  echo "Only ${free_gb} GB free on the disk; keep at least 5 GB after the swap file. Nothing changed."; exit 1
fi

echo "==> Creating a ${GB} GB swap file ($FILE)"
[[ -f "$FILE" ]] || fallocate -l "${GB}G" "$FILE" 2>/dev/null || dd if=/dev/zero of="$FILE" bs=1M count=$((GB * 1024)) status=none
chmod 600 "$FILE"
mkswap "$FILE" >/dev/null
swapon "$FILE"
grep -q "^$FILE " /etc/fstab || echo "$FILE none swap sw 0 0" >> /etc/fstab   # back after a restart

# Use swap only as a safety net, not for normal work (keeps the databases fast).
echo "vm.swappiness=10" > /etc/sysctl.d/99-plantpulse-swap.conf
sysctl -q -p /etc/sysctl.d/99-plantpulse-swap.conf

echo "==> Done"
swapon --show
free -h
