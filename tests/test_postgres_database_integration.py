"""Integration checks for constraints and stale-worker fencing on real PostgreSQL."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from redis.asyncio import Redis

from database.job_fencing import JobLeaseLost, _current_job_fence
from database.models import AIUsageBudgetDay, AIUsageLedger, Base, Company, Job, User
from services.api import job_service
from services.api.db import FencedAsyncSession
from services.worker import research_tasks


POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="POSTGRES_TEST_URL is not configured")


def test_postgres_migrations_constraints_vector_and_job_fencing() -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        try:
            async with engine.connect() as connection:
                revision = await connection.exec_driver_sql(
                    "SELECT version_num FROM alembic_version ORDER BY version_num LIMIT 1"
                )
                assert revision.scalar_one() == "0022_ai_usage_budget"
                extension = await connection.exec_driver_sql(
                    "SELECT extversion FROM pg_extension WHERE extname='vector'"
                )
                assert extension.scalar_one()

                def assert_schema(sync_connection) -> None:
                    inspector = inspect(sync_connection)
                    assert set(Base.metadata.tables).issubset(set(inspector.get_table_names()))
                    company_columns = {
                        column["name"] for column in inspector.get_columns("companies")
                    }
                    assert {
                        "page_id", "page_avatar_url", "page_connection_state",
                    }.issubset(company_columns)
                    assert any(
                        item["name"] == "ix_companies_page_id"
                        and item.get("unique") is True
                        and item["column_names"] == ["page_id"]
                        for item in inspector.get_indexes("companies")
                    )
                    report_evidence_columns = {
                        column["name"] for column in inspector.get_columns("market_report_evidence")
                    }
                    assert "created_at" in report_evidence_columns
                    run_fks = inspector.get_foreign_keys("web_crawl_runs")
                    assert any(
                        fk["name"] == "fk_web_crawl_run_job_tenant"
                        and fk["constrained_columns"] == ["company_id", "job_id"]
                        for fk in run_fks
                    )
                    page_fks = inspector.get_foreign_keys("web_crawl_pages")
                    assert {fk["name"] for fk in page_fks}.issuperset(
                        {
                            "fk_web_crawl_page_evidence_version_tenant",
                            "fk_web_crawl_page_observation_version_tenant",
                        }
                    )
                    assert {item["name"] for item in inspector.get_check_constraints("web_crawl_pages")} >= {
                        "ck_web_crawl_page_evidence_refs_all_or_none"
                    }
                    assert set(inspector.get_table_names()).issuperset({
                        "post_content_reviews", "scheduled_meta_publications",
                        "mailguard_integrations", "mailguard_tracking_references",
                        "mailguard_conversion_events", "ai_usage_budget_days", "ai_usage_ledger",
                    })
                    review_fks = inspector.get_foreign_keys("post_content_reviews")
                    assert any(fk["name"] == "fk_post_content_review_version_tenant" for fk in review_fks)
                    schedule_fks = inspector.get_foreign_keys("scheduled_meta_publications")
                    assert any(fk["name"] == "fk_scheduled_meta_connection_tenant_page" for fk in schedule_fks)
                    event_fks = inspector.get_foreign_keys("mailguard_conversion_events")
                    assert {fk["name"] for fk in event_fks}.issuperset({
                        "fk_mailguard_event_integration_tenant", "fk_mailguard_event_tracking_tenant",
                    })

                await connection.run_sync(assert_schema)
                snapshot_guard = await connection.exec_driver_sql(
                    "SELECT tgtype FROM pg_trigger "
                    "WHERE tgrelid='web_entity_snapshots'::regclass "
                    "AND tgname='trg_web_entity_snapshot_delete_guard' AND NOT tgisinternal"
                )
                event_mask = snapshot_guard.scalar_one()
                assert event_mask & 8  # DELETE
                assert event_mask & 16  # UPDATE

            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                company = Company(name="Fence integration", slug=f"fence-{uuid.uuid4().hex[:16]}")
                user = User(
                    email=f"fence-{uuid.uuid4().hex}@example.invalid",
                    full_name="Fence test",
                    password_hash="test-only-not-a-login",
                )
                db.add_all([company, user])
                await db.flush()
                job = Job(
                    company_id=company.id,
                    created_by=user.id,
                    kind="document_ingest",
                    title="keep the replacement worker value",
                    status="running",
                    claim_token="old-claim",
                    lease_until=datetime.now(timezone.utc) + timedelta(minutes=5),
                    attempts=2,
                )
                db.add(job)
                await db.commit()
                job_id = job.id

            stale_session = FencedAsyncSession(engine, expire_on_commit=False)
            fence_context = _current_job_fence.set((job_id, "old-claim"))
            try:
                stale_job = await stale_session.get(Job, job_id)
                assert stale_job is not None
                stale_job.title = "stale worker must not commit"
                async with sessions() as current_session:
                    await current_session.execute(
                        update(Job).where(Job.id == job_id).values(claim_token="current-claim")
                    )
                    await current_session.commit()
                with pytest.raises(JobLeaseLost):
                    await stale_session.commit()
            finally:
                _current_job_fence.reset(fence_context)
                await stale_session.close()

            async with sessions() as db:
                current = await db.scalar(select(Job).where(Job.id == job_id))
                assert current is not None
                assert current.title == "keep the replacement worker value"
                assert current.claim_token == "current-claim"
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_ai_budget_reservations_are_atomic_and_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from services.worker import ai_budget

    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(ai_budget, "SessionLocal", sessions)
        monkeypatch.setattr(ai_budget, "settings", SimpleNamespace(
            llm_max_input_chars=100,
            llm_max_tokens=100,
            auto_ai_daily_budget_micro_usd=40_000,
        ))
        try:
            async with sessions() as db:
                company = Company(name="Budget race", slug=f"budget-{uuid.uuid4().hex[:16]}")
                db.add(company)
                await db.commit()
                company_id = company.id

            reservations = await asyncio.gather(*(
                ai_budget.reserve_automatic_request(
                    company_id=company_id,
                    request_key=f"race:{index}",
                    provider="deepseek",
                    model="deepseek-flash",
                    operation="test_automatic_analysis",
                )
                for index in range(6)
            ))
            accepted = [item for item in reservations if item.status == "reserved"]
            deferred = [item for item in reservations if item.status == "deferred_budget"]
            assert len(accepted) == 2
            assert len(deferred) == 4
            amount = accepted[0].reserved_micro_usd
            assert amount * 2 <= 40_000

            replay = await ai_budget.reserve_automatic_request(
                company_id=company_id,
                request_key=accepted[0].request_key,
                provider="deepseek",
                model="deepseek-flash",
                operation="test_automatic_analysis",
            )
            assert replay.status == "uncertain"
            assert replay.ledger_id == accepted[0].ledger_id

            settled = await ai_budget.settle_automatic_request(
                company_id=company_id,
                reservation=accepted[0],
                provider="deepseek",
                model="deepseek-flash",
                input_tokens=100,
                output_tokens=10,
                result_json={"report": {"headline": "fixture"}, "model_name": "deepseek-flash"},
            )
            assert settled == "succeeded"
            cached = await ai_budget.reserve_automatic_request(
                company_id=company_id,
                request_key=accepted[0].request_key,
                provider="deepseek",
                model="deepseek-flash",
                operation="test_automatic_analysis",
            )
            assert cached.status == "cached"
            assert cached.cached_result == {
                "report": {"headline": "fixture"}, "model_name": "deepseek-flash",
            }

            async with sessions() as db:
                day = (await db.scalars(select(AIUsageBudgetDay).where(
                    AIUsageBudgetDay.company_id == company_id,
                ))).one()
                assert day.reserved_micro_usd == amount
                assert day.spent_micro_usd == 42
                rows = (await db.scalars(select(AIUsageLedger).where(
                    AIUsageLedger.company_id == company_id,
                ))).all()
                assert len(rows) == 2
                assert sum(row.reserved_micro_usd for row in rows) <= 40_000
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_stale_worker_cannot_commit_after_job_is_requeued_with_same_claim_token() -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                company = Company(name="Expired lease", slug=f"expired-{uuid.uuid4().hex[:16]}")
                user = User(
                    email=f"expired-{uuid.uuid4().hex}@example.invalid",
                    full_name="Lease test",
                    password_hash="test-only-not-a-login",
                )
                db.add_all([company, user])
                await db.flush()
                job = Job(
                    company_id=company.id,
                    created_by=user.id,
                    kind="document_ingest",
                    title="original title",
                    status="running",
                    claim_token="same-claim",
                    lease_until=datetime.now(timezone.utc) + timedelta(minutes=5),
                    attempts=1,
                )
                db.add(job)
                await db.commit()
                job_id = job.id

            stale_session = FencedAsyncSession(engine, expire_on_commit=False)
            fence_context = _current_job_fence.set((job_id, "same-claim"))
            try:
                stale_job = await stale_session.get(Job, job_id)
                assert stale_job is not None
                stale_job.title = "stale overwrite"
                async with sessions() as current_session:
                    await current_session.execute(
                        update(Job).where(Job.id == job_id).values(
                            status="queued", lease_until=None,
                        )
                    )
                    await current_session.commit()
                with pytest.raises(JobLeaseLost):
                    await stale_session.commit()
            finally:
                _current_job_fence.reset(fence_context)
                await stale_session.close()

            async with sessions() as db:
                current = await db.get(Job, job_id)
                assert current is not None
                assert current.title == "original title"
                assert current.status == "queued"
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_queue_and_cache_use_distinct_redis_instances_with_ttl() -> None:
    queue_url = os.getenv("REDIS_QUEUE_TEST_URL")
    cache_url = os.getenv("REDIS_CACHE_TEST_URL")
    if not queue_url or not cache_url:
        pytest.skip("Redis integration URLs are not configured")
    assert queue_url != cache_url

    async def run() -> None:
        queue = Redis.from_url(queue_url)
        cache = Redis.from_url(cache_url)
        marker = f"codex-db-check:{uuid.uuid4().hex}"
        try:
            await queue.set(marker, "queue", ex=30)
            await cache.set(marker, "cache", ex=60)
            assert await queue.get(marker) == b"queue"
            assert await cache.get(marker) == b"cache"
            assert await queue.ttl(marker) > 0
            assert await cache.ttl(marker) > 0
        finally:
            await queue.delete(marker)
            await cache.delete(marker)
            await queue.aclose()
            await cache.aclose()

    asyncio.run(run())


def test_postgres_competing_workers_only_claim_a_research_job_once() -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                page_id = f"test-{uuid.uuid4().hex[:20]}"
                company = Company(
                    name="Claim race",
                    slug=f"claim-{uuid.uuid4().hex[:16]}",
                    page_id=page_id,
                    page_connection_state="active",
                )
                user = User(
                    email=f"claim-{uuid.uuid4().hex}@example.invalid",
                    full_name="Claim test",
                    password_hash="test-only-not-a-login",
                )
                db.add_all([company, user])
                await db.flush()
                job = Job(
                    company_id=company.id,
                    created_by=user.id,
                    kind="market_research",
                    title="claim exactly once",
                    status="queued",
                    progress=0,
                    result={"group_id": "test-group"},
                    idempotency_key=f"claim:{uuid.uuid4().hex}",
                )
                db.add(job)
                await db.commit()
                job_id = job.id

            claims = await asyncio.gather(
                research_tasks._claim(job_id),
                research_tasks._claim(job_id),
            )
            assert sorted(claims) == [False, True]
            async with sessions() as db:
                claimed = await db.get(Job, job_id)
                assert claimed is not None
                assert claimed.status == "running"
                assert claimed.attempts == 1
                assert claimed.claim_token
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_postgres_committed_job_survives_queue_dispatch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                # This test intentionally calls the production dispatcher,
                # which scans all queued jobs. Clear leftovers from earlier
                # runs in the disposable PostgreSQL test database first.
                await db.execute(
                    update(Job)
                    .where(Job.status == "queued")
                    .values(status="cancelled", finished_at=datetime.now(timezone.utc), lease_until=None)
                )
                company = Company(name="Queue retry", slug=f"queue-{uuid.uuid4().hex[:16]}")
                user = User(
                    email=f"queue-{uuid.uuid4().hex}@example.invalid",
                    full_name="Queue test",
                    password_hash="test-only-not-a-login",
                )
                db.add_all([company, user])
                await db.flush()
                job = Job(
                    company_id=company.id,
                    created_by=user.id,
                    kind="market_research",
                    title="recover after Redis outage",
                    status="queued",
                    progress=0,
                    result={"group_id": "test-group"},
                    idempotency_key=f"queue:{uuid.uuid4().hex}",
                )
                db.add(job)
                await db.commit()
                job_id = job.id

            async def dispatch_unavailable(_job_id: str) -> bool:
                return False

            monkeypatch.setattr(job_service, "dispatch_research_job", dispatch_unavailable)
            async with sessions() as db:
                assert await job_service.dispatch_queued_jobs(db) == 0
            async with sessions() as db:
                queued = await db.get(Job, job_id)
                assert queued is not None
                assert queued.status == "queued"
                assert queued.dispatch_attempts == 1
                assert queued.last_dispatch_error == "queue_unavailable"
                assert queued.lease_until is not None

            async with sessions() as db:
                await db.execute(update(Job).where(Job.id == job_id).values(
                    lease_until=datetime.now(timezone.utc) - timedelta(seconds=1),
                ))
                await db.commit()

            async def dispatch_recovered(_job_id: str) -> bool:
                return True

            monkeypatch.setattr(job_service, "dispatch_research_job", dispatch_recovered)
            async with sessions() as db:
                assert await job_service.dispatch_queued_jobs(db) == 1
            async with sessions() as db:
                recovered = await db.get(Job, job_id)
                assert recovered is not None
                assert recovered.status == "queued"
                assert recovered.attempts == 0
                assert recovered.dispatch_attempts == 2
                assert recovered.last_dispatch_error is None
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_production_dispatcher_places_durable_job_on_isolated_redis_queue() -> None:
    queue_url = os.getenv("REDIS_QUEUE_TEST_URL")
    broker_url = os.getenv("REDIS_URL")
    if not queue_url or not broker_url:
        pytest.skip("REDIS_QUEUE_TEST_URL and REDIS_URL are required")
    if broker_url != queue_url:
        pytest.fail("REDIS_URL must point to the isolated REDIS_QUEUE_TEST_URL")

    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        redis = Redis.from_url(queue_url)
        marker = uuid.uuid4().hex
        job_id: str | None = None
        company_id: str | None = None
        user_id: str | None = None
        queued_message: bytes | None = None
        try:
            from services.worker.celery_app import celery_app

            assert celery_app.conf.broker_url == broker_url
            async with sessions() as db:
                company = Company(
                    name="Celery dispatch test",
                    slug=f"celery-{marker[:16]}",
                    page_id=f"test-page-{marker[:16]}",
                    page_connection_state="active",
                )
                user = User(
                    email=f"celery-{marker}@example.invalid",
                    full_name="Queue test",
                    password_hash="test-only-not-a-login",
                )
                db.add_all([company, user])
                await db.flush()
                company_id = company.id
                user_id = user.id
                job = Job(
                    company_id=company.id,
                    created_by=user.id,
                    kind="market_research",
                    title="Redis dispatcher integration",
                    status="queued",
                    result={"group_id": "unused-isolated-test-group"},
                    idempotency_key=f"celery:{marker}",
                )
                db.add(job)
                await db.commit()
                job_id = job.id

            assert await job_service.dispatch_research_job(job_id) is True
            messages = await redis.lrange("agent", 0, -1)
            for message in messages:
                try:
                    envelope = json.loads(message)
                    body = envelope.get("body")
                    if not isinstance(body, str):
                        continue
                    padded = body + "=" * (-len(body) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
                    if job_id in json.dumps(payload):
                        queued_message = message
                        break
                except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
                    continue
            assert queued_message is not None, "committed job ID was not found in the Redis agent queue"
        finally:
            if queued_message is not None:
                await redis.lrem("agent", 1, queued_message)
            await redis.aclose()
            async with sessions() as db:
                if job_id is not None:
                    job = await db.get(Job, job_id)
                    if job is not None:
                        await db.delete(job)
                if company_id is not None:
                    company = await db.get(Company, company_id)
                    if company is not None:
                        await db.delete(company)
                if user_id is not None:
                    user = await db.get(User, user_id)
                    if user is not None:
                        await db.delete(user)
                await db.commit()
            await engine.dispose()

    asyncio.run(run())
