"""API integration checks for Page token handling and manual market evidence."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import Base, MarketEvidence, MarketObservation, MetaPageConnection
from services.api import market_research as market_research_routes
from services.api import meta_tokens
from services.api.db import get_db
from services.api.main import app
from services.api.meta_client import MetaPage


@pytest.fixture
def market_api(monkeypatch):
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
    monkeypatch.setattr(market_research_routes, "settings", SimpleNamespace(meta_graph_version="v26.0"))
    encryption_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(meta_tokens, "settings", SimpleNamespace(
        meta_token_encryption_key=encryption_key,
        meta_token_encryption_key_previous="",
    ))
    try:
        with TestClient(app) as client:
            yield client, session_factory, encryption_key
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


class FakeMetaGraphClient:
    def __init__(self, page_id: str, token: str, graph_version: str):
        self.page_id = page_id
        self.token = token
        self.graph_version = graph_version

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def verify_page(self) -> MetaPage:
        return MetaPage(id=self.page_id, name=f"Page {self.page_id}")

    async def list_page_posts(self, limit: int = 1):
        return SimpleNamespace(posts=[], next_cursor=None)


def _owner(client: TestClient, email: str) -> tuple[str, dict[str, str]]:
    response = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "safe-test-password",
        "full_name": "Page Owner",
        "company_name": "Market workspace",
    })
    assert response.status_code == 201, response.text
    return response.json()["active_workspace_id"], {
        "X-CSRF-Token": client.cookies["agentic_csrf"],
    }


def _create_group(client: TestClient, workspace_id: str, headers: dict[str, str]) -> str:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/groups",
        headers=headers,
        json={
            "name": "Mỹ phẩm miền Nam",
            "industry": "Mỹ phẩm",
            "region": "TP. Hồ Chí Minh",
            "locale": "vi-VN",
            "keywords": ["chăm sóc da"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_page_token_is_encrypted_and_same_page_can_reconnect(market_api, monkeypatch) -> None:
    client, session_factory, encryption_key = market_api
    monkeypatch.setattr(market_research_routes, "MetaGraphClient", FakeMetaGraphClient)
    workspace_id, headers = _owner(client, "page-owner@example.com")
    group_id = _create_group(client, workspace_id, headers)
    token = "opaque-page-token-with-entropy-12345"
    url = f"/api/v1/workspaces/{workspace_id}/market-research/groups/{group_id}/pages"
    body = {"page_id": "123456789", "page_access_token": token}

    connected = client.post(url, headers=headers, json=body)
    assert connected.status_code == 201, connected.text
    connection_id = connected.json()["id"]
    assert "page_access_token" not in connected.json()
    assert "encrypted_token" not in connected.json()

    pages = client.get(url)
    assert pages.status_code == 200
    assert pages.json()[0]["status"] == "verified"
    assert "encrypted_token" not in pages.json()[0]

    async def read_connection():
        async with session_factory() as db:
            return await db.scalar(select(MetaPageConnection).where(MetaPageConnection.id == connection_id))

    stored = asyncio.run(read_connection())
    assert stored.encrypted_token != token
    assert meta_tokens.decrypt_page_token(stored.encrypted_token) == token

    disconnected = client.delete(
        f"/api/v1/workspaces/{workspace_id}/market-research/pages/{connection_id}",
        headers=headers,
    )
    assert disconnected.status_code == 204
    reconnected = client.post(url, headers=headers, json={**body, "page_access_token": token + "-rotated"})
    assert reconnected.status_code == 201, reconnected.text
    assert reconnected.json()["id"] == connection_id

    async def read_reconnected():
        async with session_factory() as db:
            return await db.scalar(select(MetaPageConnection).where(MetaPageConnection.id == connection_id))

    stored_again = asyncio.run(read_reconnected())
    assert stored_again.active is True
    assert stored_again.status == "verified"
    assert meta_tokens.decrypt_page_token(stored_again.encrypted_token) == token + "-rotated"


def test_manual_competitor_import_masks_private_contact_data(market_api) -> None:
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "market-owner@example.com")
    group_id = _create_group(client, workspace_id, headers)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "competitor_facebook_page",
            "name": "Đối thủ A",
            "url": "https://www.facebook.com/rival",
            "competitor_name": "Đối thủ A",
        },
    )
    assert created.status_code == 201, created.text
    source = created.json()
    assert source["status"] == "manual_import_only"

    imported = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}/import",
        headers=headers,
        json={"rows": [{
            "url": "https://www.facebook.com/rival/posts/42",
            "title": "Bài đối thủ",
            "text": "Liên hệ 0901234567 hoặc trend@example.com",
            "metrics": {"reactions": 45, "comments": 7, "shares": 3, "views": 1000},
            "comments": ["Nhắn tôi tại contact@example.com", "SĐT 0912345678"],
        }]},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["imported"] == 1

    async def read_evidence():
        async with session_factory() as db:
            evidence = await db.scalar(select(MarketEvidence).where(MarketEvidence.source_id == source["id"]))
            observation = await db.scalar(select(MarketObservation).where(MarketObservation.evidence_id == evidence.id))
            return evidence, observation

    evidence, observation = asyncio.run(read_evidence())
    assert "trend@example.com" not in evidence.text
    assert "0901234567" not in evidence.text
    assert "[đã ẩn email]" in evidence.text
    assert "[đã ẩn số điện thoại]" in evidence.text
    assert all("contact@example.com" not in item and "0912345678" not in item for item in observation.comments_json)
    assert observation.metrics_json == {"reactions": 45, "comments": 7, "shares": 3, "views": 1000}
