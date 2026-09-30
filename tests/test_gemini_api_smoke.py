"""Opt-in real Gemini smoke with synthetic collection and isolated PG/Redis.

Never run as part of fixture tests. One Google generation request maximum;
Meta/Page activation and website collection are explicitly synthetic here.
"""

import asyncio
import json
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


@pytest.mark.api_smoke
@pytest.mark.skipif(os.getenv("RUN_GEMINI_API_SMOKE") != "1", reason="Gemini live smoke requires explicit opt-in")
def test_live_gemini_research_job_through_redis_and_postgres(monkeypatch):
    from celery.contrib.testing.worker import start_worker
    from database.models import AIUsageLedger, Company, Job, MarketReport, MetaPageGroup, ResearchCycle, ResearchSource, User, new_id, utcnow
    from services.api import db as api_db, job_service
    from services.api.config import settings
    from services.api.db import FencedAsyncSession
    from services.worker import research_tasks
    from services.worker.celery_app import celery_app

    database_url = os.environ["POSTGRES_TEST_URL"]
    assert settings.database_url == database_url and "127.0.0.1:15559" in database_url
    assert settings.redis_url == os.environ["REDIS_QUEUE_TEST_URL"]
    assert "127.0.0.1:16481" in settings.redis_url
    assert settings.llm_provider == "gemini" and settings.llm_default_model == "gemini-3.8-flash"
    assert settings.gemini_api_key
    provider = research_tasks.configured_structured_model()
    original_generate = provider.generate
    calls = 0

    def safe_http_status(response):
        # No response body, request headers, key, document text or model output
        # is logged. HTTP status alone makes provider rejection diagnosable.
        print(f"GEMINI_HTTP status={response.status_code}")

    provider.client.event_hooks["response"] = [safe_http_status]

    def one_call(**kwargs):
        nonlocal calls
        calls += 1
        assert calls == 1, "live smoke provider request budget exhausted"
        try:
            return original_generate(**kwargs)
        except Exception as error:
            print(f"GEMINI_FAILURE type={type(error).__name__}")
            raise

    monkeypatch.setattr(provider, "generate", one_call)
    monkeypatch.setattr(research_tasks, "configured_structured_model", lambda: provider)

    async def synthetic_collection(company_id, group_id, source, observed_at, **_kwargs):
        await research_tasks._persist_evidence(
            company_id=company_id, group_id=group_id, source=source, url=source.url,
            title="Synthetic product announcement — not a real business",
            text="Synthetic source: a stationery business announced two notebook formats, plain and ruled. "
                 "It explains how customers may choose the appropriate format. No engagement or sales counts are supplied.",
            published_at=None, metrics={}, comments=[], raw_body=None, observed_at=observed_at,
        )
        return 1, {"items_saved": 1, "collection_fixture": True}

    monkeypatch.setattr(research_tasks, "_collect_website", synthetic_collection)

    async def run():
        engine = create_async_engine(database_url, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        monkeypatch.setattr(api_db, "SessionLocal", sessions)
        monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
        company_id, user_id, group_id, source_id, job_id, cycle_id = [new_id() for _ in range(6)]
        marker = uuid.uuid4().hex
        try:
            async with sessions() as db:
                db.add_all([
                    Company(id=company_id, name="Gemini synthetic live smoke", slug=f"gemini-smoke-{marker}",
                            page_id=f"synthetic-{marker}", page_connection_state="active"),
                    User(id=user_id, email=f"gemini-{marker}@example.invalid", full_name="Synthetic Owner", password_hash="not-a-login"),
                ])
                await db.flush()
                db.add(MetaPageGroup(id=group_id, company_id=company_id, name="Synthetic research", industry="Unknown",
                                    region="Unknown", locale="vi-VN", keywords_json=[]))
                await db.flush()
                db.add(ResearchSource(id=source_id, company_id=company_id, group_id=group_id, source_type="website",
                                      name="Synthetic website", url="https://source.example.invalid/announcement",
                                      normalized_url="https://source.example.invalid/announcement", active=True,
                                      schedule_enabled=False, created_by=user_id))
                db.add(Job(id=job_id, company_id=company_id, created_by=user_id, kind="market_research", title="Gemini live smoke",
                           status="queued", result={"group_id": group_id, "source_ids": [source_id]}))
                await db.flush()
                db.add(ResearchCycle(id=cycle_id, company_id=company_id, group_id=group_id, job_id=job_id,
                                     cycle_key=f"gemini-smoke:{marker}", status="queued", source_results_json=[], collection_observed_at=utcnow()))
                await db.commit()

            with start_worker(celery_app, pool="solo", queues=("agent",), concurrency=1,
                              perform_ping_check=False, shutdown_timeout=10):
                assert await job_service.dispatch_research_job(job_id)
                deadline = asyncio.get_running_loop().time() + 120
                while asyncio.get_running_loop().time() < deadline:
                    async with sessions() as db:
                        job = await db.get(Job, job_id)
                        if job.status in {"succeeded", "failed"}:
                            assert job.status == "succeeded", job.error
                            assert job.result["analysis_status"] == "completed", job.result.get("analysis_status")
                            break
                    await asyncio.sleep(0.2)
                else:
                    pytest.fail("live smoke job did not finish")

            async with sessions() as db:
                report = (await db.scalars(select(MarketReport).where(MarketReport.cycle_id == cycle_id))).one()
                ledger = (await db.scalars(select(AIUsageLedger).where(AIUsageLedger.company_id == company_id))).one()
                assert calls == 1 and ledger.provider == "gemini"
                assert ledger.status == "succeeded" and ledger.actual_micro_usd is not None
                assert ledger.actual_micro_usd <= 2_000_000
                assert len(report.report_json["evidence_refs"]) == 1
                print("GEMINI_SMOKE " + json.dumps({
                    "job_id": job_id, "cycle_id": cycle_id, "report_id": report.id,
                    "provider": ledger.provider, "model": ledger.model,
                    "input_tokens": ledger.input_tokens, "output_tokens": ledger.output_tokens,
                    "cost_micro_usd": ledger.actual_micro_usd, "provider_calls": calls,
                    "collection": "synthetic_fixture", "database": "isolated_postgres", "queue": "isolated_redis",
                }))
                # A second delivery is local replay, never a second Google call.
                await research_tasks.market_research_task_async(job_id)
                assert calls == 1
        finally:
            # Retain this isolated test company's rows for evidence/inspection.
            # They are not inserted into the user's preview database.
            await engine.dispose()

    asyncio.run(run())
