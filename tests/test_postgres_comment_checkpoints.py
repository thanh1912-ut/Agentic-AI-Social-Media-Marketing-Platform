"""Real PostgreSQL checks for comment frontier isolation, provenance and fencing."""

import asyncio
import os
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.job_fencing import JobLeaseLost, _current_job_fence
from database.models import (
    Company, Job, MarketObservation, MetaPageGroup, ResearchCommentCheckpoint,
    ResearchSource, User, new_id, utcnow,
)
from services.api.db import FencedAsyncSession
from services.worker import research_tasks


POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL")
POSTGRES_FRESH_TEST_URL = os.getenv("POSTGRES_FRESH_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="POSTGRES_TEST_URL is not configured")


def test_postgres_comment_checkpoint_isolation_replay_version_and_stale_worker(monkeypatch):
    async def exercise():
        assert POSTGRES_TEST_URL
        engine = create_async_engine(POSTGRES_TEST_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
        marker = uuid.uuid4().hex
        company_ids, group_ids, source_ids = ([new_id(), new_id()] for _ in range(3))
        user_id, job_id = new_id(), new_id()
        fence_context = _current_job_fence.set(None)
        try:
            async with engine.connect() as conn:
                assert (await conn.exec_driver_sql("SELECT version_num FROM alembic_version")).scalar_one() == "0029_comment_suppression"

                def check_schema(sync_conn):
                    inspector = inspect(sync_conn)
                    assert {fk["name"] for fk in inspector.get_foreign_keys("research_comment_checkpoints")} == {
                        "fk_comment_checkpoint_source_evidence_tenant",
                        "fk_comment_checkpoint_observation_version_tenant",
                    }
                    assert not {"message", "text", "author", "author_id", "raw_payload"}.intersection(
                        column["name"] for column in inspector.get_columns("research_comment_checkpoints")
                    )

                await conn.run_sync(check_schema)
            async with sessions() as db:
                db.add(User(id=user_id, email=f"comment-checkpoint-{marker}@example.invalid",
                            full_name="Synthetic checkpoint fixture", password_hash="not-a-login"))
                for index in range(2):
                    db.add(Company(id=company_ids[index], name="Synthetic checkpoint fixture",
                                   slug=f"comment-checkpoint-{index}-{marker}"))
                await db.flush()
                for index in range(2):
                    db.add(MetaPageGroup(id=group_ids[index], company_id=company_ids[index], name="Research",
                                        industry="fixture", region="fixture"))
                await db.flush()
                for index in range(2):
                    db.add(ResearchSource(id=source_ids[index], company_id=company_ids[index], group_id=group_ids[index],
                                          source_type="owned_facebook_page", name="Synthetic owned Page",
                                          url=f"https://www.facebook.com/{123 + index}",
                                          normalized_url=f"https://www.facebook.com/{123 + index}",
                                          active=True, created_by=user_id))
                db.add(Job(id=job_id, company_id=company_ids[0], created_by=user_id, kind="market_research",
                           title="Synthetic checkpoint fencing", status="running", claim_token="new-worker",
                           lease_until=utcnow() + timedelta(minutes=5)))
                await db.commit()
            async with sessions() as db:
                source = await db.get(ResearchSource, source_ids[0])
            observed_at = utcnow()
            parameters = dict(company_id=company_ids[0], group_id=group_ids[0], source=source,
                              url="https://www.facebook.com/123/posts/456", title="Synthetic post",
                              text="Synthetic post", published_at=observed_at, comments=[], raw_body=None,
                              page_id="123", external_post_id="123_456")
            evidence_id = await research_tasks._persist_evidence(**parameters, metrics={"comments": 5}, observed_at=observed_at)
            await research_tasks._persist_evidence(**parameters, metrics={"comments": 999}, observed_at=observed_at)
            async with sessions() as db:
                rows = (await db.scalars(select(ResearchCommentCheckpoint).where(
                    ResearchCommentCheckpoint.company_id == company_ids[0],
                ))).all()
                assert len(rows) == 1
                first = rows[0]
                assert first.provider_reported_count == 5 and first.received_count == 0
                assert first.status == "privacy_hold" and first.pagination_exhausted is False
                first_observation_id, first_version_id = first.observation_id, first.evidence_version_id
            base = dict(company_id=company_ids[0], source_id=source_ids[0], evidence_id=evidence_id,
                        observation_id=first_observation_id, evidence_version_id=first_version_id,
                        external_post_id="123_456", parent_key="root")
            for invalid in (
                base,  # Duplicate replay key.
                {**base, "source_id": source_ids[1], "parent_key": "456_1"},
                {**base, "company_id": company_ids[1], "parent_key": "456_2"},
                {**base, "parent_key": "456_3", "received_count": -1},
            ):
                async with sessions() as db:
                    db.add(ResearchCommentCheckpoint(**invalid))
                    with pytest.raises(IntegrityError):
                        await db.commit()
                    await db.rollback()
            parameters["text"] = "Edited synthetic post"
            await research_tasks._persist_evidence(**parameters, metrics={"comments": None},
                                                   observed_at=observed_at + timedelta(hours=12))
            async with sessions() as db:
                second = await db.scalar(select(ResearchCommentCheckpoint).where(
                    ResearchCommentCheckpoint.company_id == company_ids[0],
                    ResearchCommentCheckpoint.observation_id != first_observation_id,
                ))
                assert second.evidence_version_id != first_version_id
                assert second.provider_reported_count is None
                invalid_version = {**base, "parent_key": "456_4", "evidence_version_id": second.evidence_version_id}
                db.add(ResearchCommentCheckpoint(**invalid_version))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
            _current_job_fence.set((job_id, "expired-worker"))
            with pytest.raises(JobLeaseLost):
                await research_tasks._persist_evidence(**parameters, metrics={"comments": 8},
                                                       observed_at=observed_at + timedelta(days=1))
            _current_job_fence.set(None)
            async with sessions() as db:
                assert len((await db.scalars(select(ResearchCommentCheckpoint).where(
                    ResearchCommentCheckpoint.company_id == company_ids[0],
                ))).all()) == 2
                assert len((await db.scalars(select(MarketObservation).where(
                    MarketObservation.company_id == company_ids[0],
                ))).all()) == 2
        finally:
            _current_job_fence.set(None)
            async with sessions() as db:
                await db.execute(delete(Company).where(Company.id.in_(company_ids)))
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
            await engine.dispose()
            _current_job_fence.reset(fence_context)

    asyncio.run(exercise())


@pytest.mark.skipif(not POSTGRES_FRESH_TEST_URL, reason="POSTGRES_FRESH_TEST_URL is not configured")
def test_comment_frontier_fresh_and_upgrade_schema_match():
    """Compare actual type/default/constraint/index definitions, not just head IDs."""
    async def schema(url):
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                assert (await conn.exec_driver_sql("SELECT version_num FROM alembic_version")).scalar_one() == "0029_comment_suppression"

                def fingerprint(sync_conn):
                    inspector = inspect(sync_conn)
                    table = "research_comment_checkpoints"
                    return {
                        # Metadata puts mixin id last; the additive migration
                        # puts it first. Compare semantic definitions by name,
                        # while retaining ordered columns within FKs/indexes.
                        "columns": sorted((column["name"], str(column["type"]), column["nullable"], column["default"])
                                          for column in inspector.get_columns(table)),
                        "foreign_keys": sorted(inspector.get_foreign_keys(table), key=lambda item: item["name"]),
                        "checks": sorted(inspector.get_check_constraints(table), key=lambda item: item["name"]),
                        "uniques": sorted(inspector.get_unique_constraints(table), key=lambda item: item["name"]),
                        "indexes": sorted(inspector.get_indexes(table), key=lambda item: item["name"]),
                        "evidence_source_key": next(item for item in inspector.get_unique_constraints("market_evidence")
                                                    if item["name"] == "uq_market_evidence_tenant_source_id"),
                    }

                return await conn.run_sync(fingerprint)
        finally:
            await engine.dispose()

    async def exercise():
        assert POSTGRES_TEST_URL and POSTGRES_FRESH_TEST_URL
        assert POSTGRES_FRESH_TEST_URL != POSTGRES_TEST_URL
        assert await schema(POSTGRES_TEST_URL) == await schema(POSTGRES_FRESH_TEST_URL)

    asyncio.run(exercise())
