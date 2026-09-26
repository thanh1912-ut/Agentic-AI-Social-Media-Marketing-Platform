# Local PostgreSQL and Redis runbook

This runbook applies to the isolated macOS runtime used for local development and verification. It does not manage the pre-existing PostgreSQL/Redis services on ports 5432 and 6379.

## Local services and data

- PostgreSQL 18 with pgvector: 127.0.0.1:15432; application database: agentic_marketing_fresh.
- Redis queue: 127.0.0.1:16379, AOF everysec, policy noeviction, 256 MB.
- Redis cache: 127.0.0.1:16380, no persistence, policy allkeys-lru, 64 MB.
- Persistent runtime root: /Users/lethanh/.local/share/agentic-marketing.
- User LaunchAgents keep the three services available while the user session is logged in. Redis and PostgreSQL listen only on loopback; PostgreSQL uses UTC.
- The local backup is a custom-format PostgreSQL dump plus a tarball of local storage, checksummed together and pruned to the newest 14 bundles. At login, the backup job fills a gap only if the most recent bundle is older than 24 hours; it also runs daily at 03:00 local time.
- PostgreSQL and Redis are installed from the host package manager. The application venv used for this rollout is /private/tmp/agentic-marketing-py311.

## Start, inspect, and stop

Install or refresh the dedicated user services from the repository root:

    bash scripts/install_local_database_services.sh

Inspect readiness without displaying credentials:

    /opt/homebrew/bin/pg_isready -h 127.0.0.1 -p 15432 -d agentic_marketing_fresh
    /opt/homebrew/bin/redis-cli -h 127.0.0.1 -p 16379 ping
    /opt/homebrew/bin/redis-cli -h 127.0.0.1 -p 16380 ping

Logs are in /Users/lethanh/.local/share/agentic-marketing/logs. Stop only these services with:

    launchctl bootout gui/$(id -u)/com.agentic-marketing.backup
    launchctl bootout gui/$(id -u)/com.agentic-marketing.redis-cache
    launchctl bootout gui/$(id -u)/com.agentic-marketing.redis-queue
    launchctl bootout gui/$(id -u)/com.agentic-marketing.postgres

To start them again, run the installer. This leaves unrelated services and their data untouched.

## Environment variables

Keep credentials in the local secret directory, not in the repository. The installer writes only non-secret backup settings to secrets/backup.env; PostgreSQL credentials and pgpass stay in files with restricted permissions.

The API, worker, and scheduler must use the same PostgreSQL database, queue Redis, and absolute storage path. Set the equivalent of these placeholders in a protected local environment file:

    APP_ENV=development
    DATABASE_URL=postgresql+asyncpg://agentic_app:<password>@127.0.0.1:15432/agentic_marketing_fresh
    # Migration command only; keep this in a protected owner environment file.
    MIGRATION_DATABASE_URL=postgresql+asyncpg://agentic_owner:<password>@127.0.0.1:15432/agentic_marketing_fresh
    REDIS_URL=redis://127.0.0.1:16379/0
    REDIS_CACHE_URL=redis://127.0.0.1:16380/0
    STORAGE_BACKEND=local
    STORAGE_ROOT=/Users/lethanh/.local/share/agentic-marketing/storage
    AUTO_CREATE_SCHEMA=0
    INLINE_JOBS=0
    WEB_BASE_URL=http://127.0.0.1:3100
    CORS_ALLOWED_ORIGINS=http://127.0.0.1:3100
    JWT_SECRET=<random secret of at least 32 bytes>

Use the repository's documented setting names if they differ from this example. Do not put /api/v1 in NEXT_PUBLIC_API_BASE_URL; set NEXT_PUBLIC_USE_MOCKS=0 for the real frontend. Keep DEEPSEEK_API_KEY, Meta credentials, and encryption keys in a secret store or protected environment. Do not copy them into command output or documentation. A missing DeepSeek credential affects AI analysis only; it must not block persistence of crawl or application data.

## Migration and application start

Activate the task-specific Python environment and load the protected environment file without echoing it. `agentic_app` is runtime CRUD only; run migrations with `agentic_owner`. For a one-off local migration, override `DATABASE_URL` in that process and keep the app/worker environment on the runtime URL:

    DATABASE_URL="$MIGRATION_DATABASE_URL" alembic upgrade head
    DATABASE_URL="$MIGRATION_DATABASE_URL" alembic check
    uvicorn services.api.main:app --host 127.0.0.1 --port 8000
    celery -A services.worker.celery_app:celery_app worker --queues default,agent
    celery -A services.worker.celery_app:celery_app beat

Run API, worker, and scheduler in separate terminals. Readiness must report the current Alembic head. The local frontend is http://127.0.0.1:3100 and must use the API at http://127.0.0.1:8000.

## Backup and restore

Manual backup (use the protected backup.env and PGPASSFILE without printing them):

    set -a
    . /Users/lethanh/.local/share/agentic-marketing/secrets/backup.env
    set +a
    bash scripts/backup_application.sh

Each bundle contains `postgres.dump`, `storage.tar.gz`, `SHA256SUMS`, and `DATABASE`. Verify its checksums before restore. Restore to a new empty database and a separate empty storage directory; never overwrite the live database/storage during a rehearsal. `vector` is a superuser-installed extension, so create it with the local database admin first. The dump omits ACL/owner commands; restore objects as the migration owner, then explicitly reapply runtime and default privileges:

    shasum -a 256 -c SHA256SUMS
    createdb --host 127.0.0.1 --port 15432 --username agentic_admin --owner agentic_owner --template template0 agentic_marketing_restore
    psql --host 127.0.0.1 --port 15432 --username agentic_admin --dbname agentic_marketing_restore -c "CREATE EXTENSION vector"
    pg_restore --list postgres.dump | awk '!/EXTENSION - vector/ && !/COMMENT - EXTENSION vector/' > restore.list
    pg_restore --host 127.0.0.1 --port 15432 --username agentic_owner --no-owner --no-acl --exit-on-error --use-list=restore.list --dbname agentic_marketing_restore postgres.dump
    psql --host 127.0.0.1 --port 15432 --username agentic_admin --dbname agentic_marketing_restore <<'SQL'
    GRANT USAGE ON SCHEMA public TO agentic_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agentic_app;
    GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO agentic_app;
    ALTER DEFAULT PRIVILEGES FOR ROLE agentic_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agentic_app;
    ALTER DEFAULT PRIVILEGES FOR ROLE agentic_owner IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO agentic_app;
    SQL
    mkdir -p /Users/lethanh/.local/share/agentic-marketing/restore-storage
    tar -xzf storage.tar.gz -C /Users/lethanh/.local/share/agentic-marketing/restore-storage

Then compare Alembic head using the migration-owner URL, representative row counts, stored object checksums, and API reads using the runtime role against the source. The extension filter prevents `pg_restore` from trying to create an already-installed `vector`; preserve the rest of the archive list. Do not print passwords in command lines. Same-machine backup protects against application-level mistakes but is not an off-machine disaster-recovery copy. Back up encryption keys separately.

Keep restored tables and `alembic_version` owned by `agentic_owner`. Granting CRUD to `agentic_app` does not grant migration rights. If `alembic upgrade head` reports that the migration role does not own an object, repeat the restore into a fresh database as `agentic_owner`, then reapply runtime grants and verify the migration head.

## Common recovery

- Database is not ready: inspect the PostgreSQL LaunchAgent error log and pg_isready. Do not reuse ports 5432/6379 as a workaround.
- Queue Redis is unavailable: PostgreSQL remains the durable job ledger; bring the isolated queue instance back, then let the scheduler redispatch eligible jobs.
- Cache Redis is unavailable: read from PostgreSQL; cache loss is acceptable.
- Migration head differs: stop serving application traffic, use the migration-owner credentials to run alembic upgrade head, then check schema parity before restart.
- A stale worker reports a lost lease: do not replay its write manually; allow the current claim/recovery path to finish.
- Backup restore fails checksum: reject that bundle and use the prior verified bundle.
