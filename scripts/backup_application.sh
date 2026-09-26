#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ -z "$BACKUP_DIR" || -z "$PGDATABASE" || -z "$STORAGE_ROOT" ]]; then
  echo "Set BACKUP_DIR, PGDATABASE, and STORAGE_ROOT" >&2
  exit 2
fi
if [[ "$BACKUP_DIR" != /* || "$STORAGE_ROOT" != /* ]]; then
  echo "BACKUP_DIR and STORAGE_ROOT must be absolute paths" >&2
  exit 2
fi
if [[ ! -d "$STORAGE_ROOT" ]]; then
  echo "STORAGE_ROOT does not exist" >&2
  exit 2
fi

retention_count="$BACKUP_RETENTION_COUNT"
if [[ ! "$retention_count" =~ ^[1-9][0-9]*$ ]]; then
  echo "BACKUP_RETENTION_COUNT must be a positive integer" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
timestamp="$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))')"
database_label="$(python3 -c 'import os, re; print(re.sub(r"[^A-Za-z0-9_-]", "_", os.environ["PGDATABASE"]))')"
destination="$BACKUP_DIR/agentic-$database_label-$timestamp"
temporary="$(mktemp -d "$BACKUP_DIR/.agentic-backup.XXXXXX")"
trap 'rm -rf "$temporary"' EXIT

pg_dump --format=custom --no-owner --no-acl --file="$temporary/postgres.dump" "$PGDATABASE"
pg_restore --list "$temporary/postgres.dump" >/dev/null
tar -czf "$temporary/storage.tar.gz" -C "$STORAGE_ROOT" .
tar -tzf "$temporary/storage.tar.gz" >/dev/null

BACKUP_DIRECTORY="$temporary" PGDATABASE="$PGDATABASE" python3 - <<'PY'
import hashlib
import os
from pathlib import Path

root = Path(os.environ["BACKUP_DIRECTORY"])
entries = []
for name in ("postgres.dump", "storage.tar.gz"):
    path = root / name
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    digest = checksum.hexdigest()
    entries.append(f"{digest}  {name}")
(root / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="ascii")
(root / "DATABASE").write_text(os.environ["PGDATABASE"] + "\n", encoding="utf-8")
PY

mv "$temporary" "$destination"
trap - EXIT

BACKUP_DIR="$BACKUP_DIR" BACKUP_DATABASE_LABEL="$database_label" BACKUP_RETENTION_COUNT="$retention_count" python3 - <<'PY'
import os
import shutil
from pathlib import Path

directory = Path(os.environ["BACKUP_DIR"])
label = os.environ["BACKUP_DATABASE_LABEL"]
keep = int(os.environ["BACKUP_RETENTION_COUNT"])
backups = sorted(
    (item for item in directory.glob(f"agentic-{label}-20*") if item.is_dir()),
    key=lambda item: item.name,
)
for old_backup in backups[:-keep]:
    shutil.rmtree(old_backup)
PY

printf 'Backup bundle created: %s\n' "$destination"
