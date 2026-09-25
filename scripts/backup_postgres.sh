#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_DIR:?Set BACKUP_DIR to an absolute backup directory}"
: "${PGDATABASE:?Set PGDATABASE to the database name}"

if [[ "$BACKUP_DIR" != /* ]]; then
  echo "BACKUP_DIR must be an absolute path" >&2
  exit 2
fi

retention_count="${BACKUP_RETENTION_COUNT:-14}"
if [[ ! "$retention_count" =~ ^[1-9][0-9]*$ ]]; then
  echo "BACKUP_RETENTION_COUNT must be a positive integer" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
timestamp="$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))')"
database_label="$(python3 -c 'import os, re; print(re.sub(r"[^A-Za-z0-9_-]", "_", os.environ["PGDATABASE"]))')"
destination="$BACKUP_DIR/postgres-$database_label-$timestamp.dump"
temporary="$(mktemp "$BACKUP_DIR/.postgres-backup.XXXXXX")"
trap 'rm -f "$temporary"' EXIT

pg_dump --format=custom --no-owner --no-acl --file="$temporary" "$PGDATABASE"
pg_restore --list "$temporary" >/dev/null
mv "$temporary" "$destination"
trap - EXIT

BACKUP_DIR="$BACKUP_DIR" BACKUP_DATABASE_LABEL="$database_label" BACKUP_RETENTION_COUNT="$retention_count" python3 - <<'PY'
import os
from pathlib import Path

directory = Path(os.environ["BACKUP_DIR"])
keep = int(os.environ["BACKUP_RETENTION_COUNT"])
database_label = os.environ["BACKUP_DATABASE_LABEL"]
backups = sorted(directory.glob(f"postgres-{database_label}-*.dump"), key=lambda item: item.name)
for old_backup in backups[:-keep]:
    old_backup.unlink()
PY

printf 'Backup created: %s\n' "$destination"
