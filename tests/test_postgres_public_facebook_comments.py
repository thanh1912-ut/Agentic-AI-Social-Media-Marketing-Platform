"""Real PostgreSQL acceptance using synthetic signed-out comment records only."""

import asyncio
import os
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from database.job_fencing import JobLeaseLost, _current_job_fence
from database.models import Job, ResearchCommentPageReceipt, ResearchCommentVersion, new_id, utcnow
from services.api.db import FencedAsyncSession
from tests.test_postgres_comment_quarantine import cleanup, configure
from tests.test_public_facebook_comments import persist, post_payload, seed_public

POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="Disposable POSTGRES_TEST_URL is not configured")


def test_public_comments_concurrent_replay_history_and_stale_worker_are_atomic(monkeypatch):
    async def exercise():
        engine = create_async_engine(POSTGRES_TEST_URL, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        configure(monkeypatch, sessions)
        seed, source = await seed_public(sessions)
        context = _current_job_fence.set(None)
        try:
            observed = utcnow()
            ids = await asyncio.gather(persist(seed, source, time=observed), persist(seed, source, time=observed))
            assert ids[0] == ids[1]
            async with sessions() as db:
                original = (await db.scalars(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"],
                ))).all()
                assert len(original) == 2
                original_ids = {row.id for row in original}
                original_observation = original[0].observation_id
                assert len((await db.scalars(select(ResearchCommentPageReceipt).where(
                    ResearchCommentPageReceipt.company_id == seed["company_id"],
                ))).all()) == 1
                job_id = new_id()
                db.add(Job(id=job_id, company_id=seed["company_id"], created_by=seed["user_id"],
                    kind="market_research", status="running", title="Synthetic public comment fencing",
                    claim_token="replacement-worker", lease_until=utcnow() + timedelta(minutes=5)))
                await db.commit()
            changed = post_payload()
            changed["comment_records"][0]["likes"] = 3
            changed["comment_records"][0]["reaction_breakdown"]["LIKE"] = 3
            _current_job_fence.set((job_id, "stale-worker"))
            with pytest.raises(JobLeaseLost):
                await persist(seed, source, time=observed + timedelta(seconds=1), payload=changed)
            _current_job_fence.set((job_id, "replacement-worker"))
            await persist(seed, source, time=observed + timedelta(seconds=1), payload=changed)
            _current_job_fence.set(None)
            async with sessions() as db:
                rows = (await db.scalars(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"],
                ))).all()
                assert len(rows) == 4
                assert {row.id for row in rows if row.observation_id == original_observation} == original_ids
                assert sorted(row.likes for row in rows if row.likes is not None) == [2, 3]
                assert all(row.status == "privacy_hold" and row.candidate_ciphertext for row in rows)
                assert all(row.expires_at - row.captured_at <= timedelta(hours=24) for row in rows)
        finally:
            _current_job_fence.set(None)
            await cleanup(sessions, seed)
            await engine.dispose()
            _current_job_fence.reset(context)
    asyncio.run(exercise())


def test_public_page_comment_subprocess_runs_through_redis_and_replay_is_idempotent(monkeypatch, tmp_path):
    import json
    from dataclasses import replace
    from celery.contrib.testing.worker import start_worker
    from database.models import ResearchCycle, MarketReport, WebCrawlRun
    from services.api import job_service
    from services.api.config import settings
    from services.research.facebook_cli_collector import ENGINE_VERSION
    from services.worker import research_tasks
    from services.worker.celery_app import celery_app
    queue = os.getenv("REDIS_QUEUE_TEST_URL")
    if not queue:
        pytest.skip("Disposable REDIS_QUEUE_TEST_URL is not configured")
    assert settings.database_url == POSTGRES_TEST_URL and settings.redis_url == queue and not settings.inline_jobs
    calls = tmp_path / "synthetic-runner-calls.txt"
    runner = tmp_path / "synthetic-public-runner"
    async def exercise():
        engine = create_async_engine(POSTGRES_TEST_URL, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        configure(monkeypatch, sessions)
        seed, source = await seed_public(sessions)
        try:
            page_id = source.url.rsplit("/", 1)[-1]
            post = {**post_payload(), "author_id": page_id, "url": source.url + "/posts/456",
                    "text": "Synthetic public Page content", "published_at": utcnow().isoformat(),
                    "counts": {"reactions": 9, "comments": 200, "shares": 1, "views": None},
                    "counts_raw": {}, "reaction_breakdown": {"LIKE": 2, "LOVE": 7}}
            for record in post["comment_records"]:
                date = record["published_at"]
                record["published_at"] = date.isoformat() if date else None
            rows = [
                {"schema_version": 1, "type": "page", "page": {"id": page_id, "name": "Synthetic public Page", "url": source.url, "kind": "page"}},
                {"schema_version": 1, "type": "post", "post": post},
                {"schema_version": 1, "type": "summary", "engine_version": ENGINE_VERSION, "http_requests": 2,
                 "history_complete": False, "stop_reason": "tier0_feed_exhausted"},
            ]
            output = "\n".join(json.dumps(row) for row in rows) + "\n"
            runner.write_text("#!/usr/bin/env python3\nimport json,sys,pathlib\n"
                "request=json.load(sys.stdin)\nassert request['include_comments'] is True\n"
                f"with pathlib.Path({str(calls)!r}).open('a') as f: f.write('called\\n')\n"
                f"sys.stdout.write({output!r})\n")
            runner.chmod(0o755)
            monkeypatch.setattr(research_tasks, "settings", replace(research_tasks.settings, facebook_cli_runner_path=str(runner)))
            job_id = new_id()
            async with sessions() as db:
                db.add(Job(id=job_id, company_id=seed["company_id"], created_by=seed["user_id"], kind="market_research",
                    title="Synthetic public Page queue acceptance", status="queued", progress=0,
                    result={"group_id": seed["group_id"], "source_ids": [source.id]}))
                await db.flush()
                db.add(ResearchCycle(company_id=seed["company_id"], group_id=seed["group_id"], job_id=job_id,
                    cycle_key="synthetic-public:" + job_id, status="queued", source_results_json=[], collection_observed_at=utcnow()))
                await db.commit()
            with start_worker(celery_app, pool="solo", concurrency=1, queues=("agent",),
                              perform_ping_check=False, shutdown_timeout=10):
                assert await job_service.dispatch_research_job(job_id)
                deadline = asyncio.get_running_loop().time() + 25
                while asyncio.get_running_loop().time() < deadline:
                    async with sessions() as db:
                        job = await db.get(Job, job_id)
                        if job.status in {"succeeded", "failed"}:
                            assert job.status == "succeeded", job.error
                            break
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Public Page comments did not persist through Redis worker")
                assert await job_service.dispatch_research_job(job_id)
                await asyncio.sleep(0.2)
            assert calls.read_text().splitlines() == ["called"]
            async with sessions() as db:
                records = (await db.scalars(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == seed["company_id"]))).all()
                assert len(records) == 2 and sorted(r.likes for r in records if r.likes is not None) == [2]
                run = await db.scalar(select(WebCrawlRun).where(WebCrawlRun.company_id == seed["company_id"]))
                assert run.status == "partial" and run.counters_json["items_saved"] == 1
                reports = (await db.scalars(select(MarketReport).where(MarketReport.company_id == seed["company_id"]))).all()
                assert len(reports) == 1 and reports[0].report_json["analysis_status"] == "deferred_privacy_review"
        finally:
            await cleanup(sessions, seed)
            await engine.dispose()
    asyncio.run(exercise())
