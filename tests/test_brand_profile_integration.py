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
from tests.helpers.page_workspace import activate_test_page
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
    workspace = activate_test_page(client)
    return workspace["id"], {"X-CSRF-Token": client.cookies["agentic_csrf"]}


def _upload(client: TestClient, workspace_id: str, csrf: dict[str, str], files):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={**csrf, "Idempotency-Key": f"upload-{workspace_id}-{len(files)}"},
        files=[("files", (name, content, "text/plain")) for name, content in files],
    )


def _install_fixture_text_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ingestion workflow tests independent of the optional Docling runtime."""
    from services.ingestion.parsers import ParsedDocument, ParsedTextBlock

    def parse_fixture(path: Path, *, kind: str, mime_type: str, filename: str) -> ParsedDocument:
        text = path.read_text(encoding="utf-8")
        return ParsedDocument(
            text_blocks=[ParsedTextBlock(text=text, locator="fixture:line=1")] if text else [],
            metadata={"fixture_parser": True, "kind": kind, "mime_type": mime_type, "filename": filename},
        )

    monkeypatch.setattr(tasks, "parse_document", parse_fixture)


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
@pytest.mark.parametrize(
    ("invalid_name", "invalid_body", "max_upload_bytes", "expected_status"),
    [
        ("unsupported.bin", b"unsupported", None, 415),
        ("too-large.txt", b"123456789", 8, 413),
    ],
)
def test_upload_preflights_entire_batch_before_writing_objects(
    api_env, tmp_path, monkeypatch, invalid_name, invalid_body, max_upload_bytes, expected_status
):
    from dataclasses import replace

    from database.models import Document
    from services.api import documents
    from sqlalchemy import select

    client, sessions = api_env
    workspace_id, csrf = _register(client, f"preflight-{expected_status}@example.com", "Preflight Co")
    if max_upload_bytes is not None:
        monkeypatch.setattr(
            documents, "settings", replace(documents.settings, max_upload_bytes=max_upload_bytes)
        )
    invalid_mime = "application/octet-stream" if invalid_name.endswith(".bin") else "text/plain"
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={**csrf, "Idempotency-Key": f"preflight-{expected_status}"},
        files=[
            ("files", ("good.txt", b"Good.", "text/plain")),
            ("files", (invalid_name, invalid_body, invalid_mime)),
        ],
    )

    assert uploaded.status_code == expected_status, uploaded.text
    object_root = tmp_path / "objects"
    assert not object_root.exists() or list(object_root.rglob("*")) == []

    async def document_count():
        async with sessions() as db:
            return len((await db.scalars(select(Document))).all())

    assert asyncio.run(document_count()) == 0


@pytest.mark.fixture_integration
def test_reprocess_updates_document_parser_version(api_env, monkeypatch):
    from dataclasses import replace

    from database.models import Document, Job
    from services.api import documents

    client, sessions = api_env
    workspace_id, csrf = _register(client, "parser-version@example.com", "Parser Version Co")
    uploaded = _upload(client, workspace_id, csrf, [("brand.txt", b"Parser version test content.")])
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]

    async def finish_initial_job():
        async with sessions() as db:
            document = await db.get(Document, document_id)
            document.job_id = None
            job = await db.get(Job, uploaded.json()["job_id"])
            job.status = "failed"
            await db.commit()

    asyncio.run(finish_initial_job())

    monkeypatch.setattr(
        documents, "settings", replace(documents.settings, parser_version="m2-parser-v2")
    )
    reprocessed = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/reprocess",
        headers=csrf,
    )
    assert reprocessed.status_code == 202, reprocessed.text

    async def parser_version():
        async with sessions() as db:
            return (await db.get(Document, document_id)).parser_version

    assert asyncio.run(parser_version()) == "m2-parser-v2"


@pytest.mark.fixture_integration
def test_document_limits_images_and_extracted_content_cursor(api_env):
    from database.models import Document

    client, sessions = api_env
    workspace_id, csrf = _register(client, "document-preview@example.com", "Document Preview Co")

    limits = client.get(f"/api/v1/workspaces/{workspace_id}/documents/limits")
    assert limits.status_code == 200
    assert limits.json()["accepted_kinds"] == ["pdf", "docx", "xlsx", "csv", "txt"]
    assert limits.json()["max_text_characters"] == 20_000_000
    assert limits.json()["max_table_rows"] == 100_000
    assert limits.json()["max_table_columns"] == 256
    assert limits.json()["max_table_cells"] == 1_000_000
    assert limits.json()["max_pdf_pages"] == 200
    assert limits.json()["max_processing_seconds"] == 600
    assert limits.json()["ocr_enabled"] is False

    image = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={**csrf, "Idempotency-Key": "image-must-be-rejected"},
        files=[("files", ("not-a-document.png", b"\x89PNG\r\n\x1a\n", "image/png"))],
    )
    assert image.status_code == 415
    assert image.json()["error"]["code"] == "unsupported_type"

    disguised_image = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={**csrf, "Idempotency-Key": "disguised-image-must-be-rejected"},
        files=[("files", ("photo.txt", b"\x89PNG\r\n\x1a\nfixture", "text/plain"))],
    )
    assert disguised_image.status_code == 415
    assert disguised_image.json()["error"]["code"] == "unsupported_type"

    uploaded = _upload(client, workspace_id, csrf, [("preview.txt", b"preview source")])
    assert uploaded.status_code == 202, uploaded.text
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]

    async def seed_extracted_content():
        async with sessions() as db:
            document = await db.get(Document, document_id)
            document.normalized_json = {
                "text_blocks": [{"text": "A long source passage.", "locator": "page=1"}],
                "table_blocks": [{
                    "headers": ["name", "value"],
                    "rows": [[f"row-{index}", str(index)] for index in range(5)],
                    "locator": "sheet=Data;row=1",
                }],
            }
            document.knowledge_status = "ready"
            await db.commit()

    asyncio.run(seed_extracted_content())

    first = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/extracted-content",
        params={"limit": 2},
    )
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 2
    assert first.json()["items"][0]["kind"] == "text"
    assert first.json()["total_rows"] == 5
    assert first.json()["has_more"] is True

    second = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/extracted-content",
        params={"limit": 2, "cursor": first.json()["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    assert [item["cells"][0] for item in second.json()["items"]] == ["row-1", "row-2"]

    async def change_parser_version():
        async with sessions() as db:
            document = await db.get(Document, document_id)
            document.parser_version = "new-parser-version"
            await db.commit()

    asyncio.run(change_parser_version())
    stale = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/extracted-content",
        params={"limit": 2, "cursor": second.json()["next_cursor"]},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "extracted_content_changed"


@pytest.mark.fixture_integration
def test_upload_worker_profile_revision_confirm_and_tenant_isolation(api_env):
    pytest.skip("Legacy test asserts AI-generated Brand Profile during ingestion; covered by manual-profile ingestion tests below.")
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
    assert job.json()["result"]["profile_run"]["minimum_semantic_score"] == 0.82
    assert job.json()["result"]["profile_run"]["minimum_semantic_margin"] == 0.04
    assert job.json()["result"]["profile_run"]["minimum_hybrid_lexical_score"] == 0.45

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


@pytest.mark.fixture_integration
def test_manual_profile_is_unchanged_by_document_ingestion(api_env, monkeypatch):
    client, sessions = api_env
    _install_fixture_text_parser(monkeypatch)
    workspace_id, csrf = _register(client, "manual-profile-owner@example.com", "Bếp Mộc")
    monkeypatch.setattr(
        "services.worker.model_provider.configured_structured_model",
        lambda: pytest.fail("manual profile save and document ingestion must not call the LLM"),
    )
    profile_url = f"/api/v1/workspaces/{workspace_id}/brand-profile"
    initial = client.get(profile_url).json()
    owner_text = "Bên mình bán cơm gà cho gia đình.\nViết gần gũi và rõ ràng."
    applied = client.patch(profile_url, headers=csrf, json={"version": initial["version"], "profile_text": owner_text})
    assert applied.status_code == 200, applied.text
    assert applied.json()["profile_text"] == owner_text
    assert applied.json()["profile_mode"] == "manual_text_v1"
    applied_version = applied.json()["version"]
    revisions = client.get(f"{profile_url}/revisions")
    assert revisions.status_code == 200, revisions.text
    assert revisions.json()[0]["profile"]["profile_text"] == owner_text
    assert revisions.json()[0]["profile"]["applied_by"] == applied.json()["applied_by"]

    with TestClient(app) as registration_client:
        editor_workspace, _editor_csrf = _register(registration_client, "manual-profile-editor@example.com", "Editor Home")

    async def grant_editor_membership():
        from database.models import Membership, User
        async with sessions() as db:
            editor = await db.scalar(select(User).where(User.email == "manual-profile-editor@example.com"))
            db.add(Membership(company_id=workspace_id, user_id=editor.id, role="editor", is_active=True))
            await db.commit()

    asyncio.run(grant_editor_membership())
    with TestClient(app) as editor_client:
        login = editor_client.post("/api/v1/auth/login", json={"email": "manual-profile-editor@example.com", "password": "secret123"})
        assert login.status_code == 200, login.text
        denied = editor_client.patch(profile_url, headers={"X-CSRF-Token": editor_client.cookies["agentic_csrf"]}, json={"version": applied_version, "profile_text": "Editor replacement"})
        assert denied.status_code == 403

    assert editor_workspace != workspace_id

    uploaded = _upload(client, workspace_id, csrf, [("brand.txt", b"A price list and product facts for retrieval.")])
    assert uploaded.status_code == 202, uploaded.text
    job_id = uploaded.json()["job_id"]
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]
    profile_only = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/reprocess",
        headers=csrf,
        json={"mode": "profile_only"},
    )
    assert profile_only.status_code == 410
    assert profile_only.json()["error"]["code"] == "brand_profile_generation_removed"
    asyncio.run(tasks.ingest_document_task_batch_async(job_id, [document_id]))
    asyncio.run(tasks.ingest_document_task_batch_async(job_id, [document_id]))

    job = client.get(f"/api/v1/jobs/{job_id}").json()
    document = client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}").json()
    current_profile = client.get(profile_url).json()
    assert job["status"] == "succeeded", job
    assert job["result"]["knowledge_status"] == "ready"
    assert job["result"]["profile_status"] == "not_applicable"
    assert "profile_run" not in job["result"]
    assert document["extraction_status"] == "extracted"
    assert document["knowledge_status"] == "ready"
    assert document["profile_status"] == "not_applicable"
    assert document["selectable_for_content"] is True
    assert current_profile["profile_text"] == owner_text
    assert current_profile["version"] == applied_version

    async def revision_and_chunks():
        from database.models import Brand, BrandProfileRevision, KnowledgeChunk
        async with sessions() as db:
            brand = await db.scalar(select(Brand).where(Brand.company_id == workspace_id))
            revisions = (await db.scalars(select(BrandProfileRevision).where(BrandProfileRevision.company_id == workspace_id))).all()
            chunks = (await db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.company_id == workspace_id))).all()
            return brand, revisions, chunks

    brand, revisions, chunks = asyncio.run(revision_and_chunks())
    assert brand.version == applied_version
    assert len(revisions) == 1 and revisions[0].profile_json["profile_text"] == owner_text
    assert chunks and all(chunk.document_id == document_id for chunk in chunks)

    same_text = client.patch(profile_url, headers=csrf, json={"version": applied_version, "profile_text": owner_text})
    assert same_text.status_code == 200 and same_text.json()["version"] == applied_version
    stale = client.patch(profile_url, headers=csrf, json={"version": 1, "profile_text": "stale text"})
    assert stale.status_code == 409
    legacy = client.patch(profile_url, headers=csrf, json={"version": applied_version, "fields": [{"key": "description", "value": "old format"}]})
    assert legacy.status_code == 410


@pytest.mark.fixture_integration
def test_missing_deepseek_configuration_keeps_ingestion_ready_and_skips_profile(api_env, monkeypatch):
    client, _sessions = api_env
    _install_fixture_text_parser(monkeypatch)
    workspace_id, csrf = _register(client, "missing-deepseek@example.com", "No LLM Co")
    uploaded = _upload(
        client,
        workspace_id,
        csrf,
        [("brand.txt", b"No LLM Co serves Vietnamese coffee to local office workers.")],
    )
    assert uploaded.status_code == 202, uploaded.text
    job_id = uploaded.json()["job_id"]
    document_id = uploaded.json()["job"]["result"]["document_ids"][0]

    monkeypatch.setattr(tasks, "configured_embedding_provider", lambda: None)
    asyncio.run(tasks.ingest_document_task_batch_async(job_id, [document_id]))

    job = client.get(f"/api/v1/jobs/{job_id}").json()
    document = client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}").json()

    assert job["status"] == "succeeded"
    assert job["error"] is None
    assert job["result"]["profile_status"] == "not_applicable"
    assert all(step["key"] != "create_brand_profile" for step in job["steps"])
    assert document["status"] == "ready"
    assert document["knowledge_status"] == "ready"
    assert document["profile_status"] == "not_applicable"
    assert document["extracted"]["knowledge_chunks"] > 0


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
            job.claim_token = "expired-claim"
            job.lease_until = utcnow() - timedelta(minutes=1)
            await db.commit()

    asyncio.run(set_stale_lease())
    dispatched: list[tuple[str, str, list[str]]] = []

    async def capture_dispatch(recovered_job_id, recovered_document_id, document_ids=None):
        dispatched.append((recovered_job_id, recovered_document_id, document_ids or []))
        return True

    monkeypatch.setattr("services.api.job_service.dispatch_document_job", capture_dispatch)
    from services.worker import scheduled_jobs

    monkeypatch.setattr(scheduled_jobs, "SessionLocal", sessions)
    assert scheduled_jobs.recover_due_jobs.run() == 1
    assert dispatched == [(job_id, document_id, [document_id])]

    async def recovered_state():
        from database.models import Job

        async with sessions() as db:
            job = await db.get(Job, job_id)
            return job.status, job.attempts, job.lease_until, job.claim_token

    status, attempts, lease_until, claim_token = asyncio.run(recovered_state())
    assert status == "queued"
    assert attempts == 1  # the next claim, not scheduler dispatch, consumes an attempt
    assert lease_until is not None
    assert claim_token is not None and claim_token != "expired-claim"


@pytest.mark.fixture_integration
def test_batch_with_one_bad_file_is_not_reported_as_success(api_env, monkeypatch):
    client, _sessions = api_env
    _install_fixture_text_parser(monkeypatch)
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

    asyncio.run(tasks.ingest_document_task_batch_async(job_id, document_ids))
    result = client.get(f"/api/v1/jobs/{job_id}").json()
    assert result["status"] == "failed"
    assert result["error"]["code"] == "partial_batch"
    assert result["result"]["partial"] is True
    assert len(result["result"]["normalized_document_ids"]) == 1
    assert len(result["result"]["failed_documents"]) == 1


@pytest.mark.skip(reason="Ingestion no longer retries or calls the Brand Profile model; document extraction and AI are separate workflows.")
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
    profile_step = next(step for step in result["steps"] if step["key"] == "create_brand_profile")
    assert profile_step["status"] == ("pending" if expected_status == "queued" else "failed")
    document = client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}").json()
    assert document["profile_status"] == ("pending" if expected_status == "queued" else "failed")
