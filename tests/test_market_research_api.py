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
    AIUsageBudgetDay, AIUsageLedger, Base, Campaign, Job, MarketEvidence, MarketEvidenceVersion, MarketObservation, MetaPageConnection,
    MarketReport, MarketReportEvidence, MetaPageGroup, ResearchCycle, ResearchSource, new_id,
)
from services.api import market_research as market_research_routes
from services.api import meta_tokens
from services.api.db import get_db
from services.api.meta_client import MetaPagePost, MetaPagePostsPage, MetaPublicPage
from services.api.main import app
from tests.helpers.page_workspace import activate_test_page
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
    workspace = activate_test_page(client)
    return workspace["id"], {
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


def test_research_ai_budget_is_workspace_scoped_and_reports_reserved_cost(market_api) -> None:
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "budget-owner@example.com")

    initial = client.get(f"/api/v1/workspaces/{workspace_id}/market-research/ai-budget")
    assert initial.status_code == 200, initial.text
    initial_payload = initial.json()
    assert initial_payload["currency"] == "USD"
    assert initial_payload["limit_micro_usd"] == 2_000_000
    assert initial_payload["spent_micro_usd"] == 0
    assert initial_payload["reserved_micro_usd"] == 0
    assert initial_payload["available_micro_usd"] == 2_000_000
    assert initial_payload["unsettled_requests"] == 0
    group_id = _create_group(client, workspace_id, headers)

    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    budget_date = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()

    async def seed_budget() -> None:
        async with session_factory() as db:
            db.add(AIUsageBudgetDay(
                company_id=workspace_id,
                budget_date=budget_date,
                limit_micro_usd=2_000_000,
                reserved_micro_usd=250_000,
                spent_micro_usd=125_000,
            ))
            db.add(AIUsageLedger(
                id=new_id(),
                company_id=workspace_id,
                request_key="budget-api-test",
                provider="deepseek",
                model="deepseek-flash",
                operation="market_research_report",
                budget_class="automatic",
                budget_date=budget_date,
                pricing_version="fixture",
                cost_basis="fixture",
                reserved_micro_usd=250_000,
                status="unknown",
            ))
            now = datetime.now(timezone.utc)
            db.add(MarketReport(
                id=new_id(),
                company_id=workspace_id,
                group_id=group_id,
                window_start=now,
                window_end=now,
                report_json={"analysis_status": "deferred_budget"},
                evidence_ids_json=[],
                coverage_json={},
            ))
            await db.commit()

    asyncio.run(seed_budget())
    populated = client.get(f"/api/v1/workspaces/{workspace_id}/market-research/ai-budget")
    assert populated.status_code == 200, populated.text
    populated_payload = populated.json()
    assert populated_payload["reserved_micro_usd"] == 250_000
    assert populated_payload["spent_micro_usd"] == 125_000
    assert populated_payload["available_micro_usd"] == 1_625_000
    assert populated_payload["unsettled_requests"] == 1
    assert populated_payload["pending_reports"] == 1


def test_market_suggestion_draft_pins_report_observation_and_version(market_api) -> None:
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "pinned-report-owner@example.com")
    group_id = _create_group(client, workspace_id, headers)
    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "competitor_facebook_page",
            "name": "Nguồn tham khảo",
            "url": "https://www.facebook.com/reference-page",
            "competitor_name": "Nguồn tham khảo",
        },
    )
    assert source_response.status_code == 201, source_response.text
    source_id = source_response.json()["id"]
    now = datetime.now(timezone.utc)
    report_id, evidence_id, version_id, observation_id = (new_id() for _ in range(4))

    async def seed_report() -> None:
        async with session_factory() as db:
            db.add(MarketEvidence(
                id=evidence_id,
                company_id=workspace_id,
                group_id=group_id,
                source_id=source_id,
                canonical_url="https://www.facebook.com/reference-page/posts/123",
                title="Bài hiện tại đã đổi",
                text="Bản thân bài hiện tại không được thay report cũ.",
                content_hash="b" * 64,
                trust_level="external_unverified",
                first_seen_at=now,
                last_seen_at=now,
            ))
            db.add(MarketEvidenceVersion(
                id=version_id,
                company_id=workspace_id,
                evidence_id=evidence_id,
                content_hash="a" * 64,
                parser_version="fixture-parser-v1",
                title="Tiêu đề tại thời điểm báo cáo",
                text="Nội dung đã được dùng cho báo cáo nghiên cứu.",
                published_at=now,
                captured_at=now,
            ))
            db.add(MarketObservation(
                id=observation_id,
                company_id=workspace_id,
                evidence_id=evidence_id,
                evidence_version_id=version_id,
                observed_at=now,
                metrics_json={"reactions": 14, "shares": 3},
                comments_json=["Không được tự đưa bình luận vào campaign context"],
            ))
            db.add(MarketReport(
                id=report_id,
                company_id=workspace_id,
                group_id=group_id,
                window_start=now,
                window_end=now,
                report_json={
                    "analysis_status": "completed",
                    "suggestions": [{
                        "title": "Hướng nội dung đã chọn",
                        "angle": "Giải thích câu hỏi phổ biến",
                        "hook": "Bạn thường băn khoăn điều gì?",
                        "format": "text",
                        "evidence_ids": [evidence_id],
                    }],
                    "evidence_refs": [{
                        "id": evidence_id,
                        "title": "Tiêu đề tại thời điểm báo cáo",
                        "url": "https://www.facebook.com/reference-page/posts/123",
                        "published_at": now.isoformat(),
                        "observed_at": now.isoformat(),
                        "evidence_version_id": version_id,
                        "observation_id": observation_id,
                        "content_hash": "a" * 64,
                        "metrics": {"reactions": 14, "shares": 3},
                    }],
                },
                evidence_ids_json=[evidence_id],
                coverage_json={"ai_status": "completed"},
                model_name="fixture-model",
            ))
            db.add(MarketReportEvidence(
                company_id=workspace_id,
                group_id=group_id,
                report_id=report_id,
                observation_id=observation_id,
                evidence_id=evidence_id,
                evidence_version_id=version_id,
            ))
            await db.commit()

    asyncio.run(seed_report())
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/reports/{report_id}/draft",
        headers=headers,
        json={"suggestion_index": 0},
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["campaign_id"]

    async def read_brief() -> dict:
        async with session_factory() as db:
            campaign = await db.get(Campaign, campaign_id)
            assert campaign is not None
            return campaign.brief_json

    market_context = asyncio.run(read_brief())["market_research_context"]
    assert market_context["report_id"] == report_id
    assert market_context["evidence"] == [{
        "id": evidence_id,
        "title": "Tiêu đề tại thời điểm báo cáo",
        "url": "https://www.facebook.com/reference-page/posts/123",
        "published_at": now.replace(tzinfo=None).isoformat(),
        "evidence_version_id": version_id,
        "observation_id": observation_id,
        "content_hash": "a" * 64,
        "observed_at": now.replace(tzinfo=None).isoformat(),
        "metrics": {"reactions": 14, "shares": 3},
    }]


def test_page_token_is_encrypted_and_same_page_can_reconnect(market_api, monkeypatch) -> None:
    client, session_factory, encryption_key = market_api
    from services.api import workspaces as workspaces_routes

    monkeypatch.setattr(workspaces_routes, "MetaGraphClient", FakeMetaGraphClient)
    monkeypatch.setattr(workspaces_routes, "encrypt_page_token", meta_tokens.encrypt_page_token)
    workspace_id, headers = _owner(client, "page-owner@example.com")
    page_id = client.get(f"/api/v1/workspaces/{workspace_id}").json()["page_id"]
    token = "test-page-access-token-12345"
    pages_url = f"/api/v1/workspaces/{workspace_id}/market-research/pages"
    pages = client.get(pages_url)
    assert pages.status_code == 200
    assert pages.json()[0]["status"] == "verified"
    assert "encrypted_token" not in pages.json()[0]
    connection_id = pages.json()[0]["id"]

    async def read_connection():
        async with session_factory() as db:
            return await db.scalar(select(MetaPageConnection).where(MetaPageConnection.id == connection_id))

    stored = asyncio.run(read_connection())
    assert stored.encrypted_token != token
    assert meta_tokens.decrypt_page_token(stored.encrypted_token) == token

    reconnected = client.patch(
        f"/api/v1/workspaces/{workspace_id}/page-connection",
        headers=headers,
        json={"page_id": page_id, "page_access_token": token + "-rotated"},
    )
    assert reconnected.status_code == 200, reconnected.text
    assert reconnected.json()["id"] == workspace_id

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
    assert source["status"] == "active"
    assert source["collection_mode"] == "public_web"
    assert source["collection_post_limit"] == 50
    assert source["schedule_enabled"] is True

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

    saved_posts = client.get(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}/posts",
    )
    assert saved_posts.status_code == 200, saved_posts.text
    assert saved_posts.json()["posts"][0]["url"] == "https://www.facebook.com/rival/posts/42"
    assert saved_posts.json()["posts"][0]["metrics"]["comments"] == 7

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


def test_competitor_source_runs_without_page_token_and_keeps_collection_settings(market_api, monkeypatch) -> None:
    async def no_redis_dispatch(_job_id: str) -> bool:
        return False

    monkeypatch.setattr(market_research_routes, "dispatch_research_job", no_redis_dispatch)
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "public-page-owner@example.com")
    group_id = _create_group(client, workspace_id, headers)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "competitor_facebook_page",
            "name": "Fanpage đối thủ",
            "url": "https://www.facebook.com/rival",
        },
    )
    assert created.status_code == 201, created.text
    source = created.json()
    assert source["collection_mode"] == "public_web"

    updated = client.patch(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}/collection-settings",
        headers=headers,
        json={"collector": "public_web", "schedule_enabled": False, "post_limit": 12},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["collection_post_limit"] == 12
    assert updated.json()["schedule_enabled"] is False

    accepted = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}/crawl",
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]

    async def read_job():
        async with session_factory() as db:
            return await db.get(Job, job_id)

    job = asyncio.run(read_job())
    assert job is not None
    assert job.result["source_ids"] == [source["id"]]


def test_public_facebook_collection_requires_built_runner(market_api, monkeypatch) -> None:
    _client, _session_factory, _encryption_key = market_api
    monkeypatch.setattr(research_tasks, "settings", SimpleNamespace(
        facebook_cli_runner_path="",
    ))
    finished: list[dict[str, object]] = []

    async def open_run(*_args):
        return "run-1"

    async def finish_run(_company_id, _run_id, **kwargs):
        finished.append(kwargs)

    monkeypatch.setattr(research_tasks, "_open_competitor_run", open_run)
    monkeypatch.setattr(research_tasks, "_finish_competitor_run", finish_run)
    source = SimpleNamespace(id="source-1", collection_post_limit=50, url="https://facebook.com/rival")

    async def collect():
        return await research_tasks._collect_public_competitor_page(
            "company-1", "group-1", source, datetime.now(timezone.utc),
            cycle_id="cycle-1", job_id="job-1",
        )

    with pytest.raises(research_tasks.CrawlError) as error:
        asyncio.run(collect())

    assert error.value.code == "engine_unavailable"
    assert len(finished) == 1
    assert finished[0]["status"] == "error"
    assert finished[0]["counters"]["blocked_reason"] == "engine_unavailable"


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
            source.collection_mode = "meta_api"
        return await research_tasks._collect_competitor_page(
            workspace_id, group_id, source, datetime.now(timezone.utc),
        )

    saved, details = asyncio.run(collect())
    assert saved == 1
    assert details["metrics_available"] == ["reactions", "comments", "shares", "interactions"]
    assert details["metrics_unavailable"] == ["views"]
    assert details["comments_content"] == "privacy_hold"

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
    assert observation.comments_json == []

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
    from services.api import workspaces as workspaces_routes

    monkeypatch.setattr(workspaces_routes, "encrypt_page_token", meta_tokens.encrypt_page_token)
    monkeypatch.setattr(market_research_routes, "MetaGraphClient", FakeMetaGraphClient)
    monkeypatch.setattr(research_tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(research_tasks, "settings", SimpleNamespace(meta_graph_version="v26.0"))
    workspace_id, headers = _owner(client, "owned-page-owner@example.com")
    page_id = client.get(f"/api/v1/workspaces/{workspace_id}").json()["page_id"]
    token = "opaque-owned-page-token-with-entropy-12345"
    connected = client.patch(
        f"/api/v1/workspaces/{workspace_id}/page-connection",
        headers=headers,
        json={"page_id": page_id, "page_access_token": token},
    )
    assert connected.status_code == 200, connected.text
    connection = client.get(f"/api/v1/workspaces/{workspace_id}/market-research/pages").json()[0]
    connection_id = connection["id"]
    group_id = connection["group_id"]

    async def find_owned_source_id():
        async with session_factory() as db:
            source = await db.scalar(select(ResearchSource).where(
                ResearchSource.company_id == workspace_id,
                ResearchSource.connection_id == connection_id,
                ResearchSource.source_type == "owned_facebook_page",
            ))
            assert source is not None
            return source.id

    source_id = asyncio.run(find_owned_source_id())

    expected_page_id = page_id

    class FakeOwnedGraphClient:
        def __init__(self, actual_page_id: str, page_token: str, graph_version: str):
            assert actual_page_id == expected_page_id
            assert page_token == token
            assert graph_version == "v26.0"
            self.page_id = actual_page_id

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def read_page_followers_count(self):
            return 5400

        async def list_page_posts(self, limit: int = 100, after: str | None = None):
            assert limit == 100 and after is None
            return MetaPagePostsPage((MetaPagePost(
                external_post_id=f"{self.page_id}_42", message="Bài viết mới", created_time=None,
                permalink_url=f"https://www.facebook.com/{self.page_id}/posts/42",
                reactions=22, comments=5, shares=3,
            ),), None)

        async def read_post_media_views(self, external_post_id: str):
            assert external_post_id == f"{page_id}_42"
            return 7654

        async def list_post_comments(self, external_post_id: str, limit: int = 50):
            assert external_post_id == f"{page_id}_42" and limit == 50
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
    assert details["comments_content"] == "privacy_hold"

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
    assert observation.comments_json == []

    async def read_page_and_post_history():
        from database.models import MetaPageMetricSnapshot, MetaPagePost, MetaPostMetricSnapshot

        async with session_factory() as db:
            page_snapshot = await db.scalar(select(MetaPageMetricSnapshot).where(
                MetaPageMetricSnapshot.connection_id == connection_id,
            ))
            page_post = await db.scalar(select(MetaPagePost).where(
                MetaPagePost.company_id == workspace_id,
                MetaPagePost.external_post_id == f"{page_id}_42",
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
    assert report_evidence[0]["comments"] == []
    assert report_evidence[0]["comments_content_status"] == "privacy_hold"


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


def test_disabling_last_source_schedule_clears_group_due_time(market_api) -> None:
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "schedule-settings-owner@example.com")
    group_id = _create_group(client, workspace_id, headers)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={"group_id": group_id, "source_type": "website", "name": "Website", "url": "https://example.com"},
    )
    assert response.status_code == 201, response.text
    source_id = response.json()["id"]

    disabled = client.patch(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/crawl-settings",
        headers=headers,
        json={"crawl_mode": "site_catalog", "crawl_page_limit": 25, "render_mode": "http_only",
              "resource_hosts": [], "schedule_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["schedule_enabled"] is False
    assert disabled.json()["next_due_at"] is None

    async def read_due_times():
        async with session_factory() as db:
            source = await db.get(ResearchSource, source_id)
            group = await db.get(MetaPageGroup, group_id)
            return source.next_due_at, group.next_due_at

    source_due, group_due = asyncio.run(read_due_times())
    assert source_due is None
    assert group_due is None

    async def make_disabled_source_overdue_and_enqueue() -> int:
        now = datetime.now(timezone.utc)
        async with session_factory() as db:
            source = await db.get(ResearchSource, source_id)
            group = await db.get(MetaPageGroup, group_id)
            assert source is not None and group is not None
            source.next_due_at = now - timedelta(seconds=1)
            group.next_due_at = now - timedelta(seconds=1)
            await db.commit()
            count = await scheduled_jobs._enqueue_due_research(db, now)
            await db.commit()
            return count

    assert asyncio.run(make_disabled_source_overdue_and_enqueue()) == 0
