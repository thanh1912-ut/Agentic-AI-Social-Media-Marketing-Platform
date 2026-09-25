"""API integration checks for Page token handling and manual market evidence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import (
    Base, MarketEvidence, MarketEvidenceVersion, MarketObservation, MetaPageConnection,
    MarketReport, MarketReportEvidence, MetaPageGroup, ResearchCycle, ResearchSource, new_id,
)
from services.api import market_research as market_research_routes
from services.api import meta_tokens
from services.api.db import get_db
from services.api.meta_client import MetaPagePost, MetaPagePostsPage, MetaPublicPage
from services.api.main import app
from services.api.meta_client import MetaPage
from services.worker import research_tasks, scheduled_jobs


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
            "observed_at": "2026-09-25T12:00:00Z",
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
            version = await db.get(MarketEvidenceVersion, observation.evidence_version_id)
            return evidence, observation, version

    evidence, observation, version = asyncio.run(read_evidence())
    assert "trend@example.com" not in evidence.text
    assert "0901234567" not in evidence.text
    assert "[đã ẩn email]" in evidence.text
    assert "[đã ẩn số điện thoại]" in evidence.text
    assert all("contact@example.com" not in item and "0912345678" not in item for item in observation.comments_json)
    assert observation.metrics_json == {"reactions": 45, "comments": 7, "shares": 3, "views": 1000}
    assert version is not None
    assert version.text == evidence.text
    assert version.parser_version == "manual-import-v1"
    assert len(version.content_hash) == 64

    changed_snapshot = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}/import",
        headers=headers,
        json={"rows": [{
            "url": "https://www.facebook.com/rival/posts/42",
            "title": "Bài đã sửa",
            "text": "Nội dung thay đổi không thể thay thế bằng chứng cũ.",
            "observed_at": "2026-09-25T12:00:00Z",
            "metrics": {"reactions": 45, "comments": 7, "shares": 3, "views": 1000},
        }]},
    )
    assert changed_snapshot.status_code == 409
    assert changed_snapshot.json()["error"]["code"] == "observation_version_conflict"


def test_competitor_page_uses_approved_public_api_token_when_configured(market_api, monkeypatch) -> None:
    client, session_factory, _encryption_key = market_api
    monkeypatch.setattr(market_research_routes, "settings", SimpleNamespace(
        meta_graph_version="v26.0", meta_public_content_access_token="app-review-approved-token",
    ))
    monkeypatch.setattr(research_tasks, "settings", SimpleNamespace(
        meta_graph_version="v26.0", meta_public_content_access_token="app-review-approved-token",
    ))
    monkeypatch.setattr(research_tasks, "SessionLocal", session_factory)
    workspace_id, headers = _owner(client, "competitor-owner@example.com")
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
    source_id = created.json()["id"]
    assert created.json()["status"] == "active"

    class FakePublicGraphClient:
        def __init__(self, page_id: str, token: str, graph_version: str):
            assert token == "app-review-approved-token"
            assert graph_version == "v26.0"
            self.page_id = page_id

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def resolve_public_page(self, reference: str):
            assert self.page_id == "1"
            assert reference == "rival"
            return MetaPublicPage(id="987654", name="Đối thủ A", followers_count=2500)

        async def list_page_posts(self, limit: int = 100, after: str | None = None):
            assert self.page_id == "987654"
            assert limit == 100 and after is None
            return MetaPagePostsPage((MetaPagePost(
                external_post_id="987654_42", message="Ưu đãi mùa mới", created_time=None,
                permalink_url="https://www.facebook.com/rival/posts/42",
                reactions=17, comments=4, shares=2,
            ),), None)

        async def list_post_comments(self, external_post_id: str, limit: int = 50):
            assert external_post_id == "987654_42" and limit == 50
            return ("Liên hệ rival@example.com",)

    monkeypatch.setattr(research_tasks, "MetaGraphClient", FakePublicGraphClient)

    async def collect():
        async with session_factory() as db:
            from database.models import ResearchSource

            source = await db.get(ResearchSource, source_id)
            assert source is not None
        return await research_tasks._collect_competitor_page(
            workspace_id, group_id, source, datetime.now(timezone.utc),
        )

    saved, details = asyncio.run(collect())
    assert saved == 1
    assert details["metrics_available"] == ["reactions", "comments", "shares", "interactions"]
    assert details["metrics_unavailable"] == ["views"]

    async def read_observation():
        async with session_factory() as db:
            evidence = await db.scalar(select(MarketEvidence).where(MarketEvidence.source_id == source_id))
            observation = await db.scalar(select(MarketObservation).where(MarketObservation.evidence_id == evidence.id))
            return evidence, observation

    evidence, observation = asyncio.run(read_observation())
    assert evidence.text == "Ưu đãi mùa mới"
    assert observation.metrics_json == {
        "reactions": 17, "comments": 4, "shares": 2, "interactions": 23,
        "views": None,
    }
    assert observation.comments_json == ["Liên hệ [đã ẩn email]"]

    async def read_source_audience():
        from database.models import ResearchSourceMetricSnapshot

        async with session_factory() as db:
            return await db.scalar(select(ResearchSourceMetricSnapshot).where(
                ResearchSourceMetricSnapshot.source_id == source_id,
            ))

    audience = asyncio.run(read_source_audience())
    assert audience.followers == 2500
    assert audience.members is None


def test_owned_page_collection_saves_views_and_followers_when_meta_returns_them(market_api, monkeypatch) -> None:
    client, session_factory, _encryption_key = market_api
    monkeypatch.setattr(market_research_routes, "MetaGraphClient", FakeMetaGraphClient)
    monkeypatch.setattr(research_tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(research_tasks, "settings", SimpleNamespace(meta_graph_version="v26.0"))
    workspace_id, headers = _owner(client, "owned-page-owner@example.com")
    group_id = _create_group(client, workspace_id, headers)
    token = "opaque-owned-page-token-with-entropy-12345"
    connected = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/groups/{group_id}/pages",
        headers=headers,
        json={"page_id": "123456789", "page_access_token": token},
    )
    assert connected.status_code == 201, connected.text
    connection_id = connected.json()["id"]
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id, "source_type": "owned_facebook_page", "name": "Fanpage của tôi",
            "url": "https://www.facebook.com/123456789", "connection_id": connection_id,
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]

    class FakeOwnedGraphClient:
        def __init__(self, page_id: str, page_token: str, graph_version: str):
            assert page_id == "123456789"
            assert page_token == token
            assert graph_version == "v26.0"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def read_page_followers_count(self):
            return 5400

        async def list_page_posts(self, limit: int = 100, after: str | None = None):
            assert limit == 100 and after is None
            return MetaPagePostsPage((MetaPagePost(
                external_post_id="123456789_42", message="Bài viết mới", created_time=None,
                permalink_url="https://www.facebook.com/123456789/posts/42",
                reactions=22, comments=5, shares=3,
            ),), None)

        async def read_post_media_views(self, external_post_id: str):
            assert external_post_id == "123456789_42"
            return 7654

        async def list_post_comments(self, external_post_id: str, limit: int = 50):
            assert external_post_id == "123456789_42" and limit == 50
            return ("Bài này hữu ích",)

    monkeypatch.setattr(research_tasks, "MetaGraphClient", FakeOwnedGraphClient)

    observed_at = datetime.now(timezone.utc)

    async def collect():
        async with session_factory() as db:
            source = await db.get(ResearchSource, source_id)
            assert source is not None
        return await research_tasks._collect_page(workspace_id, group_id, source, observed_at)

    saved, details = asyncio.run(collect())
    assert saved == 1
    assert details["metrics_available"] == ["reactions", "comments", "shares", "interactions", "views"]
    assert details["metrics_unavailable"] == []

    async def read_observation():
        async with session_factory() as db:
            evidence = await db.scalar(select(MarketEvidence).where(MarketEvidence.source_id == source_id))
            return await db.scalar(select(MarketObservation).where(MarketObservation.evidence_id == evidence.id))

    observation = asyncio.run(read_observation())
    assert observation is not None
    assert observation.metrics_json == {
        "reactions": 22, "comments": 5, "shares": 3, "interactions": 30,
        "views": 7654,
    }
    assert observation.comments_json == ["Bài này hữu ích"]

    async def read_page_and_post_history():
        from database.models import MetaPageMetricSnapshot, MetaPagePost, MetaPostMetricSnapshot

        async with session_factory() as db:
            page_snapshot = await db.scalar(select(MetaPageMetricSnapshot).where(
                MetaPageMetricSnapshot.connection_id == connection_id,
            ))
            page_post = await db.scalar(select(MetaPagePost).where(
                MetaPagePost.company_id == workspace_id,
                MetaPagePost.external_post_id == "123456789_42",
            ))
            post_snapshot = await db.scalar(select(MetaPostMetricSnapshot).where(
                MetaPostMetricSnapshot.meta_page_post_id == page_post.id,
            ))
            return page_snapshot, page_post, post_snapshot

    page_snapshot, page_post, post_snapshot = asyncio.run(read_page_and_post_history())
    assert page_snapshot.followers == 5400
    assert post_snapshot.views == 7654
    assert post_snapshot.reactions == 22
    assert post_snapshot.missing_metrics_json == []

    page_history = client.get(
        f"/api/v1/workspaces/{workspace_id}/meta/pages/{connection_id}/metrics"
    )
    post_history = client.get(
        f"/api/v1/workspaces/{workspace_id}/meta/page-posts/{page_post.id}/metrics"
    )
    assert page_history.status_code == 200, page_history.text
    assert page_history.json()["snapshots"][0]["followers"] == 5400
    assert post_history.status_code == 200, post_history.text
    assert post_history.json()["snapshots"][0]["views"] == 7654

    async def seed_report_with_pinned_evidence():
        async with session_factory() as db:
            evidence = await db.scalar(select(MarketEvidence).where(MarketEvidence.source_id == source_id))
            observation = await db.scalar(select(MarketObservation).where(MarketObservation.evidence_id == evidence.id))
            report = MarketReport(
                company_id=workspace_id, group_id=group_id, cycle_id=None,
                window_start=observed_at - timedelta(hours=12), window_end=observed_at,
                report_json={"headline": "Xu hướng", "source_audience": [{"followers": 5400}]},
                evidence_ids_json=[evidence.id], coverage_json={}, model_name="fixture",
            )
            db.add(report)
            await db.flush()
            db.add(MarketReportEvidence(
                company_id=workspace_id, group_id=group_id, report_id=report.id,
                evidence_id=evidence.id, observation_id=observation.id,
                evidence_version_id=observation.evidence_version_id,
            ))
            await db.commit()
            return report.id

    report_id = asyncio.run(seed_report_with_pinned_evidence())
    reports = client.get(f"/api/v1/workspaces/{workspace_id}/market-research/groups/{group_id}/reports")
    assert reports.status_code == 200, reports.text
    report_out = next(item for item in reports.json() if item["id"] == report_id)
    assert report_out["evidence_refs"][0]["evidence_version_id"] == observation.evidence_version_id
    assert report_out["evidence_refs"][0]["provenance_status"] == "verified"
    assert report_out["source_audience"][0]["followers"] == 5400

    async def seed_previous_snapshot():
        async with session_factory() as db:
            evidence = await db.scalar(select(MarketEvidence).where(MarketEvidence.source_id == source_id))
            assert evidence is not None
            db.add(MarketObservation(
                id=new_id(), company_id=workspace_id, evidence_id=evidence.id,
                observed_at=observed_at - timedelta(hours=12),
                metrics_json={
                    "reactions": 10, "comments": 3, "shares": 2,
                    "interactions": 15, "views": 7000,
                }, comments_json=["snapshot cũ"],
            ))
            await db.commit()

    asyncio.run(seed_previous_snapshot())
    report_evidence = asyncio.run(research_tasks._evidence_for_report(workspace_id, group_id))
    assert len(report_evidence) == 1
    assert report_evidence[0]["metric_delta"] == {
        "reactions": 12, "comments": 2, "shares": 1, "interactions": 15, "views": 654,
    }
    assert report_evidence[0]["comments"] == ["Bài này hữu ích"]


def test_due_market_research_enqueues_one_durable_cycle(market_api) -> None:
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "schedule-owner@example.com")
    group_id = _create_group(client, workspace_id, headers)
    source = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={"group_id": group_id, "source_type": "website", "name": "Website", "url": "https://example.com"},
    )
    assert source.status_code == 201, source.text
    now = datetime.now(timezone.utc)

    async def set_due_time():
        async with session_factory() as db:
            group = await db.get(MetaPageGroup, group_id)
            assert group is not None
            group.next_due_at = now - timedelta(seconds=1)
            await db.commit()

    async def enqueue():
        async with session_factory() as db:
            count = await scheduled_jobs._enqueue_due_research(db, now)
            await db.commit()
            return count

    asyncio.run(set_due_time())
    assert asyncio.run(enqueue()) == 1
    assert asyncio.run(enqueue()) == 0

    async def cycle_state():
        async with session_factory() as db:
            return await db.scalar(select(ResearchCycle.status).where(ResearchCycle.group_id == group_id))

    assert asyncio.run(cycle_state()) == "queued"
