"""Real API/worker integration using a deterministic M3 handler fixture."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import Base
from packages.contracts import BrandFact, BrandProfile, SourceReference
from services.agents.brand_agent import BrandAgent
from services.api.db import get_db
from services.api.main import app
from services.worker import tasks


class TempStorage:
    def __init__(self, root: Path):
        self.root = root

    async def put(self, key: str, content: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    async def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def path(self, key: str) -> Path:
        return self.root / key


class FixtureStructuredModel:
    def generate(self, *, system_prompt, input_payload, response_model):
        source = input_payload["sources"][0]
        profile = BrandProfile(
            brand_id=input_payload["brand_id"],
            business="Quán Bếp Mộc phục vụ món Việt gia đình.",
            products=["Cơm gà"],
            audience=["Gia đình địa phương"],
            voice=["Thân thiện", "Rõ ràng"],
            facts=[
                BrandFact(
                    key="business",
                    value="Quán Bếp Mộc phục vụ món Việt gia đình.",
                    evidence=[
                        SourceReference(
                            source_id=source["source_id"],
                            document_id="fixture-document",
                            source_version="fixture-version",
                            locator=source["locator"],
                        )
                    ],
                )
            ],
        )
        return profile, None


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_db():
        async with sessions() as session:
            yield session

    asyncio.run(setup())
    app.dependency_overrides[get_db] = override_db
    storage = TempStorage(tmp_path / "objects")
    monkeypatch.setattr("services.api.documents.storage", storage)
    monkeypatch.setattr(tasks, "storage", storage)

    async def no_dispatch(*args, **kwargs):
        return None

    monkeypatch.setattr("services.api.documents.dispatch_document_job", no_dispatch)
    monkeypatch.setattr(tasks, "SessionLocal", sessions)
    try:
        with TestClient(app) as client:
            yield client, sessions
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _register(client: TestClient, email: str, company_name: str) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secret123",
            "full_name": "Test Owner",
            "company_name": company_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["active_workspace_id"], {"X-CSRF-Token": client.cookies["agentic_csrf"]}


def _upload(client: TestClient, workspace_id: str, csrf: dict[str, str], files):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={**csrf, "Idempotency-Key": f"upload-{workspace_id}-{len(files)}"},
        files=[("files", (name, content, "text/plain")) for name, content in files],
    )


def test_upload_worker_profile_revision_confirm_and_tenant_isolation(api_env):
    client, sessions = api_env
    workspace_id, csrf = _register(client, "owner-one@example.com", "Bếp Mộc")
    uploaded = _upload(client, workspace_id, csrf, [("brand.txt", b"Bep Moc phuc vu com ga cho gia dinh.")])
    assert uploaded.status_code == 202, uploaded.text
    job_id = uploaded.json()["job_id"]
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]

    agent = BrandAgent(FixtureStructuredModel())
    asyncio.run(tasks.ingest_document_task_batch_async(job_id, [document_id], agent=agent))
    # A duplicate Celery delivery cannot produce another revision.
    asyncio.run(tasks.ingest_document_task_batch_async(job_id, [document_id], agent=agent))

    job = client.get(f"/api/v1/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "succeeded"
    assert job.json()["result"]["profile_version"] == 2
    document = client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}")
    assert document.json()["extraction_status"] == "extracted"
    assert document.json()["knowledge_status"] == "ready"
    assert document.json()["profile_status"] == "ready"

    profile_response = client.get(f"/api/v1/workspaces/{workspace_id}/brand-profile")
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()
    assert profile["version"] == 2
    assert profile["description"]["state"] == "suggested"
    assert profile["description"]["provenance"][0]["document_id"] == document_id
    assert profile["description"]["provenance"][0]["quote"]
    revisions = client.get(f"/api/v1/workspaces/{workspace_id}/brand-profile/revisions")
    assert [item["version"] for item in revisions.json()] == [2]

    conflict = client.patch(
        f"/api/v1/workspaces/{workspace_id}/brand-profile",
        headers=csrf,
        json={"version": 1, "fields": [{"key": "description", "value": "stale"}]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"] == {"current_version": 2, "your_version": 1}

    updated = client.patch(
        f"/api/v1/workspaces/{workspace_id}/brand-profile",
        headers=csrf,
        json={"version": 2, "fields": [{"key": "description", "value": "Đã được chủ workspace sửa"}], "confirm": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 3
    assert updated.json()["description"]["state"] == "confirmed"
    assert updated.json()["confirmed_by"]

    confirmed = client.post(
        f"/api/v1/workspaces/{workspace_id}/brand-profile/confirm",
        headers=csrf,
        json={"version": 3},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["version"] == 3  # confirmation is attached to revision 3
    assert len(client.get(f"/api/v1/workspaces/{workspace_id}/brand-profile/revisions").json()) == 2

    deleted = client.delete(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers=csrf,
    )
    assert deleted.status_code == 204

    async def retrieve_active_chunks():
        from database.models import Brand
        from services.ingestion.knowledge_store import PostgresKnowledgeIndex

        async with sessions() as db:
            brand = await db.scalar(select(Brand).where(Brand.company_id == workspace_id))
            return await PostgresKnowledgeIndex().retrieve(
                db,
                "Bep Moc",
                company_id=workspace_id,
                brand_id=brand.id,
            )

    assert asyncio.run(retrieve_active_chunks()) == []

    other_workspace, _other_csrf = _register(client, "owner-two@example.com", "Other Co")
    assert other_workspace != workspace_id
    # A distinct user cannot read the first tenant's profile.
    other_client = TestClient(app)
    with other_client:
        other_client.post(
            "/api/v1/auth/login",
            json={"email": "owner-two@example.com", "password": "secret123"},
        )
        assert other_client.get(f"/api/v1/workspaces/{workspace_id}/brand-profile").status_code == 404
        assert other_client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}").status_code == 404
        assert other_client.get(f"/api/v1/jobs/{job_id}").status_code == 404

    async def count_rows():
        async with sessions() as db:
            from database.models import BrandProfileRevision, KnowledgeChunk

            revisions_count = await db.scalar(
                select(BrandProfileRevision).where(BrandProfileRevision.job_id == job_id)
            )
            chunks_count = len((await db.scalars(select(KnowledgeChunk))).all())
            return revisions_count, chunks_count

    revision_for_job, knowledge_chunks = asyncio.run(count_rows())
    assert revision_for_job is not None
    assert knowledge_chunks > 0


def test_expired_worker_lease_is_requeued(api_env, monkeypatch):
    client, sessions = api_env
    workspace_id, _csrf = _register(client, "lease-owner@example.com", "Lease Co")
    uploaded = _upload(client, workspace_id, _csrf, [("lease.txt", b"Durable retry test content.")])
    assert uploaded.status_code == 202, uploaded.text
    job_id = uploaded.json()["job_id"]
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]

    async def set_stale_lease():
        from datetime import timedelta

        from database.models import Job, utcnow

        async with sessions() as db:
            job = await db.get(Job, job_id)
            job.status = "running"
            job.attempts = 1
            job.lease_until = utcnow() - timedelta(minutes=1)
            await db.commit()

    asyncio.run(set_stale_lease())
    dispatched: list[tuple[str, str, list[str]]] = []

    async def capture_dispatch(recovered_job_id, recovered_document_id, document_ids=None):
        dispatched.append((recovered_job_id, recovered_document_id, document_ids or []))

    monkeypatch.setattr("services.api.job_service.dispatch_document_job", capture_dispatch)
    from services.worker import scheduled_jobs

    monkeypatch.setattr(scheduled_jobs, "SessionLocal", sessions)
    assert scheduled_jobs.recover_due_jobs.run() == 1
    assert dispatched == [(job_id, document_id, [document_id])]

    async def recovered_state():
        from database.models import Job

        async with sessions() as db:
            job = await db.get(Job, job_id)
            return job.status, job.attempts, job.lease_until

    status, attempts, lease_until = asyncio.run(recovered_state())
    assert status == "queued"
    assert attempts == 1  # the next claim, not scheduler dispatch, consumes an attempt
    assert lease_until is not None


def test_batch_with_one_bad_file_is_not_reported_as_success(api_env):
    client, _sessions = api_env
    workspace_id, csrf = _register(client, "batch-owner@example.com", "Batch Co")
    uploaded = _upload(
        client,
        workspace_id,
        csrf,
        [("good.txt", b"Brand voice is clear and friendly."), ("empty.txt", b"")],
    )
    assert uploaded.status_code == 202, uploaded.text
    job_id = uploaded.json()["job_id"]
    document_ids = uploaded.json()["job"]["result"]["document_ids"]

    asyncio.run(tasks.ingest_document_task_batch_async(job_id, document_ids, agent=BrandAgent(FixtureStructuredModel())))
    result = client.get(f"/api/v1/jobs/{job_id}").json()
    assert result["status"] == "failed"
    assert result["error"]["code"] == "partial_batch"
    assert result["result"]["partial"] is True
    assert len(result["result"]["normalized_document_ids"]) == 1
    assert len(result["result"]["failed_document_ids"]) == 1
