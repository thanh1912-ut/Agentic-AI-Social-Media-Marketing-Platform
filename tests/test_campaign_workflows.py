"""API tests for tenant-scoped campaigns, immutable versions and approval gates."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import (
    Base,
    Brand,
    Campaign,
    CampaignPost,
    Document,
    Job,
    KnowledgeChunk,
    PostVersion,
    new_id,
)
from packages.contracts import GeneratedPost, SourceReference
from packages.prompts import CONTENT_REVISE_SYSTEM_PROMPT
from services.api import campaign_workflows
from services.api import job_service
from services.api import jobs as job_routes
from services.api.db import get_db
from services.api.main import app
from services.api.storage import LocalObjectStorage
from services.agents.content_agent import ContentAgent
from services.worker import content_tasks


def test_job_dispatch_uses_dedicated_document_and_agent_queues(monkeypatch) -> None:
    import services.worker.celery_app as celery_module
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(job_service, "settings", SimpleNamespace(inline_jobs=False))
    monkeypatch.setattr(celery_module.celery_app, "send_task", lambda name, **kwargs: calls.append((name, kwargs)))
    asyncio.run(job_service.dispatch_document_job("doc-job", "doc-1", ["doc-1", "doc-2"]))
    asyncio.run(job_service.dispatch_content_generation_job("content-job"))
    assert calls == [
        ("services.worker.tasks.ingest_document_task", {"args": ["doc-job", "doc-1", ["doc-1", "doc-2"]], "queue": "default"}),
        ("services.worker.content_tasks.content_generation_task", {"args": ["content-job"], "queue": "agent"}),
    ]


def test_job_recovery_dispatches_queued_content_revision(workflow_api, monkeypatch) -> None:
    from types import SimpleNamespace
    import services.worker.celery_app as celery_module

    _client, session_factory = workflow_api
    owner = _register(_client, "content-recovery@example.com")
    job_id = new_id()
    now = datetime.now(timezone.utc)
    dispatched = []

    async def seed_job():
        async with session_factory() as db:
            db.add(Job(
                id=job_id,
                company_id=owner["active_workspace_id"],
                created_by=owner["user"]["id"],
                kind="content_revise",
                title="AI sửa bài",
                status="queued",
                progress=0,
                attempts=0,
                result={"campaign_id": "campaign-for-recovery", "post_id": "post-for-recovery", "post_version": 1},
                created_at=now,
                updated_at=now,
            ))
            await db.commit()

    asyncio.run(seed_job())
    monkeypatch.setattr(job_service, "settings", SimpleNamespace(inline_jobs=False, max_job_attempts=3, job_lease_minutes=15))
    monkeypatch.setattr(celery_module.celery_app, "send_task", lambda name, **kwargs: dispatched.append((name, kwargs)))

    async def recover():
        async with session_factory() as db:
            return await job_service.dispatch_queued_jobs(db)

    assert asyncio.run(recover()) == 1
    assert dispatched == [
        ("services.worker.content_tasks.content_generation_task", {"args": [job_id], "queue": "agent"}),
    ]


def test_failed_content_revision_job_can_be_retried(workflow_api, monkeypatch) -> None:
    client, session_factory = workflow_api
    owner = _register(client, "content-retry@example.com")
    workspace_id = owner["active_workspace_id"]
    job_id = new_id()
    now = datetime.now(timezone.utc)

    async def seed_job():
        async with session_factory() as db:
            db.add(Job(
                id=job_id,
                company_id=workspace_id,
                created_by=owner["user"]["id"],
                kind="content_revise",
                title="AI sửa bài",
                status="failed",
                progress=100,
                attempts=1,
                result={"campaign_id": "campaign-for-retry", "post_id": "post-for-retry", "post_version": 1},
                error={"code": "deepseek_request_failed", "message": "Provider timeout", "retryable": True},
                created_at=now,
                updated_at=now,
            ))
            await db.commit()

    asyncio.run(seed_job())
    dispatched: list[str] = []

    async def dispatch(job_id: str) -> None:
        dispatched.append(job_id)

    monkeypatch.setattr(job_routes, "dispatch_content_generation_job", dispatch)
    response = client.post(
        f"/api/v1/jobs/{job_id}/retry",
        headers={"X-CSRF-Token": client.cookies.get("agentic_csrf")},
    )
    assert response.status_code == 202, response.text
    assert response.json()["job"]["kind"] == "content_revise"
    assert response.json()["job"]["status"] == "queued"
    assert dispatched == [job_id]


@pytest.fixture
def workflow_api():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_db():
        async with session_factory() as session:
            yield session

    asyncio.run(setup())
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _register(client: TestClient, email: str) -> dict:
    response = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "safe-test-password",
        "full_name": "Test Owner",
        "company_name": f"Company {email}",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_campaign_api_has_tenant_scoping_and_versioned_approval(workflow_api) -> None:
    client, _session_factory = workflow_api
    owner = _register(client, "owner-campaign@example.com")
    workspace_id = owner["active_workspace_id"]
    created = client.post(f"/api/v1/workspaces/{workspace_id}/campaigns", headers={"X-CSRF-Token": client.cookies.get("agentic_csrf")}, json={
        "name": "Bếp Mộc mùa hè",
        "brief": {
            "objective": "engagement",
            "audience": ["Gia đình địa phương"],
            "product_ids": [],
            "key_message": "Món Việt dễ chọn cho bữa cơm gia đình",
            "must_include": [],
            "must_avoid": ["cam kết chữa bệnh"],
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        "content_plan": {
            "strategy_summary": "Tập trung món cơm gà, bữa cơm ấm áp cho gia đình.",
            "slots": [{
                "id": "slot-family-dinner",
                "scheduled_date": "2026-09-15",
                "pillar": "product",
                "format": "text",
                "topic": "Món cơm gà cho bữa tối cuối tuần",
            }],
        },
        "pillars": ["product"],
        "channels": ["facebook_page"],
    })
    assert created.status_code == 201, created.text
    campaign = created.json()
    assert campaign["post_count"] == 0
    campaign_url = f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign['id']}"
    update_body = {
        "version": campaign["version"],
        "name": "Bếp Mộc mùa thu",
        "brief": {
            **campaign["brief"],
            "key_message": "Bữa cơm Việt ấm áp cho ngày mưa.",
        },
        "content_plan": {
            "strategy_summary": campaign["content_plan"]["strategy_summary"],
            "slots": [{key: slot[key] for key in ("id", "scheduled_date", "pillar", "format", "topic")} for slot in campaign["content_plan"]["slots"]],
        },
        "pillars": campaign["pillars"],
        "channels": campaign["channels"],
    }
    updated_campaign = client.patch(
        campaign_url,
        headers={"X-CSRF-Token": client.cookies.get("agentic_csrf")},
        json=update_body,
    )
    assert updated_campaign.status_code == 200, updated_campaign.text
    assert updated_campaign.json()["version"] == campaign["version"] + 1
    assert updated_campaign.json()["name"] == "Bếp Mộc mùa thu"
    assert updated_campaign.json()["brief"]["key_message"] == "Bữa cơm Việt ấm áp cho ngày mưa."
    assert updated_campaign.json()["content_plan"] == campaign["content_plan"]
    stale_campaign = client.patch(
        campaign_url,
        headers={"X-CSRF-Token": client.cookies.get("agentic_csrf")},
        json=update_body,
    )
    assert stale_campaign.status_code == 409
    assert stale_campaign.json()["error"]["code"] == "version_conflict"

    other = TestClient(app)
    with other:
        second = _register(other, "other-campaign@example.com")
        denied = other.get(f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign['id']}")
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "not_found"

    csrf = client.cookies.get("agentic_csrf")
    headers = {"X-CSRF-Token": csrf}
    created_post = client.post(
        f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign['id']}/posts",
        headers=headers,
        json={"pillar": "product", "format": "text", "caption": "Món ngon cho cả nhà", "hashtags": ["#BepMoc"]},
    )
    assert created_post.status_code == 201, created_post.text
    post_id = created_post.json()["id"]
    post_url = f"/api/v1/workspaces/{workspace_id}/posts/{post_id}"

    first_edit = client.patch(post_url, headers=headers, json={"version": 1, "caption": "Bài đã được biên tập"})
    assert first_edit.status_code == 200, first_edit.text
    assert first_edit.json()["version"] == 2
    assert first_edit.json()["current"]["caption"] == "Bài đã được biên tập"

    stale = client.patch(post_url, headers=headers, json={"version": 1, "caption": "Bản cũ"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"

    submitted = client.post(f"{post_url}/submit-approval", headers=headers, json={"version": 2})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "needs_review"
    approved = client.post(f"{post_url}/approval", headers=headers, json={"version": 2, "decision": "approved"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["current"]["approved_by"] == owner["user"]["id"]

    second_edit = client.patch(post_url, headers=headers, json={"version": 2, "caption": "Bài chỉnh sau khi duyệt"})
    assert second_edit.status_code == 200, second_edit.text
    assert second_edit.json()["version"] == 3
    assert second_edit.json()["requires_reapproval"] is True
    versions = client.get(f"{post_url}/versions").json()
    assert versions["current_version"] == 3
    assert versions["versions"][0]["caption"] == "Bài chỉnh sau khi duyệt"
    assert versions["versions"][-1]["caption"] == "Món ngon cho cả nhà"


def test_content_generation_requires_current_confirmed_brand_profile(workflow_api, monkeypatch) -> None:
    client, _session_factory = workflow_api
    owner = _register(client, "content-confirmation@example.com")
    workspace_id = owner["active_workspace_id"]
    csrf = client.cookies.get("agentic_csrf")
    campaign = client.post(f"/api/v1/workspaces/{workspace_id}/campaigns", headers={"X-CSRF-Token": csrf}, json={
        "name": "Bếp Mộc",
        "brief": {
            "objective": "awareness",
            "audience": ["Gia đình"],
            "product_ids": [],
            "key_message": "Món Việt cho bữa cơm gia đình",
            "must_include": [],
            "must_avoid": [],
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        "content_plan": {
            "strategy_summary": "Tập trung món cơm gà, bữa cơm ấm áp cho gia đình.",
            "slots": [{
                "id": "slot-family-dinner",
                "scheduled_date": "2026-09-15",
                "pillar": "product",
                "format": "text",
                "topic": "Món cơm gà cho bữa tối cuối tuần",
            }],
        },
        "pillars": ["product"],
        "channels": ["facebook_page"],
    })
    assert campaign.status_code == 201, campaign.text
    async def no_dispatch(_job_id):
        return None
    monkeypatch.setattr(campaign_workflows, "dispatch_content_generation_job", no_dispatch)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/posts/generate",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "generation-unconfirmed-001"},
        json={"campaign_id": campaign.json()["id"], "count": 1},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "brand_profile_not_confirmed"


def test_content_slot_reservation_releases_on_failure_and_cancel_and_reacquires_on_retry(workflow_api, monkeypatch) -> None:
    client, session_factory = workflow_api
    owner = _register(client, "content-slot-retry@example.com")
    workspace_id = owner["active_workspace_id"]
    csrf = client.cookies.get("agentic_csrf")
    headers = {"X-CSRF-Token": csrf}
    campaign_response = client.post(f"/api/v1/workspaces/{workspace_id}/campaigns", headers=headers, json={
        "name": "Bếp Mộc",
        "brief": {
            "objective": "awareness", "audience": ["Gia đình"], "product_ids": [],
            "key_message": "Cơm gà cho bữa cơm gia đình", "must_include": [], "must_avoid": [],
            "start_date": "2026-09-01", "end_date": "2026-09-30",
        },
        "content_plan": {"strategy_summary": "Bữa cơm ấm áp", "slots": [{
            "id": "slot-retry", "scheduled_date": "2026-09-15", "pillar": "product",
            "format": "text", "topic": "Cơm gà cho gia đình",
        }]},
        "pillars": ["product"], "channels": ["facebook_page"],
    })
    assert campaign_response.status_code == 201, campaign_response.text
    profile = client.get(f"/api/v1/workspaces/{workspace_id}/brand-profile").json()
    confirmed = client.patch(f"/api/v1/workspaces/{workspace_id}/brand-profile", headers=headers, json={
        "version": profile["version"],
        "fields": [
            {"key": "business_name", "value": "Bếp Mộc"},
            {"key": "description", "value": "Quán món Việt cho gia đình"},
            {"key": "products", "value": [{"name": "Cơm gà"}]},
            {"key": "target_audience", "value": ["Gia đình"]},
            {"key": "tone_keywords", "value": ["Thân thiện"]},
        ],
        "confirm": True,
    })
    assert confirmed.status_code == 200, confirmed.text

    async def no_dispatch(_job_id):
        return None

    monkeypatch.setattr(campaign_workflows, "dispatch_content_generation_job", no_dispatch)
    monkeypatch.setattr(job_routes, "dispatch_content_generation_job", no_dispatch)
    accepted = client.post(
        f"/api/v1/workspaces/{workspace_id}/posts/generate",
        headers={**headers, "Idempotency-Key": "slot-retry-job-0001"},
        json={"campaign_id": campaign_response.json()["id"], "count": 1, "slot_id": "slot-retry"},
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]

    async def read_state():
        async with session_factory() as db:
            return await db.get(Job, job_id), await db.get(Campaign, campaign_response.json()["id"])

    queued_job, reserved_campaign = asyncio.run(read_state())
    assert queued_job.result["campaign_version"] == reserved_campaign.version

    monkeypatch.setattr(content_tasks, "SessionLocal", session_factory)
    asyncio.run(content_tasks._fail(job_id, content_tasks.ContentGenerationFailure("deepseek_request_failed", "temporary error"), attempts=1))

    failed_job, released_campaign = asyncio.run(read_state())
    assert failed_job.status == "failed"
    assert released_campaign.version == campaign_response.json()["version"] + 2
    assert failed_job.result["campaign_version"] == released_campaign.version, (
        f"job context version={failed_job.result['campaign_version']}, campaign version={released_campaign.version}"
    )
    assert "generation_job_id" not in released_campaign.content_plan_json["slots"][0]

    retried = client.post(f"/api/v1/jobs/{job_id}/retry", headers=headers)
    assert retried.status_code == 202, retried.text
    queued_job, reserved_campaign = asyncio.run(read_state())
    assert queued_job.status == "queued"
    assert reserved_campaign.version == released_campaign.version + 1
    assert reserved_campaign.content_plan_json["slots"][0]["generation_job_id"] == job_id
    assert queued_job.result["campaign_version"] == reserved_campaign.version

    cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    cancelled_job, cancelled_campaign = asyncio.run(read_state())
    assert cancelled_job.status == "cancelled"
    assert cancelled_campaign.version == reserved_campaign.version + 1
    assert "generation_job_id" not in cancelled_campaign.content_plan_json["slots"][0]


def test_content_generation_job_persists_cited_draft_and_is_idempotent(workflow_api, monkeypatch) -> None:
    client, session_factory = workflow_api
    owner = _register(client, "content-owner@example.com")
    workspace_id = owner["active_workspace_id"]
    csrf = client.cookies.get("agentic_csrf")
    headers = {"X-CSRF-Token": csrf}
    campaign_response = client.post(f"/api/v1/workspaces/{workspace_id}/campaigns", headers=headers, json={
        "name": "Bếp Mộc",
        "brief": {
            "objective": "awareness",
            "audience": ["Gia đình"],
            "product_ids": [],
            "key_message": "Cơm gà cho bữa cơm gia đình",
            "must_include": [],
            "must_avoid": [],
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        "content_plan": {
            "strategy_summary": "Tập trung món cơm gà, bữa cơm ấm áp cho gia đình.",
            "slots": [{
                "id": "slot-family-dinner",
                "scheduled_date": "2026-09-15",
                "pillar": "product",
                "format": "text",
                "topic": "Món cơm gà cho bữa tối cuối tuần",
            }],
        },
        "pillars": ["product"],
        "channels": ["facebook_page"],
    })
    assert campaign_response.status_code == 201, campaign_response.text
    campaign_id = campaign_response.json()["id"]
    profile = client.get(f"/api/v1/workspaces/{workspace_id}/brand-profile").json()
    updated = client.patch(
        f"/api/v1/workspaces/{workspace_id}/brand-profile",
        headers=headers,
        json={"version": profile["version"], "fields": [
            {"key": "business_name", "value": "Bếp Mộc"},
            {"key": "description", "value": "Quán món Việt cho gia đình"},
            {"key": "products", "value": [{"name": "Cơm gà"}]},
            {"key": "target_audience", "value": ["Gia đình"]},
            {"key": "tone_keywords", "value": ["Thân thiện"]},
        ], "confirm": True},
    )
    assert updated.status_code == 200, updated.text
    now = datetime.now(timezone.utc)
    document_id = new_id()
    source_id = new_id()
    source_hash = "b" * 64
    chunk_text = "Bếp Mộc phục vụ cơm gà với nguyên liệu tươi cho bữa cơm gia đình."

    async def seed_source():
        async with session_factory() as db:
            brand = await db.scalar(select(Brand).where(Brand.company_id == workspace_id))
            document = Document(
                id=document_id, company_id=workspace_id, source_id=source_id, source_version="1",
                filename="menu.txt", kind="text", mime_type="text/plain", size_bytes=len(chunk_text),
                source_hash=source_hash, parser_version="m2-parser-v1", storage_key=f"{workspace_id}/{document_id}/menu.txt",
                status="ready", is_active=True, normalized_json={"text_blocks": [{"text": chunk_text}]},
                knowledge_status="ready", retrieval_mode="lexical", uploaded_by=owner["user"]["id"], created_at=now, updated_at=now,
            )
            db.add(document)
            db.add(KnowledgeChunk(
                chunk_id=f"{workspace_id}:{source_id}:{source_hash}:chunk-1", company_id=workspace_id,
                brand_id=brand.id, source_id=source_id, document_id=document_id, source_version="1",
                source_hash=source_hash, locator="page=1", text=chunk_text, token_count=15, kind="text",
                parser_version="m2-parser-v1", chunker_version="vi-token-window-v2",
                embedding_provider="none", embedding_model_version="lexical-v1", is_active=True,
                created_at=now, updated_at=now,
            ))
            await db.commit()

    asyncio.run(seed_source())
    async def no_dispatch(_job_id):
        return None
    monkeypatch.setattr(campaign_workflows, "dispatch_content_generation_job", no_dispatch)
    request_headers = {**headers, "Idempotency-Key": "generation-content-0001"}
    body = {"campaign_id": campaign_id, "count": 1, "slot_id": "slot-family-dinner"}
    accepted = client.post(f"/api/v1/workspaces/{workspace_id}/posts/generate", headers=request_headers, json=body)
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    queued_campaign = client.get(f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}").json()
    assert queued_campaign["version"] == campaign_response.json()["version"] + 1
    assert queued_campaign["content_plan"]["slots"][0]["generation_job_id"] == job_id
    duplicate = client.post(f"/api/v1/workspaces/{workspace_id}/posts/generate", headers=request_headers, json=body)
    assert duplicate.status_code == 202
    assert duplicate.json()["job_id"] == job_id
    another_request = client.post(
        f"/api/v1/workspaces/{workspace_id}/posts/generate",
        headers={**headers, "Idempotency-Key": "generation-content-0002"},
        json=body,
    )
    assert another_request.status_code == 409
    assert another_request.json()["error"]["code"] == "content_slot_generation_pending"

    class FixedModel:
        last_system_prompt = ""
        last_input_payload = None
        omit_citations = False

        def generate(self, *, system_prompt, input_payload, response_model):
            self.last_system_prompt = system_prompt
            self.last_input_payload = input_payload
            source = input_payload["sources"][0]
            return GeneratedPost(
                base_version="ignored", version=1, channel="ignored", caption="Cơm gà Bếp Mộc cho bữa cơm gia đình.",
                hashtags=["#ModelOutput"], image_brief="Mô tả ảnh do model tạo",
                citations=[] if self.omit_citations else [SourceReference(
                    source_id=source["source_id"], document_id=source["document_id"],
                    source_version=source["source_version"], locator=source["locator"],
                    excerpt="Bếp Mộc phục vụ cơm gà",
                )],
            ), None

    monkeypatch.setattr(content_tasks, "SessionLocal", session_factory)
    fixed_model = FixedModel()
    asyncio.run(content_tasks.content_generation_task_async(job_id, agent=ContentAgent(fixed_model)))
    model_payload = json.dumps(fixed_model.last_input_payload, ensure_ascii=False)
    assert fixed_model.last_input_payload["content_requirements"]["strategy_summary"] == "Tập trung món cơm gà, bữa cơm ấm áp cho gia đình."
    assert fixed_model.last_input_payload["content_requirements"]["slot_topic"] == "Món cơm gà cho bữa tối cuối tuần"
    assert fixed_model.last_input_payload["content_requirements"]["start_date"] == "2026-09-15"
    assert "slot-family-dinner" not in model_payload

    async def check_saved_draft():
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            posts = (await db.scalars(select(CampaignPost).where(CampaignPost.campaign_id == campaign_id))).all()
            versions = (await db.scalars(select(PostVersion).where(PostVersion.campaign_id == campaign_id))).all()
            saved_campaign = await db.get(Campaign, campaign_id)
            return job, posts, versions, saved_campaign

    job, posts, versions, saved_campaign = asyncio.run(check_saved_draft())
    assert job.status == "succeeded"
    assert len(posts) == len(versions) == 1
    assert saved_campaign.version == campaign_response.json()["version"] + 2
    assert saved_campaign.content_plan_json["slots"][0]["generated_post_id"] == posts[0].id
    assert "generation_job_id" not in saved_campaign.content_plan_json["slots"][0]
    assert posts[0].status == "draft"
    assert versions[0].source == "ai_generated"
    assert versions[0].generation_job_id == job_id
    assert posts[0].current_json["citations"][0]["document_id"] == document_id
    assert posts[0].current_json["content_slot_id"] == "slot-family-dinner"
    assert posts[0].current_json["planned_date"] == "2026-09-15"
    assert job.result["estimated_cost_available"] is False

    duplicate_after_completion = client.post(f"/api/v1/workspaces/{workspace_id}/posts/generate", headers=request_headers, json=body)
    assert duplicate_after_completion.status_code == 202
    assert duplicate_after_completion.json()["job_id"] == job_id
    reused_slot = client.post(
        f"/api/v1/workspaces/{workspace_id}/posts/generate",
        headers={**headers, "Idempotency-Key": "generation-content-0003"},
        json=body,
    )
    assert reused_slot.status_code == 409
    assert reused_slot.json()["error"]["code"] == "content_slot_already_generated"
    current_campaign = client.get(f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}").json()
    locked_update = client.patch(
        f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}",
        headers=headers,
        json={
            "version": current_campaign["version"],
            "name": current_campaign["name"],
            "brief": current_campaign["brief"],
            "content_plan": {"strategy_summary": current_campaign["content_plan"]["strategy_summary"], "slots": []},
            "pillars": current_campaign["pillars"],
            "channels": current_campaign["channels"],
        },
    )
    assert locked_update.status_code == 409
    assert locked_update.json()["error"]["code"] == "content_slot_locked"

    post_url = f"/api/v1/workspaces/{workspace_id}/posts/{posts[0].id}"
    submitted = client.post(f"{post_url}/submit-approval", headers=headers, json={"version": 1})
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"{post_url}/approval", headers=headers, json={"version": 1, "decision": "approved"})
    assert approved.status_code == 200, approved.text

    revise_headers = {**headers, "Idempotency-Key": "revise-content-0001"}
    revise_body = {"version": 1, "instruction": "Rút gọn caption, giữ nguyên hashtag", "scope": "caption"}
    revise_response = client.post(f"{post_url}/revise", headers=revise_headers, json=revise_body)
    assert revise_response.status_code == 202, revise_response.text
    revise_job_id = revise_response.json()["job_id"]
    assert revise_response.json()["job"]["kind"] == "content_revise"
    duplicate_revise = client.post(f"{post_url}/revise", headers=revise_headers, json=revise_body)
    assert duplicate_revise.status_code == 202
    assert duplicate_revise.json()["job_id"] == revise_job_id

    asyncio.run(content_tasks.content_generation_task_async(revise_job_id, agent=ContentAgent(fixed_model)))

    async def check_revised_post():
        async with session_factory() as db:
            revise_job = await db.get(Job, revise_job_id)
            saved_post = await db.get(CampaignPost, posts[0].id)
            saved_versions = (await db.scalars(select(PostVersion).where(
                PostVersion.campaign_id == campaign_id,
                PostVersion.post_id == posts[0].id,
            ).order_by(PostVersion.version.desc()))).all()
            return revise_job, saved_post, saved_versions

    revise_job, revised_post, revised_versions = asyncio.run(check_revised_post())
    assert revise_job.status == "succeeded", revise_job.error
    assert revised_post.current_version == 2
    assert revised_post.status == "draft"
    assert revised_post.requires_reapproval is True
    assert revised_post.current_json["hashtags"] == ["#ModelOutput"]
    assert revised_post.current_json["image_brief"] == "Mô tả ảnh do model tạo"
    assert revised_versions[0].source == "ai_revised"
    assert revised_versions[0].generation_job_id == revise_job_id
    assert revised_versions[1].content_json["caption"] == posts[0].current_json["caption"]
    assert fixed_model.last_system_prompt == CONTENT_REVISE_SYSTEM_PROMPT
    assert fixed_model.last_input_payload["content_requirements"]["existing_post"]["caption"] == posts[0].current_json["caption"]

    fixed_model.omit_citations = True
    ungrounded_response = client.post(
        f"{post_url}/revise",
        headers={**headers, "Idempotency-Key": "revise-content-0002"},
        json={"version": 2, "instruction": "Thêm một tuyên bố mới", "scope": "caption"},
    )
    assert ungrounded_response.status_code == 202, ungrounded_response.text
    ungrounded_job_id = ungrounded_response.json()["job_id"]
    asyncio.run(content_tasks.content_generation_task_async(ungrounded_job_id, agent=ContentAgent(fixed_model)))

    async def check_ungrounded_revision():
        async with session_factory() as db:
            ungrounded_job = await db.get(Job, ungrounded_job_id)
            saved_post = await db.get(CampaignPost, posts[0].id)
            saved_version_count = await db.scalar(select(func.count()).select_from(PostVersion).where(
                PostVersion.campaign_id == campaign_id,
                PostVersion.post_id == posts[0].id,
            ))
            return ungrounded_job, saved_post, saved_version_count

    ungrounded_job, unchanged_post, saved_version_count = asyncio.run(check_ungrounded_revision())
    assert ungrounded_job.status == "failed"
    assert ungrounded_job.error["code"] == "content_citations_missing"
    assert unchanged_post.current_version == 2
    assert saved_version_count == 2


def test_export_writes_downloadable_csv_and_is_idempotent(workflow_api, tmp_path, monkeypatch) -> None:
    client, session_factory = workflow_api
    owner = _register(client, "export-owner@example.com")
    workspace_id = owner["active_workspace_id"]
    csrf = client.cookies.get("agentic_csrf")
    headers = {"X-CSRF-Token": csrf}
    campaign_response = client.post(f"/api/v1/workspaces/{workspace_id}/campaigns", headers=headers, json={
        "name": "Bếp Mộc",
        "brief": {
            "objective": "engagement",
            "audience": ["Gia đình"],
            "product_ids": [],
            "key_message": "Món nhà",
            "must_include": [],
            "must_avoid": [],
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        "pillars": ["product"],
        "channels": ["facebook_page"],
    })
    assert campaign_response.status_code == 201, campaign_response.text
    campaign_id = campaign_response.json()["id"]
    post_id = new_id()
    now = datetime.now(timezone.utc)
    content = {"caption": "=1+1, món nhà", "hashtags": ["#BepMoc"], "media": [], "citations": []}

    async def seed():
        async with session_factory() as db:
            db.add(CampaignPost(
                id=post_id, company_id=workspace_id, campaign_id=campaign_id,
                channel="facebook_page", pillar="product", format="text", status="draft",
                current_version=1, current_json=content, created_at=now, updated_at=now,
            ))
            db.add(PostVersion(
                id=new_id(), company_id=workspace_id, campaign_id=campaign_id,
                post_id=post_id, version=1, content_json=content, source="human",
                created_by=owner["user"]["id"], created_by_name="Test Owner", created_at=now,
            ))
            await db.commit()

    asyncio.run(seed())
    monkeypatch.setattr(campaign_workflows, "storage", LocalObjectStorage(tmp_path))
    export_headers = {**headers, "Idempotency-Key": "export-test-idempotency-001"}
    body = {"campaign_id": campaign_id, "format": "csv"}
    created = client.post(f"/api/v1/workspaces/{workspace_id}/exports", headers=export_headers, json=body)
    assert created.status_code == 202, created.text
    job = created.json()["job"]
    assert job["status"] == "succeeded"
    export_id = job["result"]["export_id"]

    repeated = client.post(f"/api/v1/workspaces/{workspace_id}/exports", headers=export_headers, json=body)
    assert repeated.status_code == 202
    assert repeated.json()["job_id"] == created.json()["job_id"]

    metadata = client.get(f"/api/v1/workspaces/{workspace_id}/exports/{export_id}")
    assert metadata.status_code == 200
    assert metadata.json()["size"] > 0
    download = client.get(f"/api/v1/workspaces/{workspace_id}/exports/{export_id}/download")
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment;")
    rows = list(csv.reader(io.StringIO(download.content.decode("utf-8-sig"))))
    assert rows[0][6] == "Nội dung"
    assert rows[1][6].startswith("'=1+1")

    xlsx_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/exports",
        headers={**headers, "Idempotency-Key": "export-xlsx-idempotency-001"},
        json={"campaign_id": campaign_id, "format": "xlsx"},
    )
    assert xlsx_response.status_code == 202, xlsx_response.text
    xlsx_id = xlsx_response.json()["job"]["result"]["export_id"]
    xlsx_download = client.get(f"/api/v1/workspaces/{workspace_id}/exports/{xlsx_id}/download")
    assert xlsx_download.status_code == 200
    workbook = load_workbook(io.BytesIO(xlsx_download.content), read_only=True, data_only=True)
    assert workbook.active.cell(row=2, column=7).value.startswith("'=1+1")
