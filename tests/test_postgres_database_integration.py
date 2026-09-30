"""Integration checks for constraints and stale-worker fencing on real PostgreSQL."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from redis.asyncio import Redis

from database.job_fencing import JobLeaseLost, _current_job_fence
from database.models import (
    AIUsageBudgetDay, AIUsageLedger, Base, Company, Job, MarketObservation,
    MarketEvidence, MarketEvidenceVersion, MetaPageGroup, ResearchCycle, ResearchSource,
    ResearchSourceErasure, ResearchSourceErasureObject, User, new_id, utcnow,
)
from services.api import db as api_db
from services.api import job_service
from services.api.db import FencedAsyncSession
from services.worker import research_erasure_tasks, research_tasks


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
                assert revision.scalar_one() == "0026_research_source_erasure"
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
                    owned_source_columns = {
                        column["name"] for column in inspector.get_columns("research_sources")
                    }
                    assert {
                        "owned_page_backfill_cursor", "owned_page_backfill_page_id",
                        "owned_page_backfill_window_start", "owned_page_backfill_complete",
                        "owned_page_backfill_window_complete",
                        "owned_page_backfill_pages_processed",
                    }.issubset(owned_source_columns)
                    research_cycle_columns = {
                        column["name"] for column in inspector.get_columns("research_cycles")
                    }
                    assert "collection_observed_at" in research_cycle_columns
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
                        "research_privacy_policy_revisions",
                        "research_source_erasures", "research_source_erasure_objects",
                    })
                    erasure_fks = inspector.get_foreign_keys("research_source_erasures")
                    assert {fk["name"] for fk in erasure_fks}.issuperset({
                        "fk_research_source_erasure_source_tenant",
                        "fk_research_source_erasure_job_tenant",
                    })
                    erasure_object_fks = inspector.get_foreign_keys(
                        "research_source_erasure_objects"
                    )
                    assert any(
                        fk["name"] == "fk_research_source_erasure_object_tenant"
                        and fk["constrained_columns"] == ["company_id", "erasure_id"]
                        for fk in erasure_object_fks
                    )
                    privacy_fks = inspector.get_foreign_keys("research_privacy_policy_revisions")
                    assert any(
                        fk["name"] == "fk_research_privacy_policy_source_tenant"
                        and fk["constrained_columns"] == ["company_id", "source_id"]
                        for fk in privacy_fks
                    )
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


def test_postgres_research_source_erasure_worker_deletes_raw_and_source_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        class RecordingStorage:
            deleted: list[str] = []

            async def delete(self, key: str) -> None:
                self.deleted.append(key)

        storage = RecordingStorage()
        monkeypatch.setattr(research_erasure_tasks, "SessionLocal", sessions)
        monkeypatch.setattr(research_erasure_tasks, "storage", storage)

        company_id, user_id, group_id = new_id(), new_id(), new_id()
        source_id, job_id, erasure_id = new_id(), new_id(), new_id()
        evidence_id, version_id, observation_id = new_id(), new_id(), new_id()
        raw_key = f"research-purge-integration/{new_id()}.json"
        observed_at = utcnow()
        slug = f"research-purge-{uuid.uuid4().hex[:16]}"

        try:
            async with sessions() as db:
                db.add_all([
                    Company(id=company_id, name="Research purge integration", slug=slug),
                    User(
                        id=user_id, email=f"purge-{uuid.uuid4().hex}@example.invalid",
                        full_name="Disposable integration user", password_hash="not-a-login",
                    ),
                ])
                await db.flush()
                db.add(MetaPageGroup(
                    id=group_id, company_id=company_id, name="Integration source",
                    industry="test", region="test",
                ))
                db.add(ResearchSource(
                    id=source_id, company_id=company_id, group_id=group_id,
                    source_type="website", name="Disposable source",
                    url="https://example.invalid/research", normalized_url="https://example.invalid/research",
                    created_by=user_id, active=False, schedule_enabled=False,
                ))
                db.add(Job(
                    id=job_id, company_id=company_id, created_by=user_id,
                    kind="research_source_erasure", title="Purge disposable source", status="queued",
                ))
                await db.flush()
                db.add(ResearchSourceErasure(
                    id=erasure_id, company_id=company_id, source_id=source_id,
                    job_id=job_id, requested_by=user_id, status="queued",
                ))
                db.add(MarketEvidence(
                    id=evidence_id, company_id=company_id, group_id=group_id,
                    source_id=source_id, canonical_url="https://example.invalid/research/item",
                    title="Disposable evidence", text="fixture only", content_hash="a" * 64,
                    first_seen_at=observed_at, last_seen_at=observed_at,
                ))
                await db.flush()
                db.add(MarketEvidenceVersion(
                    id=version_id, company_id=company_id, evidence_id=evidence_id,
                    content_hash="a" * 64, parser_version="integration-v1",
                    title="Disposable evidence", text="fixture only", captured_at=observed_at,
                ))
                await db.flush()
                db.add(MarketObservation(
                    id=observation_id, company_id=company_id, evidence_id=evidence_id,
                    evidence_version_id=version_id, observed_at=observed_at,
                    raw_object_key=raw_key, raw_sha256="b" * 64,
                ))
                await db.commit()

            await research_erasure_tasks.research_source_erasure_task_async(job_id)

            async with sessions() as db:
                source = await db.get(ResearchSource, source_id)
                job = await db.get(Job, job_id)
                request = await db.get(ResearchSourceErasure, erasure_id)
                assert source is not None and source.status == "erased" and not source.active
                assert job is not None and job.status == "succeeded"
                assert request is not None and request.status == "completed"
                assert await db.get(MarketEvidence, evidence_id) is None
                assert await db.get(MarketEvidenceVersion, version_id) is None
                assert await db.get(MarketObservation, observation_id) is None
                assert await db.scalar(select(ResearchSourceErasureObject.id).where(
                    ResearchSourceErasureObject.erasure_id == erasure_id,
                )) is None
                assert storage.deleted == [raw_key]
        finally:
            async with sessions() as db:
                # Keep the disposable PostgreSQL database reusable for later
                # integration runs and remove only this test's synthetic rows.
                await db.execute(delete(Job).where(Job.id == job_id))
                await db.execute(delete(Company).where(Company.id == company_id))
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
            await engine.dispose()

    asyncio.run(run())


def test_ai_budget_reservations_are_atomic_and_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from services.worker import ai_budget

    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(api_db, "SessionLocal", sessions)
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

            interactive = await ai_budget.reserve_interactive_request(
                company_id=company_id,
                request_key="interactive:campaign-plan:fixture-job",
                provider="deepseek",
                model="deepseek-flash",
                operation="campaign_plan",
            )
            assert interactive.status == "reserved"
            interactive_settlement = await ai_budget.settle_interactive_request(
                company_id=company_id,
                reservation=interactive,
                provider="deepseek",
                model="deepseek-flash",
                input_tokens=100,
                output_tokens=10,
                result_json={"output": {"proposal": "fixture"}},
            )
            assert interactive_settlement == "succeeded"
            interactive_replay = await ai_budget.reserve_interactive_request(
                company_id=company_id,
                request_key="interactive:campaign-plan:fixture-job",
                provider="deepseek",
                model="deepseek-flash",
                operation="campaign_plan",
            )
            assert interactive_replay.status == "cached"
            assert interactive_replay.cached_result == {"output": {"proposal": "fixture"}}
            async with sessions() as db:
                day = (await db.scalars(select(AIUsageBudgetDay).where(
                    AIUsageBudgetDay.company_id == company_id,
                ))).one()
                interactive_row = await db.get(AIUsageLedger, interactive_replay.ledger_id)
                assert day.reserved_micro_usd == amount
                assert day.spent_micro_usd == 42
                assert interactive_row is not None
                assert interactive_row.budget_class == "interactive"
                assert interactive_row.actual_micro_usd == 42
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_raw_research_object_has_committed_24_hour_expiry_before_storage_put(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
        observed: dict[str, object] = {}

        class AmbiguousStorage:
            async def put(self, key: str, _body: bytes) -> None:
                async with sessions() as db:
                    observation = await db.scalar(select(MarketObservation).where(
                        MarketObservation.raw_object_key == key,
                    ))
                    assert observation is not None
                    assert observation.raw_expires_at is not None
                    observed["key"] = key
                    observed["expires_at"] = observation.raw_expires_at
                raise OSError("simulated ambiguous storage timeout")

        monkeypatch.setattr(research_tasks, "storage", AmbiguousStorage())
        company_id: str | None = None
        user_id: str | None = None
        stored_at = datetime.now(timezone.utc)
        try:
            async with sessions() as db:
                company = Company(
                    name="Raw retention test", slug=f"raw-{uuid.uuid4().hex[:16]}",
                )
                user = User(
                    email=f"raw-{uuid.uuid4().hex}@example.invalid",
                    full_name="Raw retention test",
                    password_hash="test-only-not-a-login",
                )
                db.add_all([company, user])
                await db.flush()
                group = MetaPageGroup(
                    company_id=company.id, name="Research", industry="unknown",
                    region="unknown", locale="vi-VN", keywords_json=[], active=True,
                )
                db.add(group)
                await db.flush()
                source = ResearchSource(
                    company_id=company.id, group_id=group.id, source_type="website",
                    name="Example source", url="https://example.com/",
                    normalized_url="https://example.com/", created_by=user.id,
                    collection_mode="public_web", collection_post_limit=1,
                    schedule_enabled=False,
                )
                db.add(source)
                await db.commit()
                company_id, user_id = company.id, user.id

            seven_days_old = stored_at - timedelta(days=7)
            async with sessions() as db:
                source = await db.scalar(select(ResearchSource).where(
                    ResearchSource.company_id == company_id,
                ))
                assert source is not None
                await research_tasks._persist_evidence(
                    company_id=company_id,
                    group_id=source.group_id,
                    source=source,
                    url="https://example.com/page",
                    title="Example",
                    text="Public research text",
                    published_at=seven_days_old,
                    metrics={},
                    comments=[],
                    raw_body=b"temporary raw page payload",
                    observed_at=seven_days_old,
                )

            expiry = observed.get("expires_at")
            assert isinstance(expiry, datetime)
            assert abs((expiry - stored_at).total_seconds() - 24 * 60 * 60) < 5
            async with sessions() as db:
                observation = await db.scalar(select(MarketObservation).where(
                    MarketObservation.raw_object_key == observed.get("key"),
                ))
                assert observation is not None
                assert observation.raw_expires_at == expiry
        finally:
            async with sessions() as db:
                if company_id is not None:
                    await db.execute(delete(Company).where(Company.id == company_id))
                if user_id is not None:
                    await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
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


def test_postgres_competing_workers_only_claim_a_research_job_once(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
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


def test_postgres_celery_worker_consumes_committed_research_job() -> None:
    queue_url = os.getenv("REDIS_QUEUE_TEST_URL")
    broker_url = os.getenv("REDIS_URL")
    if not queue_url or not broker_url:
        pytest.skip("REDIS_QUEUE_TEST_URL and REDIS_URL are required")
    if broker_url != queue_url:
        pytest.fail("REDIS_URL must point to the isolated REDIS_QUEUE_TEST_URL")

    from celery.contrib.testing.worker import start_worker
    from services.worker.celery_app import celery_app

    assert celery_app.conf.broker_url == broker_url

    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        marker = uuid.uuid4().hex
        company_id = new_id()
        user_id = new_id()
        group_id = new_id()
        job_id = new_id()
        try:
            async with sessions() as db:
                company = Company(
                    id=company_id,
                    name="Celery worker integration",
                    slug=f"worker-{marker[:16]}",
                    page_id=f"worker-page-{marker[:16]}",
                    page_connection_state="active",
                )
                user = User(
                    id=user_id,
                    email=f"worker-{marker}@example.invalid",
                    full_name="Worker integration",
                    password_hash="test-only-not-a-login",
                )
                group = MetaPageGroup(
                    id=group_id,
                    company_id=company_id,
                    name="Nghiên cứu integration",
                    industry="Chưa xác định",
                    region="Chưa xác định",
                    locale="vi-VN",
                    keywords_json=[],
                    active=True,
                )
                job = Job(
                    id=job_id,
                    company_id=company_id,
                    created_by=user_id,
                    kind="market_research",
                    title="Consume committed job through Celery",
                    status="queued",
                    progress=0,
                    result={"group_id": group_id},
                    idempotency_key=f"celery-worker:{marker}",
                )
                cycle = ResearchCycle(
                    id=new_id(),
                    company_id=company_id,
                    group_id=group_id,
                    job_id=job_id,
                    cycle_key=f"celery-worker:{marker}",
                    status="queued",
                    source_results_json=[],
                    collection_observed_at=utcnow(),
                )
                db.add_all([company, user])
                await db.flush()
                db.add(group)
                await db.flush()
                db.add(job)
                await db.flush()
                db.add(cycle)
                await db.commit()

            with start_worker(
                celery_app,
                pool="solo",
                concurrency=1,
                queues=("agent",),
                perform_ping_check=False,
                shutdown_timeout=10,
            ):
                assert await job_service.dispatch_research_job(job_id) is True
                deadline = asyncio.get_running_loop().time() + 20
                while asyncio.get_running_loop().time() < deadline:
                    async with sessions() as db:
                        job = await db.get(Job, job_id)
                        if job is not None and job.status in {"succeeded", "failed"}:
                            assert job.status == "succeeded", job.error
                            assert job.attempts == 1
                            assert job.result["analysis_status"] == "not_run_no_new_evidence"
                            cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id))
                            assert cycle is not None and cycle.status == "completed_no_data"
                            break
                    await asyncio.sleep(0.2)
                else:
                    pytest.fail("Celery worker did not complete the committed no-source research job")
        finally:
            async with sessions() as db:
                job = await db.get(Job, job_id)
                if job is not None:
                    await db.delete(job)
                company = await db.get(Company, company_id)
                if company is not None:
                    await db.delete(company)
                user = await db.get(User, user_id)
                if user is not None:
                    await db.delete(user)
                await db.commit()
            await engine.dispose()

    asyncio.run(run())
