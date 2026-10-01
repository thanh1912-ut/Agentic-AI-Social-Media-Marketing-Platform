#!/usr/bin/env python3
"""Export/apply restricted comment deletion NDJSON, without printing its data."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from services.research.comment_deletion_ledger import DeletionLedgerRecord, apply_deletion_ledger, export_deletion_ledger

MAX_LEDGER_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 100_000


async def run(mode: str, path: Path):
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("PostgreSQL DATABASE_URL is required; its value will not be logged")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            if mode == "export":
                # Exclusive create, no symlink following, private from the first
                # byte. Exports belong outside Git and outside an old backup.
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                records = 0
                total_bytes = 0
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as output:
                        async for record in export_deletion_ledger(db):
                            line = record.model_dump_json() + "\n"
                            total_bytes += len(line.encode("utf-8"))
                            if records >= MAX_RECORDS or total_bytes > MAX_LEDGER_BYTES:
                                raise ValueError("ledger_limit_exceeded")
                            output.write(line)
                            records += 1
                        output.flush()
                        os.fsync(output.fileno())
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                return {"exported": records}
            if path.stat().st_size > MAX_LEDGER_BYTES:
                raise ValueError("ledger_limit_exceeded")
            records = []
            with path.open(encoding="utf-8") as source:
                for line in source:
                    if len(line) > 8192 or len(records) >= MAX_RECORDS:
                        raise ValueError("ledger_limit_exceeded")
                    records.append(DeletionLedgerRecord.model_validate_json(line))
            result = await apply_deletion_ledger(db, records)
            await db.commit()
            return result
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("export", "apply"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.mode, args.path))
    except Exception:
        # Validation exceptions can include the full input record. Never print
        # exception repr/tracebacks containing restricted ledger IDs or DSNs.
        print("Ledger operation failed; check schema, tenant mappings, limits and file permissions.", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
