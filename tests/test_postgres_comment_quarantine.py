"""PostgreSQL/Redis acceptance for synthetic comments; no live Meta or AI."""

import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from database.job_fencing import JobLeaseLost, _current_job_fence
from database.models import (
    Company, Job, ResearchCommentCheckpoint, ResearchCommentPageReceipt,
    ResearchCommentVersion, User, new_id, utcnow,
)
from services.api import job_service, meta_tokens
from services.api.db import FencedAsyncSession
from services.api.meta_client import MetaComment, MetaCommentsPage
from services.research import comment_quarantine as quarantine
from services.worker import research_comments as comments, research_tasks
from tests.helpers.comment_frontier import seed_comment_frontier


POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL")
POSTGRES_FRESH_TEST_URL = os.getenv("POSTGRES_FRESH_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="POSTGRES_TEST_URL is not configured")


def configure(monkeypatch, sessions):
    key = Fernet.generate_key().decode("ascii")
    config = SimpleNamespace(meta_token_encryption_key=key, meta_token_encryption_key_previous="")
    monkeypatch.setattr(quarantine, "settings", config)
    monkeypatch.setattr(meta_tokens, "settings", config)
    monkeypatch.setattr(comments, "SessionLocal", sessions)
    monkeypatch.setattr(research_tasks, "SessionLocal", sessions)


async def cleanup(sessions, seed):
    async with sessions() as db:
        # Decisions restrict the assessor reference, so remove the tenant first.
        await db.execute(delete(Company).where(Company.id == seed["company_id"]))
        await db.execute(delete(User).where(User.id == seed["user_id"]))
        await db.commit()


def received(seed, *, comment_id="456_1", text="Synthetic question", next_cursor=None, parent=None, replies=0):
    return MetaCommentsPage((MetaComment(comment_id, seed["post_id"], parent, text, utcnow(), None, replies, False),),
                            next_cursor, None, 0, next_cursor is None)


def test_postgres_atomic_comment_replay_tenant_24_hour_constraint_and_fencing(monkeypatch):
    async def exercise():
        engine = create_async_engine(POSTGRES_TEST_URL, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        configure(monkeypatch, sessions)
        seed = await seed_comment_frontier(sessions)
        other = await seed_comment_frontier(sessions)
        context_token = _current_job_fence.set(None)
        try:
            work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
            page = received(seed, text="Synthetic person@example.invalid", next_cursor="FIRST_CURSOR", replies=1)
            assert sorted(await asyncio.gather(comments.commit_comment_page(work, page),
                                               comments.commit_comment_page(work, page))) == [False, True]
            async with sessions() as db:
                row = await db.scalar(select(ResearchCommentVersion).where(ResearchCommentVersion.company_id == seed["company_id"]))
                assert row.status == "privacy_hold" and "person@example.invalid" not in row.candidate_ciphertext
                assert row.likes is None and row.expires_at - row.captured_at <= timedelta(hours=24)
                base = {column.name: getattr(row, column.name) for column in row.__table__.columns if column.name != "id"}
                saved_hash = row.content_hash
                assert len((await db.scalars(select(ResearchCommentPageReceipt).where(
                    ResearchCommentPageReceipt.company_id == seed["company_id"],
                ))).all()) == 1
            for invalid in (
                {**base, "content_hash": "b" * 64, "decision_id": other["decision_id"]},
                {**base, "content_hash": "c" * 64, "source_id": other["source_id"]},
                {**base, "content_hash": "d" * 64, "parent_key": "never-collected-parent"},
                {**base, "content_hash": "e" * 64, "expires_at": base["captured_at"] + timedelta(hours=25)},
                {**base, "content_hash": "f" * 64, "likes": -1},
            ):
                async with sessions() as db:
                    db.add(ResearchCommentVersion(**invalid))
                    with pytest.raises(IntegrityError):
                        await db.commit()
                    await db.rollback()
            next_work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
            job_id = new_id()
            async with sessions() as db:
                db.add(Job(id=job_id, company_id=seed["company_id"], created_by=seed["user_id"], kind="research_comments",
                           status="running", title="Synthetic fencing", claim_token="replacement-worker",
                           lease_until=utcnow() + timedelta(minutes=5), result={"source_id": seed["source_id"]}))
                await db.commit()
            _current_job_fence.set((job_id, "stale-worker"))
            with pytest.raises(JobLeaseLost):
                await comments.commit_comment_page(next_work, received(seed, text="Edited synthetic question"))
            _current_job_fence.set(None)
            async with sessions() as db:
                root = await db.get(ResearchCommentCheckpoint, seed["checkpoint_id"])
                assert root.cursor_after == "FIRST_CURSOR" and root.received_count == 1
            _current_job_fence.set((job_id, "replacement-worker"))
            assert await comments.commit_comment_page(next_work, received(seed, text="Edited synthetic question"))
            await comments._finish_comment_batch(job_id)
            _current_job_fence.set(None)
            async with sessions() as db:
                job = await db.get(Job, job_id)
                assert job.status == "queued" and job.claim_token != "replacement-worker"
                assert job.lease_until is None  # Continuation is immediately recoverable, not delayed by heartbeat.
                versions = (await db.scalars(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"],
                ))).all()
                assert len(versions) == 2 and saved_hash in {version.content_hash for version in versions}
                assert await comments.purge_expired_comment_quarantine(db, utcnow() + timedelta(days=2)) == 2
                await db.commit()
        finally:
            _current_job_fence.set(None)
            await cleanup(sessions, seed)
            await cleanup(sessions, other)
            await engine.dispose()
            _current_job_fence.reset(context_token)
    asyncio.run(exercise())


@pytest.mark.skipif(not POSTGRES_FRESH_TEST_URL, reason="POSTGRES_FRESH_TEST_URL is not configured")
def test_comment_quarantine_fresh_and_upgrade_definitions_match():
    async def schema(url):
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                assert (await connection.exec_driver_sql("SELECT version_num FROM alembic_version")).scalar_one() == "0029_comment_suppression"
                def fingerprint(sync):
                    inspector = inspect(sync)
                    result = {}
                    for table in ("research_comment_processing_decisions", "research_comment_versions", "research_comment_page_receipts"):
                        result[table] = {
                            "columns": sorted((column["name"], str(column["type"]), column["nullable"], column["default"])
                                              for column in inspector.get_columns(table)),
                            "fks": sorted(inspector.get_foreign_keys(table), key=lambda item: item["name"]),
                            "checks": sorted(inspector.get_check_constraints(table), key=lambda item: item["name"]),
                            "uniques": sorted(inspector.get_unique_constraints(table), key=lambda item: item["name"]),
                            "indexes": sorted(inspector.get_indexes(table), key=lambda item: item["name"]),
                        }
                    result["policy_tenant_key"] = next(row for row in inspector.get_unique_constraints("research_privacy_policy_revisions")
                                                       if row["name"] == "uq_research_privacy_policy_tenant_id")
                    return result
                return await connection.run_sync(fingerprint)
        finally:
            await engine.dispose()
    async def exercise():
        assert POSTGRES_TEST_URL != POSTGRES_FRESH_TEST_URL
        assert await schema(POSTGRES_TEST_URL) == await schema(POSTGRES_FRESH_TEST_URL)
    asyncio.run(exercise())


def test_postgres_redis_comment_job_is_recoverable_and_consumed_once(monkeypatch):
    queue = os.getenv("REDIS_QUEUE_TEST_URL")
    if not queue:
        pytest.skip("REDIS_QUEUE_TEST_URL is not configured")
    from celery.contrib.testing.worker import start_worker
    from services.api.config import settings
    from services.worker.celery_app import celery_app
    assert settings.database_url == POSTGRES_TEST_URL and settings.redis_url == queue and not settings.inline_jobs
    calls = []
    class SyntheticMetaClient:
        def __init__(self, *args):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def list_comments_page(self, post_id, **kwargs):
            calls.append(kwargs)
            parent = kwargs["parent_comment_id"]
            comment = MetaComment("456_1" if parent is None else "456_2", post_id, parent,
                                  "Synthetic contact: person@example.invalid", utcnow(), 0, 1 if parent is None else 0, False)
            return MetaCommentsPage((comment,), None, 1, 0, True)
    monkeypatch.setattr(comments, "MetaGraphClient", SyntheticMetaClient)
    async def exercise():
        engine = create_async_engine(POSTGRES_TEST_URL, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        configure(monkeypatch, sessions)
        seed = await seed_comment_frontier(sessions)
        try:
            async with sessions() as db:
                assert await comments.enqueue_comment_batches(db, utcnow()) == 1
                await db.commit()
                job = await db.scalar(select(Job).where(Job.company_id == seed["company_id"], Job.kind == "research_comments"))
            actual_dispatch = job_service.dispatch_research_comments_job
            async def failed_delivery(_job_id):
                return False
            monkeypatch.setattr(job_service, "dispatch_research_comments_job", failed_delivery)
            async with sessions() as db:
                await job_service.dispatch_queued_jobs(db)
                queued = await db.get(Job, job.id)
                assert queued.status == "queued" and queued.last_dispatch_error == "queue_unavailable"
                queued.lease_until = utcnow() - timedelta(seconds=1)
                await db.commit()
            monkeypatch.setattr(job_service, "dispatch_research_comments_job", actual_dispatch)
            with start_worker(celery_app, pool="solo", concurrency=1, queues=("agent",), perform_ping_check=False,
                              shutdown_timeout=10):
                async with sessions() as db:
                    assert await job_service.dispatch_queued_jobs(db) >= 1
                deadline = asyncio.get_running_loop().time() + 20
                while asyncio.get_running_loop().time() < deadline:
                    async with sessions() as db:
                        current = await db.get(Job, job.id)
                        if current.status in {"succeeded", "failed"}:
                            assert current.status == "succeeded", current.error
                            assert current.result["content_status"] == "privacy_hold"
                            assert current.dispatch_attempts == 2 and current.last_dispatch_error is None
                            assert len((await db.scalars(select(ResearchCommentVersion).where(
                                ResearchCommentVersion.company_id == seed["company_id"],
                            ))).all()) == 2
                            break
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Comment worker did not finish synthetic root/reply traversal")
                assert await actual_dispatch(job.id)
                await asyncio.sleep(0.2)
                assert len(calls) == 2
            async with sessions() as db:
                coverage = await comments.comment_frontier_coverage(db, company_id=seed["company_id"], observation_id=seed["observation_id"])
                assert coverage["accessible_edges_exhausted"] and not coverage["history_complete"]
                assert await comments.enqueue_comment_batches(db, utcnow()) == 0
        finally:
            await cleanup(sessions, seed)
            await engine.dispose()
    asyncio.run(exercise())
