"""Owned Meta comment boundary tests, synthetic adapter; not live Facebook."""
import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from database.models import (
    Company, Job, Membership, MetaPageConnection, ResearchCommentCheckpoint,
    ResearchCommentProcessingDecision, ResearchCommentVersion, ResearchSource, User,
)
from services.api import job_service
from services.api.db import FencedAsyncSession, get_db
from services.api.main import app
from services.api.dependencies import ACCESS_COOKIE
from services.api.security import create_access_token
from services.research import comment_quarantine
from services.research.public_comments import active_public_comment_decision
from services.worker import research_comments, research_tasks
from tests.helpers.comment_frontier import seed_comment_frontier
from tests.test_market_research_api import market_api as _market_api_fixture
from tests.test_research_comment_quarantine import item, page

market_api = _market_api_fixture


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.getenv("POSTGRES_OWNED_COMMENT_TEST_URL") else []))
def owned_api(market_api, monkeypatch, request):
    client, sessions, key = market_api
    engine = None
    original_db = app.dependency_overrides[get_db]
    if request.param == "postgres":
        engine = create_async_engine(os.environ["POSTGRES_OWNED_COMMENT_TEST_URL"], poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)
        async def postgres_db():
            async with sessions() as db:
                yield db
        app.dependency_overrides[get_db] = postgres_db
    monkeypatch.setattr(comment_quarantine, "settings", SimpleNamespace(
        meta_token_encryption_key=key, meta_token_encryption_key_previous=""))
    monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
    monkeypatch.setattr(research_comments, "SessionLocal", sessions)
    seed = asyncio.run(seed_comment_frontier(sessions))

    async def identity():
        async with sessions() as db:
            user = await db.get(User, seed["user_id"])
            checkpoint = await db.get(ResearchCommentCheckpoint, seed["checkpoint_id"])
            return create_access_token(user)[0], checkpoint.evidence_id
    token, evidence_id = asyncio.run(identity())
    client.cookies.set("agentic_csrf", "synthetic-owned-comment-csrf")
    headers = {"Authorization": "Bearer " + token, "X-CSRF-Token": "synthetic-owned-comment-csrf"}
    base = f"/api/v1/workspaces/{seed['company_id']}/market-research/sources/{seed['source_id']}"
    try:
        yield client, sessions, seed, headers, base, evidence_id
    finally:
        app.dependency_overrides[get_db] = original_db
        if engine is not None:
            async def cleanup():
                async with sessions() as db:
                    await db.execute(delete(Company).where(Company.id == seed["company_id"]))
                    await db.execute(delete(User).where(User.id == seed["user_id"]))
                    await db.commit()
                await engine.dispose()
            asyncio.run(cleanup())


async def collect(sessions, seed):
    work = await research_comments.prepare_comment_page(seed["checkpoint_id"],
        company_id=seed["company_id"], decision_id=seed["decision_id"])
    assert await research_comments.commit_comment_page(work, page(
        item(seed, text="Question 0901 234 567", likes=0, replies=1),
        item(seed, "456_2", text="Other question", likes=None), total=2))
    async with sessions() as db:
        child = await db.scalar(select(ResearchCommentCheckpoint).where(
            ResearchCommentCheckpoint.company_id == seed["company_id"],
            ResearchCommentCheckpoint.parent_key == "456_1"))
    work = await research_comments.prepare_comment_page(child.id,
        company_id=seed["company_id"], decision_id=seed["decision_id"])
    assert await research_comments.commit_comment_page(work,
        page(item(seed, "456_3", parent="456_1", text="Reply", likes=4), total=1))


def test_owned_posts_and_comments_preserve_reply_tree_and_unknown_reactions(owned_api):
    client, sessions, seed, headers, base, evidence = owned_api
    asyncio.run(collect(sessions, seed))
    posts = client.get(base + "/posts", headers=headers)
    assert posts.status_code == 200, posts.text
    assert any(post["id"] == evidence for post in posts.json()["posts"])
    response = client.get(base + f"/posts/{evidence}/comments", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert response.headers["cache-control"] == "no-store, private"
    assert data["coverage"]["mode"] == "meta_api_accessible_edges"
    assert data["coverage"]["returned_count"] == 3
    assert data["coverage"]["received_root_comments"] == 2
    assert data["coverage"]["received_replies"] == 1
    assert data["coverage"]["provider_reported_count_scope"] == "root_edge"
    assert data["coverage"]["pending_edges"] == 0
    assert data["coverage"]["history_complete"] is False
    assert data["provider_transmission_allowed"] is False
    by_text = {comment["text"]: comment for comment in data["comments"]}
    parent = next(row for row in data["comments"] if row["reply_count"] == 1)
    reply = by_text["Reply"]
    assert parent["likes"] == 0 and parent["reactions"] is None
    assert by_text["Other question"]["likes"] is None
    assert reply["is_reply"] and reply["parent_version_id"] == parent["id"] and reply["likes"] == 4
    assert not parent["is_reply"] and parent["parent_version_id"] is None
    assert not any(value in response.text for value in ("0901 234 567", '"456_1"', '"456_3"', "synthetic-test-token"))


@pytest.mark.parametrize("change", ["expired_version", "edited_anchor"])
def test_latest_version_and_cursor_never_resurface_old_candidate(owned_api, change):
    client, sessions, seed, headers, base, evidence = owned_api
    asyncio.run(collect(sessions, seed))
    path = base + f"/posts/{evidence}/comments"
    first = client.get(path, headers=headers, params={"limit": 1}).json()
    assert first["next_cursor"]
    anchor_id = first["comments"][0]["id"]

    async def edit():
        async with sessions() as db:
            old = await db.get(ResearchCommentVersion, anchor_id)
            replacement = ResearchCommentVersion(company_id=old.company_id, source_id=old.source_id,
                evidence_id=old.evidence_id,
                evidence_version_id=old.evidence_version_id, observation_id=old.observation_id,
                decision_id=old.decision_id, external_comment_id=old.external_comment_id,
                parent_key=old.parent_key, content_hash="f" * 64,
                candidate_ciphertext=old.candidate_ciphertext, redaction_json=old.redaction_json,
                redactor_version=old.redactor_version,
                captured_at=old.captured_at + timedelta(seconds=1), expires_at=old.expires_at,
                status="expired" if change == "expired_version" else "privacy_hold")
            if change == "expired_version":
                replacement.candidate_ciphertext = None
            db.add(replacement)
            await db.commit()
    asyncio.run(edit())
    stale = client.get(path, headers=headers, params={"cursor": first["next_cursor"]})
    assert stale.status_code == 409
    refreshed = client.get(path, headers=headers).json()
    assert anchor_id not in {row["id"] for row in refreshed["comments"]}
    if change == "expired_version":
        assert len(refreshed["comments"]) == 2


@pytest.mark.parametrize("change", ["page_reconnect", "connection_disabled", "decision_revoked", "viewer", "editor"])
def test_owned_read_and_crawl_require_current_owner_connection_and_scope(owned_api, change):
    client, sessions, seed, headers, base, evidence = owned_api
    asyncio.run(collect(sessions, seed))

    async def mutate():
        async with sessions() as db:
            if change == "page_reconnect":
                (await db.get(Company, seed["company_id"])).page_connection_state = "needs_reconnect"
            elif change == "connection_disabled":
                (await db.get(MetaPageConnection, seed["connection_id"])).active = False
            elif change == "decision_revoked":
                (await db.get(ResearchCommentProcessingDecision, seed["decision_id"])).status = "revoked"
            else:
                membership = await db.scalar(select(Membership).where(Membership.company_id == seed["company_id"]))
                membership.role = change
            await db.commit()
    asyncio.run(mutate())
    read = client.get(base + f"/posts/{evidence}/comments", headers=headers)
    queued = client.post(base + "/comments/crawl", headers=headers)
    if change in {"editor", "viewer"}:
        assert read.status_code == queued.status_code == 403
    else:
        assert read.status_code == 200 and read.json()["comments"] == []
        assert read.json()["status"] == "processing_required"
        assert queued.status_code == 409 and queued.json()["error"]["code"] == "comment_processing_required"


@pytest.mark.parametrize("sent", [False, True])
def test_manual_crawl_commits_before_dispatch_and_returns_existing_job(owned_api, monkeypatch, sent):
    client, sessions, seed, headers, base, _evidence = owned_api
    dispatched = []

    async def dispatch(job_id):
        async with sessions() as db:
            job = await db.get(Job, job_id)
            assert job is not None and job.status == "queued"
            assert job.result["source_id"] == seed["source_id"]
            assert job.result["decision_id"] == seed["decision_id"]
        dispatched.append(job_id)
        return sent
    monkeypatch.setattr(job_service, "dispatch_research_comments_job", dispatch)
    first = client.post(base + "/comments/crawl", headers=headers)
    assert first.status_code == 202, first.text
    job_id = first.json()["job_id"]
    repeat = client.post(base + "/comments/crawl", headers=headers)
    assert repeat.status_code == 202 and repeat.json()["job_id"] == job_id
    assert dispatched == [job_id]

    async def verify():
        async with sessions() as db:
            jobs = (await db.scalars(select(Job).where(Job.company_id == seed["company_id"], Job.kind == "research_comments"))).all()
            assert len(jobs) == 1
            assert jobs[0].dispatch_attempts == 1
            assert jobs[0].last_dispatch_error == (None if sent else "queue_unavailable")
    asyncio.run(verify())


def test_manual_crawl_requires_csrf_and_frontier_and_cannot_enqueue_public(owned_api, monkeypatch):
    client, sessions, seed, headers, base, _ = owned_api
    client.cookies.set(ACCESS_COOKIE, headers["Authorization"].removeprefix("Bearer "))
    assert client.post(base + "/comments/crawl").status_code == 403

    async def exhaust():
        async with sessions() as db:
            (await db.get(ResearchCommentCheckpoint, seed["checkpoint_id"])).pagination_exhausted = True
            await db.commit()
    asyncio.run(exhaust())
    response = client.post(base + "/comments/crawl", headers=headers)
    assert response.status_code == 409 and response.json()["error"]["code"] == "comment_frontier_unavailable"

    async def public():
        async with sessions() as db:
            source = await db.get(ResearchSource, seed["source_id"])
            source.source_type = "competitor_facebook_page"
            source.collection_mode = "public_web"
            await db.commit()
    asyncio.run(public())
    response = client.post(base + "/comments/crawl", headers=headers)
    assert response.status_code == 409 and response.json()["error"]["code"] == "comment_collector_unsupported"


def test_public_validator_does_not_expand_to_owned_collection(owned_api):
    _client, sessions, seed, _headers, _base, _evidence = owned_api

    async def verify():
        async with sessions() as db:
            source = await db.get(ResearchSource, seed["source_id"])
            assert await active_public_comment_decision(db, source) is None
            source.source_type = "competitor_facebook_page"
            source.collection_mode = "public_web"
            await db.commit()
        async with sessions() as db:
            stale = await db.get(ResearchSource, seed["source_id"])
        async with sessions() as db:
            source = await db.get(ResearchSource, seed["source_id"])
            source.source_type = "owned_facebook_page"
            await db.commit()
        async with sessions() as db:
            assert await active_public_comment_decision(db, stale) is None
    asyncio.run(verify())


def test_active_job_from_previous_decision_cannot_be_reinterpreted(owned_api, monkeypatch):
    client, sessions, seed, headers, base, _ = owned_api
    async def deferred(_job_id):
        return False
    monkeypatch.setattr(job_service, "dispatch_research_comments_job", deferred)
    first = client.post(base + "/comments/crawl", headers=headers)
    assert first.status_code == 202

    async def replace_decision():
        async with sessions() as db:
            old = await db.get(ResearchCommentProcessingDecision, seed["decision_id"])
            db.add(ResearchCommentProcessingDecision(company_id=seed["company_id"], source_id=seed["source_id"],
                policy_revision_id=seed["policy_id"], status="active", assessed_by=seed["user_id"],
                assessment_reference="Changed synthetic local scope", created_at=old.created_at + timedelta(seconds=1),
                valid_until=old.valid_until))
            await db.commit()
    asyncio.run(replace_decision())
    changed = client.post(base + "/comments/crawl", headers=headers)
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "comment_job_context_changed"


def test_owned_endpoints_cannot_read_or_enqueue_another_tenants_source(owned_api):
    client, sessions, seed, headers, base, evidence = owned_api
    other = asyncio.run(seed_comment_frontier(sessions))
    try:
        cross = base.replace(seed["company_id"], other["company_id"])
        async def identity():
            async with sessions() as db:
                return create_access_token(await db.get(User, other["user_id"]))[0]
        other_headers = {**headers, "Authorization": "Bearer " + asyncio.run(identity())}
        for path in (cross + "/posts", cross + f"/posts/{evidence}/comments"):
            assert client.get(path, headers=other_headers).status_code == 404
        assert client.post(cross + "/comments/crawl", headers=other_headers).status_code == 404
        async def verify():
            async with sessions() as db:
                assert await db.scalar(select(Job.id).where(Job.company_id.in_([seed["company_id"], other["company_id"]]))) is None
        asyncio.run(verify())
    finally:
        async def cleanup():
            async with sessions() as db:
                await db.execute(delete(Company).where(Company.id == other["company_id"]))
                await db.execute(delete(User).where(User.id == other["user_id"]))
                await db.commit()
        asyncio.run(cleanup())
