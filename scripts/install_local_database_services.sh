#!/usr/bin/env bash
set -euo pipefail

AGENTDB_REPOSITORY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTDB_RUNTIME_ROOT="/Users/lethanh/.local/share/agentic-marketing"
AGENTDB_SECRET_DIR="$AGENTDB_RUNTIME_ROOT/secrets"
AGENTDB_SCRIPT_DIR="$AGENTDB_RUNTIME_ROOT/scripts"
AGENTDB_LOG_DIR="$AGENTDB_RUNTIME_ROOT/logs"
AGENTDB_LAUNCH_AGENT_DIR="/Users/lethanh/Library/LaunchAgents"
AGENTDB_UID="$(/usr/bin/id -u)"
AGENTDB_DOMAIN="gui/$AGENTDB_UID"

mkdir -p "$AGENTDB_SCRIPT_DIR" "$AGENTDB_LOG_DIR" "$AGENTDB_LAUNCH_AGENT_DIR"
chmod 700 "$AGENTDB_RUNTIME_ROOT" "$AGENTDB_SECRET_DIR" "$AGENTDB_SCRIPT_DIR" "$AGENTDB_LOG_DIR"

cat > "$AGENTDB_SECRET_DIR/backup.env" <<'EOF'
BACKUP_DIR=/Users/lethanh/.local/share/agentic-marketing/backups
PGDATABASE=agentic_marketing_fresh
PGHOST=127.0.0.1
PGPORT=15432
PGUSER=agentic_owner
PGPASSFILE=/Users/lethanh/.local/share/agentic-marketing/secrets/pgpass
STORAGE_ROOT=/Users/lethanh/.local/share/agentic-marketing/storage
BACKUP_RETENTION_COUNT=14
EOF
chmod 600 "$AGENTDB_SECRET_DIR/backup.env"
cp "$AGENTDB_REPOSITORY_ROOT/scripts/backup_application.sh" "$AGENTDB_SCRIPT_DIR/backup_application.sh"

cat > "$AGENTDB_SCRIPT_DIR/run_backup.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
AGENTDB_RUNTIME_ROOT=/Users/lethanh/.local/share/agentic-marketing
set -a
. "$AGENTDB_RUNTIME_ROOT/secrets/backup.env"
set +a
AGENTDB_LAST_BACKUP="$(/usr/bin/find "$BACKUP_DIR" -maxdepth 1 -type d -name 'agentic-agentic_marketing_fresh-20*' -print 2>/dev/null | /usr/bin/xargs -I{} /usr/bin/stat -f '%m %N' {} 2>/dev/null | /usr/bin/sort -rn | /usr/bin/head -1 | /usr/bin/awk '{print $1}')"
if [[ -n "$AGENTDB_LAST_BACKUP" ]] && (( $(/bin/date +%s) - AGENTDB_LAST_BACKUP < 86400 )); then
  exit 0
fi
for AGENTDB_ATTEMPT in {1..30}; do
  if /opt/homebrew/bin/pg_isready -h "$PGHOST" -p "$PGPORT" -d "$PGDATABASE" >/dev/null 2>&1; then
    exec /bin/bash "$AGENTDB_RUNTIME_ROOT/scripts/backup_application.sh"
  fi
  /bin/sleep 2
done
echo "PostgreSQL did not become ready for the local backup." >&2
exit 1
EOF
chmod 700 "$AGENTDB_SCRIPT_DIR/run_backup.sh"

AGENTDB_RUNTIME_ROOT="$AGENTDB_RUNTIME_ROOT" python3 - <<'PY'
import os
import plistlib
from pathlib import Path

root = Path(os.environ["AGENTDB_RUNTIME_ROOT"])
launch_agents = Path("/Users/lethanh/Library/LaunchAgents")
log_dir = root / "logs"

jobs = {
    "com.agentic-marketing.postgres": [
        "/opt/homebrew/bin/postgres",
        "-D", str(root / "postgres"),
        "-h", "127.0.0.1",
        "-p", "15432",
        "-c", "unix_socket_directories=/tmp",
        "-c", "timezone=UTC",
        "-c", "shared_buffers=256MB",
    ],
    "com.agentic-marketing.redis-queue": [
        "/opt/homebrew/bin/redis-server",
        "--bind", "127.0.0.1", "--protected-mode", "yes",
        "--port", "16379", "--dir", str(root / "redis-queue"),
        "--appendonly", "yes", "--appendfsync", "everysec",
        "--maxmemory", "256mb", "--maxmemory-policy", "noeviction",
        "--daemonize", "no",
    ],
    "com.agentic-marketing.redis-cache": [
        "/opt/homebrew/bin/redis-server",
        "--bind", "127.0.0.1", "--protected-mode", "yes",
        "--port", "16380", "--dir", str(root / "redis-cache"),
        "--save", "", "--appendonly", "no",
        "--maxmemory", "64mb", "--maxmemory-policy", "allkeys-lru",
        "--daemonize", "no",
    ],
    "com.agentic-marketing.backup": ["/bin/bash", str(root / "scripts" / "run_backup.sh")],
}

for label, arguments in jobs.items():
    plist = {
        "Label": label,
        "ProgramArguments": arguments,
        # launchd's sparse locale environment can trigger PG's macOS startup
        # guard; use the stable POSIX locale for this local cluster.
        "EnvironmentVariables": {"LANG": "C", "LC_ALL": "C"},
        "RunAtLoad": True,
        "StandardOutPath": str(log_dir / f"{label}.log"),
        "StandardErrorPath": str(log_dir / f"{label}.error.log"),
        "WorkingDirectory": str(root),
    }
    if label == "com.agentic-marketing.backup":
        plist["StartCalendarInterval"] = {"Hour": 3, "Minute": 0}
    else:
        plist["KeepAlive"] = True
    path = launch_agents / f"{label}.plist"
    path.write_bytes(plistlib.dumps(plist))
    path.chmod(0o600)
PY

# Unload only the task-owned agents before stopping their daemons. Keeping a
# KeepAlive LaunchAgent loaded while pg_ctl/redis-cli shuts a process down can
# cause launchd to restart it before the next step finishes.
for AGENTDB_LABEL in \
  com.agentic-marketing.postgres \
  com.agentic-marketing.redis-queue \
  com.agentic-marketing.redis-cache \
  com.agentic-marketing.backup; do
  if /bin/launchctl print "$AGENTDB_DOMAIN/$AGENTDB_LABEL" >/dev/null 2>&1; then
    /bin/launchctl bootout "$AGENTDB_DOMAIN/$AGENTDB_LABEL"
  fi
done

# Stop only the PostgreSQL data directory and Redis PIDs created for this task.
if /opt/homebrew/bin/pg_ctl -D "$AGENTDB_RUNTIME_ROOT/postgres" status >/dev/null 2>&1; then
  /opt/homebrew/bin/pg_ctl -D "$AGENTDB_RUNTIME_ROOT/postgres" -m fast -w stop
fi
for AGENTDB_ENTRY in "redis-queue:16379" "redis-cache:16380"; do
  AGENTDB_NAME="$(/usr/bin/cut -d: -f1 <<<"$AGENTDB_ENTRY")"
  AGENTDB_PORT="$(/usr/bin/cut -d: -f2 <<<"$AGENTDB_ENTRY")"
  if [[ -f "$AGENTDB_RUNTIME_ROOT/$AGENTDB_NAME/redis.pid" ]]; then
    AGENTDB_PID="$(cat "$AGENTDB_RUNTIME_ROOT/$AGENTDB_NAME/redis.pid")"
    AGENTDB_SERVER_PID="$(/opt/homebrew/bin/redis-cli -h 127.0.0.1 -p "$AGENTDB_PORT" --raw INFO server 2>/dev/null | /usr/bin/awk -F: '/^process_id:/ {gsub("\r", "", $2); print $2}')"
    if [[ -n "$AGENTDB_PID" && "$AGENTDB_PID" == "$AGENTDB_SERVER_PID" ]]; then
      /opt/homebrew/bin/redis-cli -h 127.0.0.1 -p "$AGENTDB_PORT" shutdown
    fi
  fi
done

for AGENTDB_LABEL in \
  com.agentic-marketing.postgres \
  com.agentic-marketing.redis-queue \
  com.agentic-marketing.redis-cache \
  com.agentic-marketing.backup; do
  AGENTDB_REGISTERED=0
  for AGENTDB_BOOTSTRAP_ATTEMPT in {1..5}; do
    if /bin/launchctl bootstrap "$AGENTDB_DOMAIN" "$AGENTDB_LAUNCH_AGENT_DIR/$AGENTDB_LABEL.plist" 2>/dev/null; then
      AGENTDB_REGISTERED=1
      break
    fi
    if /bin/launchctl print "$AGENTDB_DOMAIN/$AGENTDB_LABEL" >/dev/null 2>&1; then
      AGENTDB_REGISTERED=1
      break
    fi
    /bin/sleep 2
  done
  if [[ "$AGENTDB_REGISTERED" != 1 ]]; then
    echo "Could not register LaunchAgent $AGENTDB_LABEL" >&2
    exit 1
  fi
done

for AGENTDB_ATTEMPT in {1..30}; do
  if /opt/homebrew/bin/pg_isready -h 127.0.0.1 -p 15432 -d agentic_marketing_fresh >/dev/null 2>&1 \
    && /opt/homebrew/bin/redis-cli -h 127.0.0.1 -p 16379 ping >/dev/null 2>&1 \
    && /opt/homebrew/bin/redis-cli -h 127.0.0.1 -p 16380 ping >/dev/null 2>&1; then
    echo "Local PostgreSQL, Redis queue, Redis cache, and daily backup services are loaded."
    exit 0
  fi
  /bin/sleep 2
done
echo "Local services were registered but did not become ready; inspect $AGENTDB_LOG_DIR." >&2
exit 1
