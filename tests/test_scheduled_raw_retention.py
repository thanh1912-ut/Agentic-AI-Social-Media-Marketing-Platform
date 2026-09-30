"""Focused tests for expiry cleanup; storage failures must remain retryable."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from services.worker import scheduled_jobs


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self.rows = rows
        self.flush_count = 0

    async def scalars(self, _statement):
        return _Rows(self.rows)

    async def flush(self):
        self.flush_count += 1


class _Storage:
    def __init__(self, failing_keys=()):
        self.failing_keys = set(failing_keys)
        self.deleted = []

    async def delete(self, key):
        if key in self.failing_keys:
            raise OSError("simulated object-store failure")
        self.deleted.append(key)


def test_expired_raw_cleanup_clears_only_successful_deletions(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(raw_object_key="expired-ok", raw_expires_at=now),
        SimpleNamespace(raw_object_key="expired-failed", raw_expires_at=now),
    ]
    db = _Db(rows)
    storage = _Storage(failing_keys={"expired-failed"})
    monkeypatch.setattr(scheduled_jobs, "storage", storage)

    deleted = asyncio.run(scheduled_jobs._purge_expired_raw(db, now))

    assert deleted == 1
    assert storage.deleted == ["expired-ok"]
    assert rows[0].raw_object_key is None and rows[0].raw_expires_at is None
    assert rows[1].raw_object_key == "expired-failed"
    assert rows[1].raw_expires_at == now
    assert db.flush_count == 1


def test_expired_raw_cleanup_does_not_flush_when_storage_keeps_failing(monkeypatch):
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(raw_object_key="still-pending", raw_expires_at=now)
    db = _Db([row])
    monkeypatch.setattr(scheduled_jobs, "storage", _Storage(failing_keys={"still-pending"}))

    deleted = asyncio.run(scheduled_jobs._purge_expired_raw(db, now))

    assert deleted == 0
    assert row.raw_object_key == "still-pending"
    assert row.raw_expires_at == now
    assert db.flush_count == 0
