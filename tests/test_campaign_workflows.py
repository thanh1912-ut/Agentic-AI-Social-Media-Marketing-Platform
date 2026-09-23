"""API tests for tenant-scoped campaigns, immutable versions and approval gates."""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import (
    Base,
    Brand,
    CampaignPost,
    Document,
    Job,
    KnowledgeChunk,
    PostVersion,
    new_id,
)
from packages.contracts import GeneratedPost, SourceReference
from services.api import campaign_workflows
from services.api import job_service
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
        "pillars": ["product"],
        "channels": ["facebook_page"],
    })
    assert created.status_code == 201, created.text
    campaign = created.json()
    assert campaign["post_count"] == 0

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
    body = {"campaign_id": campaign_id, "count": 1}
    accepted = client.post(f"/api/v1/workspaces/{workspace_id}/posts/generate", headers=request_headers, json=body)
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    duplicate = client.post(f"/api/v1/workspaces/{workspace_id}/posts/generate", headers=request_headers, json=body)
    assert duplicate.status_code == 202
    assert duplicate.json()["job_id"] == job_id

    class FixedModel:
        def generate(self, *, system_prompt, input_payload, response_model):
            source = input_payload["sources"][0]
            return GeneratedPost(
                base_version="ignored", version=1, channel="ignored", caption="Cơm gà Bếp Mộc cho bữa cơm gia đình.",
                citations=[SourceReference(
                    source_id=source["source_id"], document_id=source["document_id"],
                    source_version=source["source_version"], locator=source["locator"],
                    excerpt="Bếp Mộc phục vụ cơm gà",
                )],
            ), None

    monkeypatch.setattr(content_tasks, "SessionLocal", session_factory)
    asyncio.run(content_tasks.content_generation_task_async(job_id, agent=ContentAgent(FixedModel())))

    async def check_saved_draft():
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            posts = (await db.scalars(select(CampaignPost).where(CampaignPost.campaign_id == campaign_id))).all()
            versions = (await db.scalars(select(PostVersion).where(PostVersion.campaign_id == campaign_id))).all()
            return job, posts, versions

    job, posts, versions = asyncio.run(check_saved_draft())
    assert job.status == "succeeded"
    assert len(posts) == len(versions) == 1
    assert posts[0].status == "draft"
    assert versions[0].source == "ai_generated"
    assert versions[0].generation_job_id == job_id
    assert posts[0].current_json["citations"][0]["document_id"] == document_id
    assert job.result["estimated_cost_available"] is False


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
