"""Integration checks for constraints and stale-worker fencing on real PostgreSQL."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from database.job_fencing import JobLeaseLost, _current_job_fence
from database.models import (
    AIUsageBudgetDay, AIUsageLedger, Base, Company, Job, JobEvent, JobStep, MarketObservation,
    MarketEvidence, MarketEvidenceVersion, MarketReport, Membership, MetaPageConnection,
    MetaPageGroup, ResearchCycle, ResearchPrivacyPolicyRevision, ResearchSource,
    ResearchSourceErasure, ResearchSourceErasureObject, User, new_id, utcnow,
)
from services.api import db as api_db
from services.api import job_service
from services.api.db import FencedAsyncSession
from services.worker import research_erasure_tasks, research_tasks
from services.worker import scheduled_jobs


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


def test_postgres_facebook_evidence_persistence_enforces_privacy_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(research_tasks, "SessionLocal", sessions)

        class NoFacebookStorage:
            async def put(self, *_args, **_kwargs) -> None:
                raise AssertionError("Facebook raw content must not be stored")

        monkeypatch.setattr(research_tasks, "storage", NoFacebookStorage())
        company_id, user_id, group_id, source_id = new_id(), new_id(), new_id(), new_id()
        slug = f"facebook-privacy-{uuid.uuid4().hex[:16]}"
        try:
            async with sessions() as db:
                db.add_all([
                    Company(id=company_id, name="Facebook privacy fixture", slug=slug),
                    User(
                        id=user_id, email=f"fb-privacy-{uuid.uuid4().hex}@example.invalid",
                        full_name="Disposable privacy fixture", password_hash="not-a-login",
                    ),
                ])
                await db.flush()
                db.add(MetaPageGroup(
                    id=group_id, company_id=company_id, name="Research",
                    industry="test", region="test",
                ))
                await db.flush()
                source = ResearchSource(
                    id=source_id, company_id=company_id, group_id=group_id,
                    source_type="competitor_facebook_page", name="Public Page",
                    url="https://www.facebook.com/privacy-fixture",
                    normalized_url="https://www.facebook.com/privacy-fixture",
                    created_by=user_id, active=True,
                )
                db.add(source)
                await db.commit()

            async with sessions() as db:
                source = await db.get(ResearchSource, source_id)
                assert source is not None
            evidence_id = await research_tasks._persist_evidence(
                company_id=company_id,
                group_id=group_id,
                source=source,
                url="https://www.facebook.com/privacy-fixture/posts/42",
                title="Gọi 0901 234 567",
                text="Gửi email person@example.test; nhà riêng: 12/5 Đường Cá Nhân, Quận 1",
                published_at=None,
                metrics={
                    "comments": 1,
                    "reactions": 19,
                    "shares": 1.5,
                    "comment_text": "Do not store this nested personal text",
                    "authors": [{"name": "Private Person", "profile_url": "https://facebook.com/private-person"}],
                    "raw_response": {"comments": ["private@example.invalid"]},
                    "link_url": "https://news.example/story?email=private@example.invalid&token=signed",
                    "attachments": [{
                        "kind": "image", "provider_type": "photo", "title": "Private Person",
                        "target_url": "https://cdn.example/image?access_token=secret",
                        "author": "Private Person",
                    }],
                    "_provenance": {
                        "reactions": {"raw": "19", "precision": "exact",
                                      "locator": "facebook-cli/counts.reactions"},
                        "shares": {"raw": "private@example.invalid", "locator": "comment_author"},
                    },
                },
                comments=["commenter@example.test"],
                raw_body=b"raw Facebook response",
                observed_at=utcnow(),
            )
            async with sessions() as db:
                evidence = await db.get(MarketEvidence, evidence_id)
                observation = await db.scalar(select(MarketObservation).where(
                    MarketObservation.evidence_id == evidence_id,
                ))
                assert evidence is not None and observation is not None
                assert "0901 234 567" not in evidence.title
                assert "person@example.test" not in evidence.text
                assert "12/5 Đường Cá Nhân" not in evidence.text
                assert observation.comments_json == []
                assert observation.raw_object_key is None
                assert observation.metrics_json["comments_privacy"]["status"] == "privacy_hold"
                assert observation.metrics_json["raw_payload_privacy"]["status"] == "not_retained"
                assert "not_anonymization" in observation.metrics_json["privacy_redaction"]["limitations"]
                assert observation.metrics_json["reactions"] == 19
                assert "shares" not in observation.metrics_json
                assert "comment_text" not in observation.metrics_json
                assert "authors" not in observation.metrics_json
                assert "raw_response" not in observation.metrics_json
                assert observation.metrics_json["link_url"] == "https://news.example/story"
                assert observation.metrics_json["attachments"] == [{
                    "kind": "image", "provider_type": "photo", "title": None,
                    "description": None, "target_url": "https://cdn.example/image",
                    "content_status": "metadata_only_privacy_hold",
                }]
                assert observation.metrics_json["_provenance"]["reactions"] == {
                    "raw": "19", "precision": "exact", "locator": "facebook-cli/counts.reactions",
                }
                assert "shares" not in observation.metrics_json["_provenance"]
        finally:
            async with sessions() as db:
                await db.execute(delete(Company).where(Company.id == company_id))
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
            await engine.dispose()


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


def test_automatic_ai_budget_is_shared_across_deepseek_gemini_and_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider-specific reservations compete for the same workspace/day cap."""
    from types import SimpleNamespace

    from services.worker import ai_budget
    from services.worker.ai_budget import price_for, reserve_token_bound_micro_usd

    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(api_db, "SessionLocal", sessions)
        monkeypatch.setattr(ai_budget, "settings", SimpleNamespace(
            llm_max_input_chars=100,
            llm_max_tokens=100,
            auto_ai_daily_budget_micro_usd=100_000,
        ))
        company_id: str | None = None
        try:
            async with sessions() as db:
                company = Company(name="Shared provider budget", slug=f"shared-budget-{uuid.uuid4().hex[:16]}")
                db.add(company)
                await db.commit()
                company_id = company.id

            deepseek = await ai_budget.reserve_automatic_request(
                company_id=company_id,
                request_key="shared:deepseek",
                provider="deepseek",
                model="deepseek-flash",
                operation="synthetic_research_summary",
            )
            gemini = await ai_budget.reserve_automatic_request(
                company_id=company_id,
                request_key="shared:gemini",
                provider="gemini",
                model="gemini-3.8-flash",
                operation="synthetic_media_analysis",
                max_input_tokens=100_000,
                max_output_tokens=1,
            )
            qwen = await ai_budget.reserve_automatic_request(
                company_id=company_id,
                request_key="shared:qwen",
                provider="qwen",
                model="qwen3.8-27b",
                operation="synthetic_comment_summary",
                region="singapore",
                max_input_tokens=100_000,
                max_output_tokens=1,
            )

            assert deepseek.status == "reserved"
            assert gemini.status == "reserved"
            assert qwen.status == "deferred_budget"
            qwen_bound = reserve_token_bound_micro_usd(
                price_for("qwen", "qwen3.8-27b", region="singapore"),
                max_input_tokens=100_000,
                max_output_tokens=1,
            )
            assert gemini.reserved_micro_usd < 100_000
            assert qwen_bound < 100_000
            assert deepseek.reserved_micro_usd + gemini.reserved_micro_usd <= 100_000
            assert deepseek.reserved_micro_usd + gemini.reserved_micro_usd + qwen_bound > 100_000

            async with sessions() as db:
                day = (await db.scalars(select(AIUsageBudgetDay).where(
                    AIUsageBudgetDay.company_id == company_id,
                ))).one()
                rows = (await db.scalars(select(AIUsageLedger).where(
                    AIUsageLedger.company_id == company_id,
                ).order_by(AIUsageLedger.provider))).all()
                assert day.limit_micro_usd == 100_000
                assert day.reserved_micro_usd == deepseek.reserved_micro_usd + gemini.reserved_micro_usd
                assert day.spent_micro_usd == 0
                assert day.reserved_micro_usd <= day.limit_micro_usd
                assert {(row.provider, row.model) for row in rows} == {
                    ("deepseek", "deepseek-flash"),
                    ("gemini", "gemini-3.8-flash"),
                }
                assert all(row.budget_class == "automatic" for row in rows)
        finally:
            if company_id is not None:
                async with sessions() as db:
                    await db.execute(delete(AIUsageLedger).where(AIUsageLedger.company_id == company_id))
                    await db.execute(delete(AIUsageBudgetDay).where(AIUsageBudgetDay.company_id == company_id))
                    await db.execute(delete(Company).where(Company.id == company_id))
                    await db.commit()
            await engine.dispose()

    asyncio.run(run())


def test_gemini_research_report_reserves_real_postgres_usage_and_replays_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Native Gemini HTTP fixture + real ledger; no Google/Facebook request."""
    import httpx
    from types import SimpleNamespace
    from services.agents.providers.gemini_text import GeminiStructuredModel
    from services.worker import ai_budget

    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.host == "generativelanguage.googleapis.com"
        return httpx.Response(200, json={
            "modelVersion": "gemini-3.8-flash",
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
                "headline": "Báo cáo thử nghiệm", "summary": "Dữ liệu website tổng hợp, không phải nguồn Facebook thật.",
                "trends": [], "suggestions": [],
            })}]}}],
            "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 10,
                              "thoughtsTokenCount": 15, "totalTokenCount": 45},
        })
    model = GeminiStructuredModel(api_key="synthetic-gemini", model="gemini-3.8-flash",
                                 client=httpx.Client(transport=httpx.MockTransport(handler)), max_tokens=1000)
    monkeypatch.setattr(research_tasks, "configured_structured_model", lambda: model)
    monkeypatch.setattr(ai_budget, "settings", SimpleNamespace(auto_ai_daily_budget_micro_usd=2_000_000))

    async def run():
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(api_db, "SessionLocal", sessions)
        monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
        try:
            async with sessions() as db:
                company = Company(name="Gemini report fixture", slug=f"gemini-report-{uuid.uuid4().hex}")
                db.add(company)
                await db.commit()
                company_id = company.id
            group = SimpleNamespace(industry="unknown", region="unknown", locale="vi-VN", keywords_json=[])
            evidence = [{"id": "website-fixture", "title": "Website fixture", "url": "https://example.invalid/"}]
            first = await research_tasks._make_report(company_id, "fixture-cycle", group, evidence, [], [])
            second = await research_tasks._make_report(company_id, "fixture-cycle", group, evidence, [], [])
            assert first[2] == second[2] == "completed" and first[1] == "gemini-3.8-flash"
            assert len(requests) == 1  # Durable replay, not another billable call.
            async with sessions() as db:
                ledger = (await db.scalars(select(AIUsageLedger).where(AIUsageLedger.company_id == company_id))).one()
                day = (await db.scalars(select(AIUsageBudgetDay).where(AIUsageBudgetDay.company_id == company_id))).one()
                assert ledger.provider == "gemini" and ledger.model == "gemini-3.8-flash"
                assert ledger.status == "succeeded" and ledger.budget_class == "automatic"
                assert ledger.input_tokens == 20 and ledger.output_tokens == 25
                assert ledger.actual_micro_usd == 109
                assert day.spent_micro_usd == 109 and day.reserved_micro_usd == 0
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


@pytest.mark.parametrize(
    ("connection_state", "has_page_id", "expected_error_code"),
    [
        ("needs_reconnect", True, "page_needs_reconnect"),
        ("connection_required", False, "page_connection_required"),
    ],
)
def test_postgres_research_worker_blocks_queued_job_without_active_page(
    monkeypatch: pytest.MonkeyPatch,
    connection_state: str,
    has_page_id: bool,
    expected_error_code: str,
) -> None:
    """A stale queued job must stop before any collector or model work starts."""
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
        try:
            async with sessions() as db:
                company = Company(
                    name="Disconnected Page gate",
                    slug=f"page-gate-{uuid.uuid4().hex[:16]}",
                    page_id=f"test-{uuid.uuid4().hex[:20]}" if has_page_id else None,
                    page_connection_state=connection_state,
                )
                user = User(
                    email=f"page-gate-{uuid.uuid4().hex}@example.invalid",
                    full_name="Page gate test",
                    password_hash="test-only-not-a-login",
                )
                db.add_all([company, user])
                await db.flush()
                group = MetaPageGroup(
                    company_id=company.id,
                    name="Internal research group",
                    industry="Unknown",
                    region="Unknown",
                    locale="vi-VN",
                    keywords_json=[],
                    active=True,
                )
                db.add(group)
                await db.flush()
                job = Job(
                    company_id=company.id,
                    created_by=user.id,
                    kind="market_research",
                    title="must not run after Page disconnect",
                    status="queued",
                    progress=0,
                    result={"group_id": group.id},
                    idempotency_key=f"page-gate:{uuid.uuid4().hex}",
                )
                db.add(job)
                await db.flush()
                cycle = ResearchCycle(
                    company_id=company.id,
                    group_id=group.id,
                    job_id=job.id,
                    cycle_key=f"page-gate:{uuid.uuid4().hex}",
                    status="queued",
                    source_results_json=[],
                )
                step = JobStep(
                    job_id=job.id,
                    step_key="collect_sources",
                    label="Collect sources",
                    status="pending",
                )
                db.add_all([cycle, step])
                await db.commit()
                job_id = job.id
                company_id = company.id

            assert await research_tasks._claim(job_id) is False
            async with sessions() as db:
                blocked = await db.get(Job, job_id)
                assert blocked is not None
                assert blocked.status == "failed"
                assert blocked.error is not None
                assert blocked.error["code"] == expected_error_code
                assert blocked.error["retryable"] is False
                assert "Fanpage" in blocked.error["message"]
                assert blocked.attempts == 0
                assert blocked.started_at is None
                assert blocked.claim_token is None
                assert blocked.lease_until is None
                cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id))
                assert cycle is not None and cycle.status == "failed"
                step = await db.scalar(select(JobStep).where(JobStep.job_id == job_id))
                assert step is not None and step.status == "failed"
                event = await db.scalar(select(JobEvent).where(JobEvent.job_id == job_id))
                assert event is not None and event.event_type == "error"
                await db.delete(await db.get(Company, company_id))
                await db.delete(await db.get(User, blocked.created_by))
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_postgres_research_scheduler_does_not_enqueue_when_page_needs_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(scheduled_jobs, "SessionLocal", sessions)
        try:
            now = datetime.now(timezone.utc)
            async with sessions() as db:
                company = Company(
                    name="Research scheduler Page gate",
                    slug=f"research-gate-{uuid.uuid4().hex[:16]}",
                    page_id=f"test-{uuid.uuid4().hex[:20]}",
                    page_connection_state="needs_reconnect",
                )
                user = User(
                    email=f"research-gate-{uuid.uuid4().hex}@example.invalid",
                    full_name="Research scheduler test",
                    password_hash="test-only-not-a-login",
                )
                db.add_all([company, user])
                await db.flush()
                db.add(Membership(
                    company_id=company.id, user_id=user.id, role="owner", is_active=True,
                ))
                group = MetaPageGroup(
                    company_id=company.id,
                    name="Scheduled research",
                    industry="Unknown",
                    region="Unknown",
                    locale="vi-VN",
                    keywords_json=[],
                    next_due_at=now - timedelta(seconds=1),
                    active=True,
                )
                db.add(group)
                await db.flush()
                source = ResearchSource(
                    company_id=company.id,
                    group_id=group.id,
                    source_type="website",
                    name="Scheduled website",
                    url="https://example.invalid/",
                    normalized_url="https://example.invalid/",
                    status="active",
                    active=True,
                    schedule_enabled=True,
                    next_due_at=now - timedelta(seconds=1),
                    created_by=user.id,
                )
                db.add(source)
                await db.commit()
                company_id = company.id
                user_id = user.id
                group_id = group.id
                source_id = source.id

            async with sessions() as db:
                assert await scheduled_jobs._enqueue_due_research(db, now) == 0
                await db.commit()
            async with sessions() as db:
                group = await db.get(MetaPageGroup, group_id)
                source = await db.get(ResearchSource, source_id)
                jobs = (await db.scalars(select(Job).where(Job.company_id == company_id))).all()
                cycles = (await db.scalars(
                    select(ResearchCycle).where(ResearchCycle.company_id == company_id)
                )).all()
                assert group is not None and group.next_due_at is None
                assert source is not None and source.next_due_at is not None
                assert source.next_due_at <= now
                assert jobs == []
                assert cycles == []
                await db.delete(await db.get(Company, company_id))
                await db.delete(await db.get(User, user_id))
                await db.commit()
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
    from services.api.config import settings
    from services.worker.celery_app import celery_app

    assert celery_app.conf.broker_url == broker_url
    assert settings.database_url == POSTGRES_TEST_URL, (
        "DATABASE_URL must point to POSTGRES_TEST_URL before importing the Celery worker; "
        "POSTGRES_TEST_URL alone configures the test client, not the application."
    )

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


def test_owned_page_backfill_continues_through_redis_and_finalizes_once(monkeypatch) -> None:
    """Real PG/Redis/Celery; external Meta responses are labeled fixtures."""
    queue_url = os.getenv("REDIS_QUEUE_TEST_URL")
    if not queue_url or os.getenv("REDIS_URL") != queue_url:
        pytest.skip("an isolated Redis broker is required")
    from celery.contrib.testing.worker import start_worker
    from sqlalchemy.pool import NullPool
    from services.api.meta_client import MetaPagePost, MetaPagePostsPage
    from services.worker.celery_app import celery_app

    observed_at = utcnow()
    page_id = "812345670099"
    calls: list[str | None] = []

    class MetaFixture:
        def __init__(self, actual_page_id, _token, _version):
            assert actual_page_id == page_id

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def read_page_followers_count(self):
            return 100

        async def read_post_media_views(self, _post_id):
            return None

        async def list_page_posts(self, limit=100, after=None):
            calls.append(after)
            index = int(after[1:]) if after else 0
            assert limit == (50 if index < 2 else 100)
            # Six pages require more successful batches than the retry limit.
            return MetaPagePostsPage((MetaPagePost(
                external_post_id=f"{page_id}_{index + 1}",
                message=f"Synthetic owned Page post {index + 1}",
                created_time=observed_at - timedelta(days=index),
                permalink_url=f"https://www.facebook.com/{page_id}/posts/{index + 1}",
                reactions=index, comments=None, shares=0,
            ),), f"c{index + 1}" if index < 5 else None)

    monkeypatch.setattr(research_tasks, "MetaGraphClient", MetaFixture)
    monkeypatch.setattr(research_tasks, "decrypt_page_token", lambda _value: "synthetic-token-no-live-access")

    async def run():
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        worker_sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        monkeypatch.setattr(research_tasks, "SessionLocal", worker_sessions)
        marker = uuid.uuid4().hex
        company_id, user_id, group_id, connection_id, source_id, job_id = [new_id() for _ in range(6)]
        try:
            async with sessions() as db:
                db.add_all([
                    Company(id=company_id, name="Meta fixture batching", slug=f"batches-{marker}",
                            page_id=page_id, page_connection_state="active"),
                    User(id=user_id, email=f"batches-{marker}@example.invalid", full_name="Fixture Owner",
                         password_hash="not-a-login"),
                ])
                await db.flush()
                db.add(MetaPageGroup(id=group_id, company_id=company_id, name="Research batch fixture",
                                    industry="Unknown", region="Unknown", locale="vi-VN", keywords_json=[]))
                await db.flush()
                db.add(MetaPageConnection(id=connection_id, company_id=company_id, group_id=group_id,
                                         page_id=page_id, page_name="Meta fixture batching",
                                         encrypted_token="fixture-not-usable", active=True, status="verified",
                                         token_fingerprint="test-only-fingerprint"))
                await db.flush()
                db.add(ResearchSource(id=source_id, company_id=company_id, group_id=group_id,
                                      connection_id=connection_id, source_type="owned_facebook_page",
                                      collection_mode="meta_api", name="Owned Page fixture",
                                      url=f"https://www.facebook.com/{page_id}",
                                      normalized_url=f"https://www.facebook.com/{page_id}",
                                      active=True, schedule_enabled=False, created_by=user_id))
                await db.flush()
                db.add(ResearchPrivacyPolicyRevision(company_id=company_id, source_id=source_id,
                    revision_no=1, purpose="Synthetic test content only", processing_basis_reference="fixture",
                    policy_version="test-only", requested_retention_days=90, configured_by=user_id))
                db.add(Job(id=job_id, company_id=company_id, created_by=user_id, kind="market_research",
                           title="Owned Page batch fixture", status="queued", progress=0,
                           result={"group_id": group_id, "source_ids": [source_id]}))
                await db.flush()
                db.add(ResearchCycle(company_id=company_id, group_id=group_id, job_id=job_id,
                                     cycle_key=f"batches:{marker}", status="queued", source_results_json=[],
                                     collection_observed_at=observed_at))
                await db.commit()

            with start_worker(celery_app, pool="solo", concurrency=1, queues=("agent",),
                              perform_ping_check=False, shutdown_timeout=10):
                assert await job_service.dispatch_research_job(job_id) is True
                deadline = asyncio.get_running_loop().time() + 25
                while asyncio.get_running_loop().time() < deadline:
                    async with sessions() as db:
                        job = await db.get(Job, job_id)
                        if job is not None and job.status in {"succeeded", "failed"}:
                            assert job.status == "succeeded", job.error
                            break
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Owned Page batching did not finish through Redis/Celery")
            async with sessions() as db:
                job = await db.get(Job, job_id)
                cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id))
                reports = (await db.scalars(select(MarketReport).where(MarketReport.cycle_id == cycle.id))).all()
                observations = (await db.scalars(select(MarketObservation).where(
                    MarketObservation.company_id == company_id))).all()
                source = await db.get(ResearchSource, source_id)
                assert calls == [None, "c1", "c2", "c3", "c4", "c5"]
                assert job.attempts == 1
                assert len(reports) == 1
                assert len(observations) == 6
                assert all(row.observed_at == observed_at for row in observations)
                assert all(row.comments_json == [] for row in observations)
                assert cycle.source_results_json[0]["collection_batches_completed"] == 5
                assert cycle.source_results_json[0]["items_saved"] == 6
                assert cycle.source_results_json[0]["continuation_pending"] is False
                assert source.owned_page_backfill_complete is True
                assert source.owned_page_backfill_cursor is None
                assert source.next_due_at is None  # A manual crawl never enables scheduling.
                # Replayed deliveries cannot create a second report/snapshot.
                await research_tasks.market_research_task_async(job_id)
                assert len((await db.scalars(select(MarketReport).where(MarketReport.cycle_id == cycle.id))).all()) == 1
        finally:
            async with sessions() as db:
                company = await db.get(Company, company_id)
                if company is not None:
                    await db.delete(company)
                user = await db.get(User, user_id)
                if user is not None:
                    await db.delete(user)
                await db.commit()
            await engine.dispose()

    asyncio.run(run())


def test_owned_page_continuation_recovers_after_real_disposable_redis_outage(monkeypatch, tmp_path) -> None:
    """Stop only a Redis process started by this test; retain its committed job."""
    from celery import Celery
    from services.worker import celery_app as celery_module

    redis_binary = shutil.which("redis-server")
    if not redis_binary:
        pytest.skip("local Redis binary is required for an owned disposable fault test")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    broker_url = f"redis://127.0.0.1:{port}/0"
    fault_app = Celery("disposable_research_fault", broker=broker_url)
    fault_app.conf.update(task_serializer="json", task_publish_retry=False,
                          broker_transport_options={"socket_connect_timeout": 0.2, "socket_timeout": 0.2,
                                                    "max_retries": 0})
    monkeypatch.setattr(celery_module, "celery_app", fault_app)
    process = None

    def start_redis():
        return subprocess.Popen([
            redis_binary, "--bind", "127.0.0.1", "--port", str(port), "--protected-mode", "yes",
            "--save", "", "--appendonly", "no", "--dir", str(tmp_path),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def ready(redis, owned_process):
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            assert owned_process.poll() is None, "test Redis process exited"
            try:
                info = await redis.info("server")
                assert int(info["process_id"]) == owned_process.pid
                return
            except (RedisConnectionError, OSError):
                pass
            await asyncio.sleep(0.05)
        pytest.fail("disposable Redis did not become ready")

    async def run():
        nonlocal process
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
        marker = uuid.uuid4().hex
        company_id, user_id, group_id, job_id = [new_id() for _ in range(4)]
        checkpoint = [{"source_id": "synthetic-source", "continuation_pending": True,
                       "status": "collected", "items_saved": 7}]
        redis = Redis.from_url(broker_url)
        try:
            async with sessions() as db:
                db.add_all([Company(id=company_id, name="Redis fault fixture", slug=f"redis-fault-{marker}"),
                            User(id=user_id, email=f"redis-fault-{marker}@example.invalid", full_name="Fixture",
                                 password_hash="not-a-login")])
                await db.flush()
                db.add(MetaPageGroup(id=group_id, company_id=company_id, name="Fault fixture",
                                    industry="Unknown", region="Unknown", locale="vi-VN", keywords_json=[]))
                await db.flush()
                db.add(Job(id=job_id, company_id=company_id, created_by=user_id, kind="market_research",
                           title="Fault fixture batch", status="running", attempts=1,
                           result={"group_id": group_id}))
                await db.flush()
                db.add(ResearchCycle(company_id=company_id, group_id=group_id, job_id=job_id,
                                     cycle_key=f"fault:{marker}", status="running", source_results_json=[]))
                await db.commit()

            process = start_redis()
            await ready(redis, process)
            assert await research_tasks._queue_owned_page_continuation(job_id, checkpoint) is True
            process.terminate()
            process.wait(timeout=5)
            await research_tasks._dispatch_owned_page_continuation(job_id)
            async with sessions() as db:
                job = await db.get(Job, job_id)
                cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id))
                assert job.status == "queued"
                assert job.last_dispatch_error == "queue_unavailable"
                assert job.lease_until is None
                assert cycle.source_results_json == checkpoint

            process = start_redis()
            await ready(redis, process)
            await research_tasks._dispatch_owned_page_continuation(job_id)
            raw = await redis.lpop("agent")
            assert raw is not None
            message = json.loads(raw)
            body = json.loads(base64.b64decode(message["body"]))
            assert body[0] == [job_id]
            assert await redis.llen("agent") == 0
            async with sessions() as db:
                job = await db.get(Job, job_id)
                assert job.status == "queued"  # Recovered delivery is awaiting a worker.
                assert job.last_dispatch_error is None
                assert job.dispatch_attempts == 2
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            await redis.aclose()
            fault_app.close()
            async with sessions() as db:
                company = await db.get(Company, company_id)
                if company is not None:
                    await db.delete(company)
                user = await db.get(User, user_id)
                if user is not None:
                    await db.delete(user)
                await db.commit()
            await engine.dispose()

    asyncio.run(run())
