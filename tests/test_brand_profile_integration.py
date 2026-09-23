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
                            document_id=source["document_id"],
                            source_version=source["source_version"],
                            locator=source["locator"],
                        )
                    ],
                )
            ],
        )
        return profile, None


class FakeEmbeddingProvider:
    provider_name = "test"
    model_name = "test-embed-v2"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[1.0] + [0.0] * 1535 for _ in texts]


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


@pytest.mark.fixture_integration
def test_upload_filename_is_not_used_as_storage_path(api_env, tmp_path):
    client, sessions = api_env
    workspace_id, csrf = _register(client, "filename-owner@example.com", "Filename Co")
    body = b"Brand facts stored under a server-generated object key."
    uploaded = _upload(
        client,
        workspace_id,
        csrf,
        [("../../outside.txt", body)],
    )
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]

    async def stored_document():
        from database.models import Document

        async with sessions() as db:
            document = await db.get(Document, document_id)
            return document.filename, document.storage_key

    filename, storage_key = asyncio.run(stored_document())
    storage_root = (tmp_path / "objects").resolve()
    stored_path = (storage_root / storage_key).resolve()
    assert filename == "outside.txt"
    assert filename not in storage_key
    assert len(storage_key.split("/")) == 3
    assert storage_root in stored_path.parents
    assert stored_path.read_bytes() == body


@pytest.mark.fixture_integration
def test_upload_worker_profile_revision_confirm_and_tenant_isolation(api_env):
    client, sessions = api_env
    workspace_id, csrf = _register(client, "owner-one@example.com", "Bếp Mộc")
    uploaded = _upload(client, workspace_id, csrf, [("brand.txt", "Bếp Mộc phục vụ cơm gà cho gia đình.".encode())])
    assert uploaded.status_code == 202, uploaded.text
    job_id = uploaded.json()["job_id"]
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]

    agent = BrandAgent(FixtureStructuredModel())
    asyncio.run(tasks.ingest_document_task_batch_async(job_id, [document_id], agent=agent))
    # A duplicate Celery delivery cannot produce another revision.
    asyncio.run(tasks.ingest_document_task_batch_async(job_id, [document_id], agent=agent))

    job = client.get(f"/api/v1/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "succeeded", job.json()
    assert job.json()["result"]["profile_version"] == 2
    assert job.json()["result"]["profile_run"]["task_name"] == "run_brand_profile_handler"
    assert job.json()["result"]["profile_run"]["semantic_vector_rag_accepted"] is False
    assert "not been accepted or verified" in job.json()["result"]["profile_run"]["lexical_mode_notice"]
    assert job.json()["result"]["profile_run"]["minimum_relevance_score"] == 0.12
    assert job.json()["result"]["profile_run"]["minimum_semantic_score"] == 0.72

    async def check_handler_context():
        from database.models import BrandProfileRevision

        async with sessions() as db:
            revision = await db.scalar(
                select(BrandProfileRevision).where(BrandProfileRevision.job_id == job_id)
            )
            source = revision.input_snapshot_json["context"][0]
            assert source["company_id"] == workspace_id
            assert source["brand_id"]
            assert source["document_id"] == document_id
            assert source["source_id"]
            assert source["source_version"] == "1"
            assert source["source_hash"]
            assert source["locator"]

    asyncio.run(check_handler_context())
    document = client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}")
    assert document.json()["extraction_status"] == "extracted"
    assert document.json()["knowledge_status"] == "ready"
    assert document.json()["retrieval_mode"] == "lexical"
    assert document.json()["profile_status"] == "ready"

    async def reindex_version_change():
        from database.models import Document, KnowledgeChunk
        from packages.contracts import NormalizedDocument
        from services.ingestion.knowledge_store import PostgresKnowledgeIndex

        async with sessions() as db:
            source = await db.get(Document, document_id)
            index = PostgresKnowledgeIndex()
            old_rows = list((await db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source.source_id))).all())
            assert old_rows and all(row.embedding is None for row in old_rows)
            assert {row.embedding_model_version for row in old_rows} == {"lexical-v1"}

            embedder = FakeEmbeddingProvider()
            inserted = await index.upsert(
                db,
                NormalizedDocument.model_validate(source.normalized_json),
                embedder=embedder,
                parser_version=source.parser_version,
                chunker_version="integration-chunker-v2",
                embedding_model_version=embedder.model_name,
            )
            await db.flush()
            assert inserted > 0
            assert embedder.calls > 0
            new_rows = list((await db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source.source_id))).all())
            active = [row for row in new_rows if row.is_active]
            assert active and all(row.chunker_version == "integration-chunker-v2" for row in active)
            assert all(row.embedding_model_version == "test-embed-v2" for row in active)
            assert all(row.embedding is not None for row in active)
            assert all(not row.is_active for row in old_rows)

            repeated = await index.upsert(
                db,
                NormalizedDocument.model_validate(source.normalized_json),
                embedder=embedder,
                parser_version=source.parser_version,
                chunker_version="integration-chunker-v2",
                embedding_model_version=embedder.model_name,
            )
            assert repeated == 0
            assert embedder.calls == 1
            await db.commit()

    asyncio.run(reindex_version_change())

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


@pytest.mark.fixture_integration
def test_batch_with_one_bad_file_is_not_reported_as_success(api_env):
    client, _sessions = api_env
    workspace_id, csrf = _register(client, "batch-owner@example.com", "Batch Co")
    uploaded = _upload(
        client,
        workspace_id,
        csrf,
        [("good.txt", b"Batch Co brand voice is clear and friendly."), ("empty.txt", b"")],
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


@pytest.mark.fixture_integration
@pytest.mark.parametrize(
    ("failure_code", "retryable", "expected_status"),
    [
        ("provider_authentication_failed", False, "failed"),
        ("provider_model_not_found", False, "failed"),
        ("provider_rate_limited", True, "queued"),
        ("provider_timeout", True, "queued"),
    ],
)
def test_worker_honors_m3_provider_retry_policy(
    api_env, monkeypatch, failure_code, retryable, expected_status
):
    from services.agents.brand_agent.result import BrandProfileFailure, BrandProfileHandlerResult

    client, _sessions = api_env
    workspace_id, csrf = _register(
        client,
        f"{failure_code}@example.com",
        "Retry Co",
    )
    uploaded = _upload(
        client,
        workspace_id,
        csrf,
        [("brand.txt", b"Retry Co brand identity and customer service.")],
    )
    assert uploaded.status_code == 202, uploaded.text
    job_id = uploaded.json()["job_id"]
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]

    def fail_from_m3(**kwargs):
        return BrandProfileHandlerResult(
            status="failed",
            company_id=kwargs["company_id"],
            brand_id=kwargs["brand_id"],
            document_ids=tuple(kwargs["document_ids"]),
            job_id=kwargs["job_id"],
            run_id=kwargs["run_id"],
            input_snapshot_id=kwargs["input_snapshot_id"],
            profile=None,
            source_references=(),
            missing_information=(),
            contradictions=(),
            generation=None,
            repair_attempts=0,
            estimated_cost_available=False,
            error=BrandProfileFailure(
                failure_code,
                "Safe provider test failure.",
                retryable,
            ),
        )

    monkeypatch.setattr(tasks, "run_brand_profile_handler", fail_from_m3)
    asyncio.run(
        tasks.ingest_document_task_batch_async(
            job_id,
            [document_id],
            agent=BrandAgent(FixtureStructuredModel()),
        )
    )
    result = client.get(f"/api/v1/jobs/{job_id}").json()

    assert result["status"] == expected_status
    assert result["error"]["code"] == failure_code
    assert result["error"]["retryable"] is retryable
