#!/usr/bin/env bash
# KONTACT — full backup script
# Produces a single .tar.gz with everything needed to restore on a new server.
#
# Output: kontact-backup-YYYYMMDD-HHMMSS.tar.gz
# Contains:
#   - data/ (full app data: SQLite WAL-checkpointed, ChromaDB, uploads, extractions, JSON)
#   - .env  (secrets — DO NOT share publicly)
#   - manifest.txt (sizes + timestamps for verification)
#
# Usage:  ./backup.sh                 -> writes to ./backups/
#         ./backup.sh /path/to/dir    -> writes to that dir

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${1:-$REPO_DIR/backups}"
TS="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$OUT_DIR/kontact-backup-$TS.tar.gz"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$OUT_DIR"

echo "[1/5] Checkpointing SQLite WAL into main DB..."
# Force WAL truncate so the main .db file is self-contained
docker compose exec -T kontact python3 -c "
import sqlite3
c = sqlite3.connect('/app/data/kontact.db')
c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
c.close()
print('  WAL checkpointed')
" 2>/dev/null || echo "  (skipped — container not running)"

echo "[2/5] Copying data volume..."
docker compose cp kontact:/app/data "$WORK/data"

echo "[3/5] Copying .env..."
if [ -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/.env" "$WORK/.env"
else
  echo "  WARNING: .env missing — restore will need a fresh one"
fi

echo "[4/5] Writing manifest..."
{
  echo "KONTACT backup"
  echo "timestamp:    $TS"
  echo "source_host:  $(hostname)"
  echo "git_commit:   $(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "git_branch:   $(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo
  echo "Sizes:"
  du -sh "$WORK"/* 2>/dev/null
  echo
  echo "SQLite row counts:"
  docker compose exec -T kontact python3 -c "
import sqlite3
c = sqlite3.connect('/app/data/kontact.db')
for tbl in ['users','documents','products','contacts','queue','chat_history','audit_events','tags','notes','meetings','events']:
    try:
        n = c.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
        print(f'  {tbl}: {n}')
    except Exception as e:
        print(f'  {tbl}: (error)')
c.close()
" 2>/dev/null || echo "  (container not running — row counts skipped)"
} > "$WORK/manifest.txt"

echo "[5/5] Creating archive..."
tar -czf "$ARCHIVE" -C "$WORK" .

SIZE=$(du -h "$ARCHIVE" | cut -f1)
echo
echo "✓ Backup complete: $ARCHIVE  ($SIZE)"
echo
echo "To restore on a new server:"
echo "  1. git clone <repo> && cd City-KONTACT"
echo "  2. ./restore.sh $(basename "$ARCHIVE")"
echo "  3. docker compose up -d --build kontact"
