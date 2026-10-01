"""Real PostgreSQL suppression race/tenant/schema acceptance; synthetic data."""
import asyncio
import os
from datetime import timedelta

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from database.models import ResearchCommentSuppression, ResearchCommentVersion, new_id, utcnow
from services.api.db import FencedAsyncSession
from tests.test_comment_suppression import suppress
from tests.test_postgres_comment_quarantine import cleanup, configure
from tests.test_public_facebook_comments import seed_public, persist

TEST_URL = os.getenv("POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="Disposable POSTGRES_TEST_URL is not configured")


def test_postgres_suppression_races_with_new_observation_and_tenant_fk(monkeypatch):
    async def exercise():
        engine = create_async_engine(TEST_URL, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        configure(monkeypatch, sessions)
        seed, source = await seed_public(sessions)
        other, _ = await seed_public(sessions)
        try:
            observed = utcnow()
            await persist(seed, source, time=observed)
            async with sessions() as db:
                target = await db.scalar(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"],
                    ResearchCommentVersion.external_comment_id == "opaque-comment-one"))
                target_id = target.id
            results = await asyncio.gather(suppress(sessions, seed, target_id),
                persist(seed, source, time=observed + timedelta(seconds=1)),
                suppress(sessions, seed, target_id))
            assert results[0].suppression_id == results[2].suppression_id
            await persist(seed, source, time=observed + timedelta(seconds=2))
            async with sessions() as db:
                rows = (await db.scalars(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"],
                    ResearchCommentVersion.external_comment_id == "opaque-comment-one"))).all()
                assert rows and all(row.candidate_ciphertext is None and row.status == "suppressed" for row in rows)
                ledger = (await db.scalars(select(ResearchCommentSuppression).where(
                    ResearchCommentSuppression.company_id == seed["company_id"]))).all()
                assert len(ledger) == 1
                record = ledger[0]
                assert len((await db.scalars(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"],
                    ResearchCommentVersion.external_comment_id == "opaque-comment-two"))).all()) == 3
                db.add(ResearchCommentSuppression(id=new_id(), company_id=other["company_id"],
                    source_id=record.source_id, post_key_hash=record.post_key_hash,
                    external_comment_id="synthetic-wrong-tenant", reason="subject_request", created_by=other["user_id"]))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
        finally:
            await cleanup(sessions, seed)
            await cleanup(sessions, other)
            await engine.dispose()
    asyncio.run(exercise())


def test_suppression_schema_fresh_and_upgrade_match():
    fresh = os.getenv("POSTGRES_FRESH_TEST_URL")
    if not fresh:
        pytest.skip("POSTGRES_FRESH_TEST_URL is not configured")
    tables = ("research_comment_suppressions", "research_comment_versions", "research_comment_page_receipts")
    def snapshot(connection):
        inspector = inspect(connection)
        result = {}
        for table in tables:
            result[table] = {
                "columns": sorted((c["name"], str(c["type"]), c["nullable"], str(c["default"]))
                            for c in inspector.get_columns(table)),
                "checks": sorted((c["name"], c["sqltext"]) for c in inspector.get_check_constraints(table)),
                "unique": sorted((c["name"], c["column_names"]) for c in inspector.get_unique_constraints(table)),
                "indexes": sorted((c["name"], c["column_names"], c["unique"]) for c in inspector.get_indexes(table)),
                "foreign_keys": sorted((c["name"], c["constrained_columns"], c["referred_table"],
                    c["referred_columns"], c["options"]) for c in inspector.get_foreign_keys(table)),
            }
        return result
    async def read(url):
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.connect() as conn:
            result = await conn.run_sync(snapshot)
        await engine.dispose()
        return result
    assert asyncio.run(read(TEST_URL)) == asyncio.run(read(fresh))


def test_postgres_restore_older_backup_applies_latest_private_deletion_ledger(monkeypatch, tmp_path):
    import subprocess
    import uuid
    from pathlib import Path
    from sqlalchemy.engine import make_url
    from services.research.comment_deletion_ledger import apply_deletion_ledger, export_deletion_ledger
    from services.worker import research_tasks
    parsed = make_url(TEST_URL)
    tools = Path(os.getenv("PG_TEST_BIN", "/opt/homebrew/opt/postgresql@18/bin"))
    if not (tools / "pg_dump").exists():
        pytest.skip("PG_TEST_BIN backup/restore tools are not configured")
    restore_name = "comment_restore_" + uuid.uuid4().hex[:12]
    connection_args = ["-h", parsed.host, "-p", str(parsed.port or 5432), "-U", parsed.username]
    env = {**os.environ}
    if parsed.password:
        env["PGPASSWORD"] = parsed.password
    def run(command, *args):
        completed = subprocess.run([str(tools / command), *connection_args, *args], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert completed.returncode == 0, f"Disposable {command} failed (restricted output withheld)"
    async def exercise():
        engine = create_async_engine(TEST_URL, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        configure(monkeypatch, sessions)
        seed, source = await seed_public(sessions)
        restored_engine = None
        created = False
        try:
            observed = utcnow()
            await persist(seed, source, time=observed)
            async with sessions() as db:
                target = await db.scalar(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"],
                    ResearchCommentVersion.external_comment_id == "opaque-comment-one"))
                version_id = target.id
            dump = tmp_path / "pre-erasure.dump"
            dump.touch(mode=0o600)
            await asyncio.to_thread(run, "pg_dump", "-d", parsed.database, "-Fc", "-f", str(dump))
            await suppress(sessions, seed, version_id)
            async with sessions() as db:
                records = [r async for r in export_deletion_ledger(db)]
            assert records
            await asyncio.to_thread(run, "createdb", restore_name)
            created = True
            await asyncio.to_thread(run, "pg_restore", "-d", restore_name, "--no-owner", "--no-acl", "--exit-on-error", str(dump))
            restored_engine = create_async_engine(parsed.set(database=restore_name), poolclass=NullPool)
            restored = async_sessionmaker(restored_engine, expire_on_commit=False, class_=FencedAsyncSession)
            async with restored() as db:
                assert (await db.get(ResearchCommentVersion, version_id)).candidate_ciphertext is not None
                result = await apply_deletion_ledger(db, records)
                await db.commit()
                assert result["versions_erased"] == 1
                assert (await db.get(ResearchCommentVersion, version_id)).candidate_ciphertext is None
                assert (await apply_deletion_ledger(db, records))["versions_erased"] == 0
                await db.commit()
            monkeypatch.setattr(research_tasks, "SessionLocal", restored)
            await persist(seed, source, time=observed + timedelta(seconds=1))
            async with restored() as db:
                versions = (await db.scalars(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"],
                    ResearchCommentVersion.external_comment_id == "opaque-comment-one"))).all()
                assert len(versions) == 1 and versions[0].status == "suppressed"
        finally:
            if restored_engine is not None:
                await restored_engine.dispose()
            if created:
                await asyncio.to_thread(run, "dropdb", restore_name)
            await cleanup(sessions, seed)
            await engine.dispose()
    asyncio.run(exercise())
