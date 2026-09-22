"""FastAPI/ingestion smoke tests for the M2 foundation slice."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import Base
from services.api.db import get_db
from services.api.main import app
from services.ingestion.parsers import parse_document


@pytest.fixture
def api_client():
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
            yield client
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_auth_and_tenant_isolation(api_client: TestClient) -> None:
    first = api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "first@example.com",
            "password": "secret123",
            "full_name": "First Owner",
            "company_name": "First Co",
        },
    )
    assert first.status_code == 201
    workspace_id = first.json()["active_workspace_id"]

    second = TestClient(app)
    with second:
        second_response = second.post(
            "/api/v1/auth/register",
            json={
                "email": "second@example.com",
                "password": "secret123",
                "full_name": "Second Owner",
                "company_name": "Second Co",
            },
        )
        assert second_response.status_code == 201
        response = second.get(f"/api/v1/workspaces/{workspace_id}/documents")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.headers["x-request-id"].startswith("req_")


def test_parser_returns_locators_and_rejects_scan_pdf(tmp_path) -> None:
    text_path = tmp_path / "brand.txt"
    text_path.write_text("Bếp Mộc phục vụ món Việt.", encoding="utf-8")
    parsed = parse_document(text_path, kind="txt", mime_type="text/plain", filename=text_path.name)
    assert parsed.text_blocks[0].locator == "text:1"
    assert parsed.text_blocks[0].text.startswith("Bếp Mộc")

    from services.ingestion.parsers import ParseError

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 not a readable text layer")
    with pytest.raises(ParseError) as error:
        parse_document(pdf_path, kind="pdf", mime_type="application/pdf", filename=pdf_path.name)
    assert error.value.code in {"corrupted", "pdf_no_text_layer"}

