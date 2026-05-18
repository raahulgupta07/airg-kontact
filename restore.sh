#!/usr/bin/env bash
# KONTACT — restore from backup archive
#
# Usage:  ./restore.sh /path/to/kontact-backup-YYYYMMDD-HHMMSS.tar.gz
#
# Requires: docker compose, git repo checked out, no running kontact container
# (script will stop it). Destructive — overwrites the volume.

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <kontact-backup-*.tar.gz>"
  exit 1
fi

ARCHIVE="$1"
if [ ! -f "$ARCHIVE" ]; then
  echo "ERROR: archive not found: $ARCHIVE"
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[1/6] Extracting archive..."
tar -xzf "$ARCHIVE" -C "$WORK"

echo "[2/6] Manifest:"
if [ -f "$WORK/manifest.txt" ]; then
  head -10 "$WORK/manifest.txt" | sed 's/^/  /'
fi

read -rp "Continue restore? This will overwrite current data. [y/N] " ans
if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
  echo "Cancelled."
  exit 0
fi

echo "[3/6] Stopping kontact container (if running)..."
docker compose stop kontact 2>/dev/null || true

echo "[4/6] Restoring .env..."
if [ -f "$WORK/.env" ]; then
  if [ -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env" "$REPO_DIR/.env.pre-restore-$(date +%s)"
    echo "  existing .env backed up to .env.pre-restore-*"
  fi
  cp "$WORK/.env" "$REPO_DIR/.env"
  echo "  .env restored"
else
  echo "  no .env in archive — keep your existing one"
fi

echo "[5/6] Restoring data volume..."
# Start container momentarily to create the volume mount, then copy in
docker compose up -d --no-deps kontact >/dev/null 2>&1 || true
sleep 2
docker compose exec -T kontact rm -rf /app/data 2>/dev/null || true
docker compose cp "$WORK/data" kontact:/app/data
docker compose exec -T kontact chmod -R u+rw /app/data 2>/dev/null || true

echo "[6/6] Restarting kontact..."
docker compose restart kontact
sleep 5

echo
echo "✓ Restore complete."
echo
echo "Verify:"
echo "  curl http://localhost:\${PORT:-8090}/health"
echo "  docker compose logs --tail 20 kontact"
