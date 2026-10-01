"""Synthetic Gemini fixtures; PostgreSQL variants verify durable/fenced writes."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from database.models import (
    AIUsageBudgetDay, AIUsageLedger, Job, Membership, ResearchCommentAnalysisBatch,
    ResearchCommentVersion, ResearchScreenedComment, utcnow,
)
from services.api import job_service
from services.agents.providers.comment_contracts import CommentAnalysis
from services.agents.providers.errors import ProviderTimeoutError
from services.research.comment_analysis import purge_expired_screened_comments
from services.worker import ai_budget, comment_analysis_tasks
from tests.test_owned_comment_api import owned_api as _owned_api_fixture, collect
from tests.test_market_research_api import market_api as _market_api_fixture

owned_api = _owned_api_fixture
market_api = _market_api_fixture


def request_for(client, seed, headers, base, evidence):
    comments = client.get(base + f"/posts/{evidence}/comments", headers=headers).json()["comments"]
    return {"request_key": str(uuid4()), "decision_id": seed["decision_id"], "policy_revision_no": 1,
        "provider_assessment_reference": "Synthetic fixture only; no personal data; provider transfer test",
        "comments": [{"version_id": comments[0]["id"], "text": "Tôi muốn biết cách sử dụng sản phẩm."}]}


@pytest.fixture
def screened(owned_api, monkeypatch):
    client, sessions, seed, headers, base, evidence = owned_api
    asyncio.run(collect(sessions, seed))
    sent = []
    async def dispatch(job_id):
        async with sessions() as db:
            job = await db.get(Job, job_id)
            batch = await db.get(ResearchCommentAnalysisBatch, job.result["batch_id"])
            assert batch is not None and job.status == "queued"
        sent.append(job_id)
        return False  # Commit/queue recovery tested without sending live work.
    monkeypatch.setattr(job_service, "dispatch_comment_analysis_job", dispatch)
    monkeypatch.setattr(comment_analysis_tasks, "SessionLocal", sessions)
    async def hold_report_dispatch(job_id):
        return False  # Tests explicitly execute followup; never dispatch to shared Redis.
    monkeypatch.setattr(job_service, "dispatch_comment_report_job", hold_report_dispatch)
    from services.api import db as api_db
    monkeypatch.setattr(api_db, "SessionLocal", sessions)
    body = request_for(client, seed, headers, base, evidence)
    return client, sessions, seed, headers, base, body, sent


def enqueue(screened):
    client, sessions, seed, headers, base, body, sent = screened
    result = client.post(base + "/comment-analyses", json=body, headers=headers)
    assert result.status_code == 202, result.text
    return result.json()["job_id"]


def test_screened_selection_is_immutable_encrypted_and_durable_before_dispatch(screened):
    client, sessions, seed, headers, base, body, sent = screened
    job_id = enqueue(screened)
    repeat = client.post(base + "/comment-analyses", json=body, headers=headers)
    assert repeat.status_code == 202 and repeat.json()["job_id"] == job_id
    assert sent == [job_id]
    changed = {**body, "comments": [{**body["comments"][0], "text": "Changed excerpt"}]}
    response = client.post(base + "/comment-analyses", json=changed, headers=headers)
    assert response.status_code == 409 and response.json()["error"]["code"] == "comment_analysis_replay_conflict"
    async def verify():
        async with sessions() as db:
            job = await db.get(Job, job_id)
            assert job.dispatch_attempts == 1 and job.last_dispatch_error == "queue_unavailable"
            batch = await db.get(ResearchCommentAnalysisBatch, job.result["batch_id"])
            item = await db.scalar(select(ResearchScreenedComment).where(ResearchScreenedComment.batch_id == batch.id))
            assert body["comments"][0]["text"] not in item.excerpt_ciphertext
            assert item.source_content_hash and item.excerpt_hash and item.content_edited
            assert batch.result_json is None and batch.provider == "gemini"
    asyncio.run(verify())
    listing = client.get(base + "/comment-analyses", headers=headers)
    assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store, private"
    assert listing.json()["items"][0]["selected_version_ids"] == [body["comments"][0]["version_id"]]
    assert listing.json()["items"][0]["citations"][0]["text"] == body["comments"][0]["text"]
    assert "author_alias" not in listing.text and "external_comment_id" not in listing.text


@pytest.mark.parametrize("change", ["contact", "missing", "expired", "stale", "viewer", "editor", "duplicate", "cross_source"])
def test_unreviewed_or_invalid_selections_do_not_create_jobs(screened, change):
    client, sessions, seed, headers, base, body, sent = screened
    if change == "contact":
        body["comments"][0]["text"] = "Call 0901 234 567"
    elif change == "missing":
        body["comments"][0]["version_id"] = str(uuid4())
    elif change == "duplicate":
        body["comments"] *= 2
    elif change in {"viewer", "editor"}:
        async def role():
            async with sessions() as db:
                m = await db.scalar(select(Membership).where(Membership.company_id == seed["company_id"]))
                m.role = change
                await db.commit()
        asyncio.run(role())
    else:
        async def mutate():
            async with sessions() as db:
                row = await db.get(ResearchCommentVersion, body["comments"][0]["version_id"])
                if change == "expired":
                    row.status = "expired"
                    row.candidate_ciphertext = None
                elif change == "cross_source":
                    # API must not accept even an existing ID on another source.
                    body["comments"][0]["version_id"] = str(uuid4())
                else:
                    attrs = {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != "id"}
                    attrs.update(id=str(uuid4()), content_hash="a"*64,
                        captured_at=row.captured_at + timedelta(seconds=1))
                    db.add(ResearchCommentVersion(**attrs))
                await db.commit()
        asyncio.run(mutate())
    response = client.post(base + "/comment-analyses", json=body, headers=headers)
    assert response.status_code in {403, 409, 422}, response.text
    assert sent == []


class FakeGemini:
    provider_name = "gemini"
    model_name = "gemini-3.8-flash"
    def __init__(self, hook=None, fail=False):
        self.calls, self.hook, self.fail, self.inputs = 0, hook, fail, []
    def reservation_parameters(self):
        return {"max_input_tokens": 1_048_576, "max_output_tokens": 8192, "max_attempts": 1}
    def summarize_screened_comments(self, *, batch):
        self.calls += 1
        self.inputs.append(batch.model_dump())
        if self.hook:
            self.hook()
        if self.fail:
            raise ProviderTimeoutError("Synthetic timeout")
        return CommentAnalysis(topics=[{"category": "question", "topic": "Cách sử dụng", "summary": "Người đọc hỏi cách dùng.",
            "evidence_refs": [batch.comments[0].evidence_ref]}], limitations=["Chỉ một đoạn đã kiểm tra, chưa đại diện toàn Page."]), SimpleNamespace(model=self.model_name, input_tokens=20, output_tokens=10)


def postgres_only(sessions):
    if sessions.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Durable worker/budget verification requires disposable PostgreSQL")


def configured(monkeypatch, model):
    monkeypatch.setattr(comment_analysis_tasks, "configured_structured_model", lambda: model)


def test_worker_pins_refs_accounts_budget_and_duplicate_task_calls_once(screened, monkeypatch):
    client, sessions, seed, headers, base, body, _sent = screened
    postgres_only(sessions)
    model = FakeGemini()
    configured(monkeypatch, model)
    job_id = enqueue(screened)
    asyncio.run(comment_analysis_tasks.comment_analysis_task_async(job_id))
    asyncio.run(comment_analysis_tasks.comment_analysis_task_async(job_id))
    assert model.calls == 1
    assert len(model.inputs[0]["comments"]) == 1 and "author" not in str(model.inputs)
    async def verify():
        async with sessions() as db:
            job = await db.get(Job, job_id)
            batch = await db.get(ResearchCommentAnalysisBatch, job.result["batch_id"])
            item = await db.scalar(select(ResearchScreenedComment).where(ResearchScreenedComment.batch_id == batch.id))
            ledger = await db.scalar(select(AIUsageLedger).where(AIUsageLedger.company_id == seed["company_id"]))
            day = await db.scalar(select(AIUsageBudgetDay).where(AIUsageBudgetDay.company_id == seed["company_id"]))
            assert job.status == "succeeded" and batch.status == "completed"
            assert batch.result_json["topics"][0]["evidence_refs"] == ["comment_" + item.id]
            assert ledger.status == "succeeded" and ledger.budget_class == "automatic"
            assert ledger.result_json == {"comment_analysis_batch_id": batch.id}
            assert day.spent_micro_usd == 53 and day.reserved_micro_usd == 0
    asyncio.run(verify())
    listing = client.get(base + "/comment-analyses", headers=headers).json()
    assert listing["items"][0]["result"]["topics"][0]["topic"] == "Cách sử dụng"


def test_timeout_keeps_reservation_and_recovery_does_not_resubmit(screened, monkeypatch):
    client, sessions, seed, headers, base, body, _ = screened
    postgres_only(sessions)
    model = FakeGemini(fail=True)
    configured(monkeypatch, model)
    job_id = enqueue(screened)
    asyncio.run(comment_analysis_tasks.comment_analysis_task_async(job_id))
    async def recover():
        async with sessions() as db:
            job = await db.get(Job, job_id)
            job.status, job.lease_until = "queued", None
            await db.commit()
    asyncio.run(recover())
    asyncio.run(comment_analysis_tasks.comment_analysis_task_async(job_id))
    assert model.calls == 1
    async def verify():
        async with sessions() as db:
            ledger = await db.scalar(select(AIUsageLedger).where(AIUsageLedger.company_id == seed["company_id"]))
            assert ledger.status == "unknown" and ledger.result_json is None
            assert (await db.get(Job, job_id)).error["code"] == "provider_outcome_unknown"
    asyncio.run(verify())


@pytest.mark.parametrize("change", ["lease_lost", "suppress_during_call"])
def test_lost_lease_or_erasure_prevents_result_write(screened, monkeypatch, change):
    client, sessions, seed, headers, base, body, _ = screened
    postgres_only(sessions)
    job_id = enqueue(screened)
    def hook():
        async def mutate():
            async with sessions() as db:
                if change == "lease_lost":
                    job = await db.get(Job, job_id)
                    job.claim_token = str(uuid4())
                    job.lease_until = utcnow() + timedelta(minutes=5)
                else:
                    from services.research.comment_analysis import lock_source
                    from services.research.comment_suppression import suppress_comment_tree
                    await lock_source(db, seed["company_id"], seed["source_id"])
                    version = await db.get(ResearchCommentVersion, body["comments"][0]["version_id"])
                    await suppress_comment_tree(db, version=version, actor_id=seed["user_id"], reason="subject_request")
                await db.commit()
        asyncio.run(mutate())
    model = FakeGemini(hook=hook)
    configured(monkeypatch, model)
    asyncio.run(comment_analysis_tasks.comment_analysis_task_async(job_id))
    assert model.calls == 1
    async def verify():
        async with sessions() as db:
            job = await db.get(Job, job_id)
            batch = await db.get(ResearchCommentAnalysisBatch, job.result["batch_id"])
            assert batch.result_json is None
            if change == "suppress_during_call":
                assert batch.status == "suppressed"
                items = (await db.scalars(select(ResearchScreenedComment).where(ResearchScreenedComment.batch_id == batch.id))).all()
                assert all(item.excerpt_ciphertext is None for item in items)
    asyncio.run(verify())


def test_budget_wait_keeps_excerpts_without_call(screened, monkeypatch):
    client, sessions, seed, headers, base, body, _ = screened
    postgres_only(sessions)
    model = FakeGemini()
    configured(monkeypatch, model)
    job_id = enqueue(screened)
    async def exhaust():
        async with sessions() as db:
            db.add(AIUsageBudgetDay(company_id=seed["company_id"], budget_date=ai_budget._budget_date(),
                limit_micro_usd=2_000_000, spent_micro_usd=2_000_000, reserved_micro_usd=0))
            await db.commit()
    asyncio.run(exhaust())
    asyncio.run(comment_analysis_tasks.comment_analysis_task_async(job_id))
    assert model.calls == 0
    async def verify():
        async with sessions() as db:
            job = await db.get(Job, job_id)
            batch = await db.get(ResearchCommentAnalysisBatch, job.result["batch_id"])
            assert job.status == "queued" and job.result["retry_not_before"]
            assert batch.status == "deferred_budget"
    asyncio.run(verify())


def test_erasure_is_limited_to_batches_using_the_removed_version(screened):
    client, sessions, seed, headers, base, body, _ = screened
    job_id = enqueue(screened)
    comments = client.get(base + f"/posts/{asyncio.run(evidence_for(sessions, body))}/comments", headers=headers).json()["comments"]
    other_id = next(item["id"] for item in comments if item["id"] != body["comments"][0]["version_id"] and not item["is_reply"])
    other = {**body, "request_key": str(uuid4()), "comments": [{"version_id": other_id, "text": "Second independent excerpt"}]}
    response = client.post(base + "/comment-analyses", headers=headers, json=other)
    assert response.status_code == 202
    deleted = client.post(base + f"/comments/{body['comments'][0]['version_id']}/suppress", headers=headers,
        json={"reason": "subject_request"})
    assert deleted.status_code == 200
    async def verify():
        async with sessions() as db:
            affected = await db.get(ResearchCommentAnalysisBatch, (await db.get(Job, job_id)).result["batch_id"])
            independent = await db.get(ResearchCommentAnalysisBatch, (await db.get(Job, response.json()["job_id"])).result["batch_id"])
            assert affected.status == "suppressed" and independent.status == "queued"
            await purge_expired_screened_comments(db, utcnow() + timedelta(days=91))
            await db.commit()
            await db.refresh(independent)
            assert independent.status == "expired" and independent.result_json is None
    asyncio.run(verify())


async def evidence_for(sessions, body):
    async with sessions() as db:
        return (await db.get(ResearchCommentVersion, body["comments"][0]["version_id"])).evidence_id


def test_cross_tenant_api_and_sql_cannot_bind_another_workspace_comment(screened):
    client, sessions, seed, headers, base, body, _ = screened
    postgres_only(sessions)
    from tests.helpers.comment_frontier import seed_comment_frontier
    from database.models import Company, User
    from sqlalchemy import delete
    from sqlalchemy.exc import IntegrityError
    other = asyncio.run(seed_comment_frontier(sessions))
    try:
        asyncio.run(collect(sessions, other))
        async def other_id():
            async with sessions() as db:
                return await db.scalar(select(ResearchCommentVersion.id).where(
                    ResearchCommentVersion.company_id == other["company_id"]).limit(1))
        version_id = asyncio.run(other_id())
        cross = {**body, "request_key": str(uuid4()), "comments": [{"version_id": version_id, "text": "Cross-tenant fixture"}]}
        response = client.post(base + "/comment-analyses", headers=headers, json=cross)
        assert response.status_code == 409 and response.json()["error"]["code"] == "comment_selected_version_unavailable"
        job_id = enqueue(screened)
        async def attempt_sql():
            async with sessions() as db:
                batch_id = (await db.get(Job, job_id)).result["batch_id"]
                db.add(ResearchScreenedComment(company_id=seed["company_id"], source_id=seed["source_id"],
                    batch_id=batch_id, version_id=version_id, excerpt_hash="a"*64,
                    source_content_hash="b"*64, content_edited=True))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
        asyncio.run(attempt_sql())
    finally:
        async def cleanup():
            async with sessions() as db:
                await db.execute(delete(Company).where(Company.id == other["company_id"]))
                await db.execute(delete(User).where(User.id == other["user_id"]))
                await db.commit()
        asyncio.run(cleanup())


def test_screened_comment_schema_matches_fresh_and_upgrade():
    import os
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    fresh, upgrade = os.getenv("POSTGRES_SCREENED_FRESH_URL"), os.getenv("POSTGRES_SCREENED_UPGRADE_URL")
    if not fresh or not upgrade:
        pytest.skip("Disposable fresh/upgrade URLs are required for catalog comparison")
    def snapshot(connection):
        inspector = inspect(connection)
        result = {}
        for table in ("research_comment_versions", "research_comment_analysis_batches", "research_screened_comments"):
            result[table] = {
                "columns": sorted((c["name"], str(c["type"]), c["nullable"], str(c["default"])) for c in inspector.get_columns(table)),
                "checks": sorted((c["name"], c["sqltext"]) for c in inspector.get_check_constraints(table)),
                "unique": sorted((c["name"], c["column_names"]) for c in inspector.get_unique_constraints(table)),
                "indexes": sorted((c["name"], c["column_names"], c["unique"]) for c in inspector.get_indexes(table)),
                "foreign_keys": sorted((c["name"], c["constrained_columns"], c["referred_table"], c["referred_columns"], c["options"]) for c in inspector.get_foreign_keys(table)),
            }
        return result
    async def read(url):
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.connect() as connection:
            result = await connection.run_sync(snapshot)
        await engine.dispose()
        return result
    assert asyncio.run(read(fresh)) == asyncio.run(read(upgrade))
