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
    AIUsageBudgetDay, AIUsageLedger, Base, Brand, BrandProfileRevision, Campaign, Job, MarketEvidence, MarketEvidenceVersion, MarketObservation, MetaPageConnection,
    MarketReport, MarketReportEvidence, MetaPageGroup, ResearchCycle, ResearchSource, Company, new_id,
    Membership, ResearchPrivacyPolicyRevision, User, WebCrawlRun,
)
from services.api import market_research as market_research_routes
from services.api import meta_tokens
from services.api.db import get_db
from services.api.meta_client import MetaPagePost, MetaPagePostsPage, MetaPublicPage
from services.api.main import app
from tests.helpers.page_workspace import activate_test_page
from services.api.meta_client import MetaPage
from services.worker import research_tasks, scheduled_jobs
from services.api.security import create_access_token, hash_password


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
    assert source_response.json()["status"] == "needs_privacy_policy"
    assert source_response.json()["collection_status"] == "privacy_policy_required"
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
                    "business_profile_context": {
                        "status": "applied", "brand_id": "brand-1",
                        "revision_id": "revision-3", "revision": 3,
                    },
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
                coverage_json={
                    "ai_status": "completed",
                    "business_profile_context": {
                        "status": "applied", "brand_id": "brand-1",
                        "revision_id": "revision-3", "revision": 3,
                    },
                },
                model_name="fixture-model",
            ))
            group = await db.get(MetaPageGroup, group_id)
            assert group is not None
            group.industry = "Chưa xác định"
            group.region = "unknown"
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

    brief = asyncio.run(read_brief())
    market_context = brief["market_research_context"]
    assert market_context["report_id"] == report_id
    assert brief["audience"] == []
    assert market_context["business_profile_context"] == {
        "status": "applied", "brand_id": "brand-1",
        "revision_id": "revision-3", "revision": 3,
    }
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


def test_research_context_requires_the_current_applied_manual_profile(market_api, monkeypatch) -> None:
    _client, session_factory, _encryption_key = market_api
    workspace_id, _headers = _owner(_client, "research-brand-profile@example.com")
    from services.worker import research_tasks

    async def seed_profile():
        async with session_factory() as db:
            user = await db.scalar(select(User).where(User.email == "research-brand-profile@example.com"))
            brand = await db.scalar(select(Brand).where(Brand.company_id == workspace_id))
            assert user is not None and brand is not None
            profile_text = "Chúng tôi bán trà rang nhẹ, giọng gần gũi và không phóng đại công dụng."
            brand.version = 4
            brand.profile = {
                "profile_mode": "manual_text_v1",
                "profile_text": profile_text,
                "version": 4,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
                "confirmed_by": user.id,
            }
            revision = BrandProfileRevision(
                brand_id=brand.id,
                company_id=workspace_id,
                revision=4,
                profile_json=dict(brand.profile),
                source_refs_json=[],
                warnings_json=[],
                confirmed_at=datetime.now(timezone.utc),
                confirmed_by=user.id,
            )
            db.add(revision)
            await db.flush()
            await db.commit()
            return brand.id, revision.id, user.id, profile_text

    brand_id, revision_id, user_id, profile_text = asyncio.run(seed_profile())
    monkeypatch.setattr(research_tasks, "SessionLocal", session_factory)
    context, provenance = asyncio.run(research_tasks._active_owner_brand_context(workspace_id))

    assert context == {
        "source": "owner_authored",
        "brand_id": brand_id,
        "revision_id": revision_id,
        "revision": 4,
        "profile_text": profile_text,
    }
    assert provenance == {
        "status": "applied",
        "brand_id": brand_id,
        "revision_id": revision_id,
        "revision": 4,
    }
    assert context["revision_id"] == revision_id

    async def switch_back_to_legacy():
        async with session_factory() as db:
            brand = await db.scalar(select(Brand).where(Brand.company_id == workspace_id))
            assert brand is not None
            brand.profile = {"business": "AI legacy profile", "confirmed_by": user_id}
            await db.commit()

    asyncio.run(switch_back_to_legacy())
    context, provenance = asyncio.run(research_tasks._active_owner_brand_context(workspace_id))
    assert context is None
    assert provenance == {"status": "not_configured"}


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


def test_manual_competitor_import_requires_policy_and_holds_comment_text(market_api) -> None:
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
    assert source["status"] == "needs_privacy_policy"
    assert source["collection_mode"] == "public_web"
    assert source["collection_post_limit"] == 50
    assert source["schedule_enabled"] is True

    import_url = f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}/import"
    import_body = {"rows": [{
        "url": "https://www.facebook.com/rival/posts/42",
        "title": "Bài đối thủ",
        "text": "Liên hệ 0901234567 hoặc trend@example.com",
        "observed_at": "2026-09-25T12:00:00Z",
        "metrics": {"reactions": 45, "comments": 7, "shares": 3, "views": 1000},
        "comments": ["Nhắn tôi tại contact@example.com", "SĐT 0912345678"],
    }]}
    withheld = client.post(import_url, headers=headers, json=import_body)
    assert withheld.status_code == 409
    assert withheld.json()["error"]["code"] == "privacy_policy_required"
    configured = client.put(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}/privacy-policy",
        headers=headers,
        json={
            "purpose": "Tổng hợp câu hỏi công khai để lập báo cáo nghiên cứu.",
            "processing_basis_reference": "Hồ sơ rà soát nội bộ PRIV-2026-09.",
            "policy_version": "privacy-policy-v1",
            "requested_retention_days": 90,
        },
    )
    assert configured.status_code == 200
    imported = client.post(
        import_url,
        headers=headers,
        json=import_body,
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["imported"] == 1
    assert imported.json()["comments_content_status"] == "privacy_hold"
    assert imported.json()["comments_withheld_count"] == 2
    assert "contact@example.com" not in imported.text
    assert "0912345678" not in imported.text

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
    assert observation.comments_json == []
    assert {key: value for key, value in observation.metrics_json.items() if key != "privacy_redaction"} == {
        "reactions": 45, "comments": 7, "shares": 3, "views": 1000,
    }
    assert observation.metrics_json["privacy_redaction"]["content"]["redaction_count"] == 2
    assert observation.metrics_json["privacy_redaction"]["content"]["status"] == "pattern_redacted_review_incomplete"
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


def test_disconnected_page_blocks_research_but_allows_only_cancelling_schedules(market_api) -> None:
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "page-gate-settings@example.com")
    group_id = _create_group(client, workspace_id, headers)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "competitor_facebook_page",
            "name": "Nguồn công khai",
            "url": "https://www.facebook.com/rival-page-gate",
        },
    )
    assert created.status_code == 201, created.text
    source = created.json()
    website_created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "website",
            "name": "Trang công khai",
            "url": "https://example.com/news",
        },
    )
    assert website_created.status_code == 201, website_created.text
    website = website_created.json()
    website_settings = {
        "crawl_mode": "site_catalog",
        "crawl_page_limit": 1000,
        "render_mode": "http_only",
        "resource_hosts": [],
        "schedule_enabled": True,
    }
    website_enabled = client.patch(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{website['id']}/crawl-settings",
        headers=headers,
        json=website_settings,
    )
    assert website_enabled.status_code == 200, website_enabled.text

    async def require_reconnect() -> None:
        async with session_factory() as db:
            company = await db.get(Company, workspace_id)
            assert company is not None
            company.page_connection_state = "needs_reconnect"
            await db.commit()

    asyncio.run(require_reconnect())
    source_path = f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}"

    paused = client.patch(
        source_path + "/collection-settings",
        headers=headers,
        json={"collector": "public_web", "schedule_enabled": False, "post_limit": source["collection_post_limit"]},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["schedule_enabled"] is False

    resumed = client.patch(
        source_path + "/collection-settings",
        headers=headers,
        json={"collector": "public_web", "schedule_enabled": True, "post_limit": source["collection_post_limit"]},
    )
    assert resumed.status_code == 409
    assert resumed.json()["error"]["code"] == "page_needs_reconnect"

    changed_while_paused = client.patch(
        source_path + "/collection-settings",
        headers=headers,
        json={"collector": "public_web", "schedule_enabled": False, "post_limit": source["collection_post_limit"] - 1},
    )
    assert changed_while_paused.status_code == 409
    assert changed_while_paused.json()["error"]["code"] == "page_needs_reconnect"

    website_paused = client.patch(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{website['id']}/crawl-settings",
        headers=headers,
        json={**website_settings, "schedule_enabled": False},
    )
    assert website_paused.status_code == 200, website_paused.text
    website_resumed = client.patch(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{website['id']}/crawl-settings",
        headers=headers,
        json=website_settings,
    )
    assert website_resumed.status_code == 409
    assert website_resumed.json()["error"]["code"] == "page_needs_reconnect"

    crawl = client.post(source_path + "/crawl", headers=headers)
    assert crawl.status_code == 409
    assert crawl.json()["error"]["code"] == "page_needs_reconnect"

    group_crawl = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/groups/{group_id}/crawl",
        headers=headers,
    )
    assert group_crawl.status_code == 409
    assert group_crawl.json()["error"]["code"] == "page_needs_reconnect"

    added_while_disconnected = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "website",
            "name": "Nguồn mới bị chặn",
            "url": "https://example.org/news",
        },
    )
    assert added_while_disconnected.status_code == 409
    assert added_while_disconnected.json()["error"]["code"] == "page_needs_reconnect"

    stopped = client.delete(source_path, headers=headers)
    assert stopped.status_code == 204, stopped.text


def test_page_read_verification_does_not_claim_publish_permission(market_api) -> None:
    client, _session_factory, _encryption_key = market_api
    workspace_id, _headers = _owner(client, "page-capability-owner@example.com")

    response = client.get(f"/api/v1/workspaces/{workspace_id}/meta/connection")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "verified"
    assert body["read_posts_capability"] == "verified"
    assert body["publish_capability"] == "not_tested"
    assert body["can_publish"] is False
    assert "chưa được thử" in body["message"]


def test_public_facebook_collection_requires_built_runner(market_api, monkeypatch) -> None:
    _client, _session_factory, _encryption_key = market_api
    monkeypatch.setattr(research_tasks, "settings", SimpleNamespace(
        facebook_cli_runner_path="",
    ))
    finished: list[dict[str, object]] = []

    async def open_run(*_args, **_kwargs):
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
    assert created.json()["status"] == "needs_privacy_policy"
    policy = client.put(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/privacy-policy",
        headers=headers,
        json={
            "purpose": "Tổng hợp dữ liệu công khai phục vụ nghiên cứu.",
            "processing_basis_reference": "Hồ sơ rà soát nội bộ PRIV-2026-09.",
            "policy_version": "privacy-policy-v1",
            "requested_retention_days": 90,
        },
    )
    assert policy.status_code == 200
    assert policy.json()["collection_ready"] is True
    assert policy.json()["legal_basis_verified"] is False

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
                link_url="https://news.example/story?token=private&lang=vi",
                attachments=({
                    "kind": "image", "provider_type": "photo", "title": "Ảnh sản phẩm",
                    "description": "Mô tả bất kỳ", "target_url": "javascript:alert(1)",
                    "content_status": "metadata_only_privacy_hold",
                },),
                attachment_metadata_status="returned",
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
    assert {key: value for key, value in observation.metrics_json.items() if key != "privacy_redaction"} == {
        "reactions": 17, "comments": 4, "shares": 2, "interactions": 23,
        "views": None,
        "link_url": "https://news.example/story",
        "attachments": [{
            "kind": "image", "provider_type": "photo", "title": None,
            "description": None, "target_url": None,
            "content_status": "metadata_only_privacy_hold",
        }],
        "attachment_metadata_status": "returned",
    }
    assert observation.metrics_json["privacy_redaction"]["redactor_version"] == "facebook-contact-patterns-v1"
    assert observation.metrics_json["privacy_redaction"]["status"] == "pattern_redacted_review_incomplete"
    assert observation.comments_json == []
    posts = client.get(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/posts",
        headers=headers,
    )
    assert posts.status_code == 200, posts.text
    assert posts.json()["posts"][0]["link_url"] == "https://news.example/story"
    assert posts.json()["posts"][0]["attachments"][0]["target_url"] is None
    assert posts.json()["posts"][0]["attachments"][0]["content_status"] == "metadata_only_privacy_hold"
    assert posts.json()["posts"][0]["attachments"][0]["title"] is None
    assert posts.json()["posts"][0]["attachments"][0]["description"] is None

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
    source_settings = client.patch(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/collection-settings",
        headers=headers,
        json={"collector": "meta_api", "schedule_enabled": True, "post_limit": 100},
    )
    assert source_settings.status_code == 200, source_settings.text
    assert source_settings.json()["schedule_enabled"] is True
    assert source_settings.json()["collection_mode"] == "meta_api"
    rejected_collector = client.patch(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/collection-settings",
        headers=headers,
        json={"collector": "public_web", "schedule_enabled": True, "post_limit": 100},
    )
    assert rejected_collector.status_code == 422
    assert rejected_collector.json()["error"]["code"] == "owned_page_collector_fixed"

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
            if after is None:
                assert limit in {50, 100}
                return MetaPagePostsPage((MetaPagePost(
                    external_post_id=f"{self.page_id}_42",
                    message=("Bài viết mới; liên hệ owner@example.invalid hoặc 0901 234 567. "
                             "Địa chỉ nhà riêng: 12/5 Đường Cá Nhân, Quận 1."),
                    created_time=observed_at,
                    permalink_url=f"https://www.facebook.com/{self.page_id}/posts/42",
                    reactions=22, comments=5, shares=3,
                    link_url="https://example.com/landing?utm_source=facebook",
                    attachments=({
                        "kind": "image", "provider_type": "photo", "title": "Ảnh minh họa",
                        "description": None, "target_url": None,
                        "content_status": "metadata_only_privacy_hold",
                    },),
                    attachment_metadata_status="returned",
                ),), "history-1" if limit == 50 else None)
            if after == "history-1":
                assert limit == 50
                return MetaPagePostsPage((MetaPagePost(
                    external_post_id=f"{self.page_id}_41", message="Bài viết tháng trước",
                    created_time=observed_at - timedelta(days=30),
                    permalink_url=f"https://www.facebook.com/{self.page_id}/posts/41",
                    reactions=4, comments=1, shares=0,
                ),), "history-2")
            if after == "history-2":
                assert limit == 50
                return MetaPagePostsPage((MetaPagePost(
                    external_post_id=f"{self.page_id}_40", message="Bài viết cũ trong cửa sổ",
                    created_time=observed_at - timedelta(days=89),
                    permalink_url=f"https://www.facebook.com/{self.page_id}/posts/40",
                    reactions=2, comments=0, shares=0,
                ),), None)
            raise AssertionError(f"unexpected Meta cursor: {after}")

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
    assert saved == 2
    assert details["metrics_available"] == ["reactions", "comments", "shares", "interactions", "views"]
    assert details["metrics_unavailable"] == []
    assert details["comments_content"] == "privacy_hold"
    assert details["requested_post_budget"] == 100
    assert details["history_complete"] is False
    assert details["window_coverage_complete"] is False
    assert details["coverage_status"] == "backfill_in_progress"
    assert details["next_checkpoint_available"] is True

    async def read_backfill_checkpoint():
        async with session_factory() as db:
            source = await db.get(ResearchSource, source_id)
            assert source is not None
            return (source.owned_page_backfill_cursor, source.owned_page_backfill_page_id,
                    source.owned_page_backfill_complete, source.owned_page_backfill_window_complete,
                    source.owned_page_backfill_pages_processed)

    assert asyncio.run(read_backfill_checkpoint()) == ("history-2", page_id, False, False, 1)

    # A later source run resumes the old-history cursor while refreshing the
    # newest page, and stops when the provider says there is no more history.
    second_saved, second_details = asyncio.run(collect())
    assert second_saved == 2
    assert second_details["history_complete"] is True
    assert second_details["window_coverage_complete"] is False
    assert second_details["coverage_status"] == "provider_history_exhausted_before_90_days"
    assert second_details["stop_reason"] == "provider_exhausted"
    assert asyncio.run(read_backfill_checkpoint()) == (None, page_id, True, False, 2)
    _, refresh_details = asyncio.run(collect())
    assert refresh_details["coverage_status"] == "provider_history_exhausted_before_90_days"
    assert refresh_details["window_coverage_complete"] is False

    async def read_observation():
        async with session_factory() as db:
            evidence = await db.scalar(select(MarketEvidence).where(MarketEvidence.source_id == source_id))
            observation = await db.scalar(select(MarketObservation).where(MarketObservation.evidence_id == evidence.id))
            return evidence, observation

    evidence, observation = asyncio.run(read_observation())
    assert observation is not None
    assert "owner@example.invalid" not in evidence.text
    assert "0901 234 567" not in evidence.text
    assert "12/5 Đường Cá Nhân" not in evidence.text
    assert "not_anonymization" in observation.metrics_json["privacy_redaction"]["limitations"]
    assert observation.metrics_json == {
        "reactions": 22, "comments": 5, "shares": 3, "interactions": 30,
        "views": 7654,
        "privacy_redaction": {
            "redactor_version": "facebook-contact-patterns-v1",
            "status": "pattern_redacted_review_incomplete",
            "redaction_count": 3,
            "redacted_fields": {"home_address": 1, "email": 1, "phone": 1},
            "limitations": ["names_not_detected", "not_anonymization", "manual_review_may_be_required"],
        },
        "link_url": "https://example.com/landing",
        "attachments": [{
            "kind": "image", "provider_type": "photo", "title": None,
            "description": None, "target_url": None,
            "content_status": "metadata_only_privacy_hold",
        }],
        "attachment_metadata_status": "returned",
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
    assert page_post.link_url == "https://example.com/landing"
    assert "owner@example.invalid" not in page_post.message
    assert page_post.attachments_json[0]["kind"] == "image"
    assert page_post.attachment_metadata_status == "returned"
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
    page_posts = client.get(f"/api/v1/workspaces/{workspace_id}/meta/page-posts", headers=headers)
    assert page_posts.status_code == 200, page_posts.text
    assert page_posts.json()["items"][0]["link_url"] == "https://example.com/landing"
    assert page_posts.json()["items"][0]["attachments"][0]["kind"] == "image"
    assert page_posts.json()["items"][0]["attachment_metadata_status"] == "returned"

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
    assert len(report_evidence) == 3
    latest_post = next(item for item in report_evidence if item["url"].endswith("/posts/42"))
    assert latest_post["metric_delta"] == {
        "reactions": 12, "comments": 2, "shares": 1, "interactions": 15, "views": 654,
    }
    assert latest_post["text"] == ""
    assert latest_post["content_processing_status"] == "privacy_review_required"
    assert latest_post["title"] == "Bài viết Facebook đang chờ rà soát dữ liệu cá nhân"
    assert latest_post["comments"] == []
    assert latest_post["comments_content_status"] == "privacy_hold"


def test_facebook_only_report_waits_for_privacy_review_without_provider_call(monkeypatch) -> None:
    def unexpected_provider_call():
        raise AssertionError("privacy-held Facebook text must not trigger an AI provider request")

    monkeypatch.setattr(research_tasks, "configured_structured_model", unexpected_provider_call)
    report, model_name, status = asyncio.run(research_tasks._make_report(
        "workspace-test", "cycle-test", SimpleNamespace(),
        evidence_rows=[{
            "id": "evidence-test",
            "content_processing_status": "privacy_review_required",
            "text": "",
        }],
        audience_rows=[],
        web_snapshot_rows=[],
    ))

    assert status == "deferred_privacy_review"
    assert model_name is None
    assert report["analysis_status"] == "deferred_privacy_review"
    assert report["privacy_coverage"]["facebook_post_text_withheld"] == 1
    assert report["privacy_coverage"]["comments_content_status"] == "privacy_hold"


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


def test_source_privacy_policy_records_configuration_but_does_not_verify_legal_basis(market_api) -> None:
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "privacy-policy-owner@example.com")
    group_id = _create_group(client, workspace_id, headers)
    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "competitor_facebook_page",
            "name": "Public competitor page",
            "url": "https://www.facebook.com/example.public.page",
        },
    )
    assert source_response.status_code == 201, source_response.text
    source_id = source_response.json()["id"]
    policy_url = f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/privacy-policy"

    empty = client.get(policy_url)
    assert empty.status_code == 200, empty.text
    assert empty.json()["configured"] is False
    assert empty.json()["collection_ready"] is False
    assert empty.json()["legal_basis_verified"] is False
    assert empty.json()["comments_content_status"] == "privacy_hold"
    assert empty.json()["retention_enforcement_status"] == "not_enforced"

    saved = client.put(policy_url, headers=headers, json={
        "purpose": "Tổng hợp câu hỏi công khai về sản phẩm để lập báo cáo nghiên cứu.",
        "processing_basis_reference": "Hồ sơ rà soát nội bộ PRIV-2026-09, mục 4.",
        "policy_version": "privacy-policy-2026-09-v1",
        "requested_retention_days": 90,
    })
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["configured"] is True
    assert body["collection_ready"] is True
    assert body["legal_basis_verified"] is False
    assert body["revision_no"] == 1
    assert body["requested_retention_days"] == 90
    assert body["retention_enforcement_status"] == "not_enforced"
    assert body["comments_content_status"] == "privacy_hold"
    sources_after_policy = client.get(f"/api/v1/workspaces/{workspace_id}/market-research/sources")
    resumed_source = next(item for item in sources_after_policy.json() if item["id"] == source_id)
    assert resumed_source["status"] == "active"
    reread = client.get(policy_url)
    assert reread.status_code == 200
    assert reread.json()["purpose"] == body["purpose"]

    async def read_policy():
        async with session_factory() as db:
            return await db.scalar(select(ResearchPrivacyPolicyRevision).where(
                ResearchPrivacyPolicyRevision.company_id == workspace_id,
                ResearchPrivacyPolicyRevision.source_id == source_id,
            ))

    persisted = asyncio.run(read_policy())
    assert persisted is not None
    assert persisted.policy_version == "privacy-policy-2026-09-v1"

    repeated = client.put(policy_url, headers=headers, json={
        "purpose": "Tổng hợp câu hỏi công khai về sản phẩm để lập báo cáo nghiên cứu.",
        "processing_basis_reference": "Hồ sơ rà soát nội bộ PRIV-2026-09, mục 4.",
        "policy_version": "privacy-policy-2026-09-v1",
        "requested_retention_days": 90,
    })
    assert repeated.status_code == 200
    assert repeated.json()["revision_no"] == 1
    revised = client.put(policy_url, headers=headers, json={
        "purpose": "Tổng hợp câu hỏi và chủ đề công khai cho báo cáo nghiên cứu.",
        "processing_basis_reference": "Hồ sơ rà soát nội bộ PRIV-2026-09, mục 4.",
        "policy_version": "privacy-policy-2026-09-v2",
        "requested_retention_days": 60,
    })
    assert revised.status_code == 200
    assert revised.json()["revision_no"] == 2

    async def count_policy_revisions():
        async with session_factory() as db:
            return len((await db.scalars(select(ResearchPrivacyPolicyRevision).where(
                ResearchPrivacyPolicyRevision.company_id == workspace_id,
                ResearchPrivacyPolicyRevision.source_id == source_id,
            ))).all())

    assert asyncio.run(count_policy_revisions()) == 2


def test_collection_run_pins_policy_snapshot_without_verifying_legal_basis(market_api, monkeypatch) -> None:
    async def no_redis_dispatch(_job_id: str) -> bool:
        return False

    monkeypatch.setattr(market_research_routes, "dispatch_research_job", no_redis_dispatch)
    monkeypatch.setattr(research_tasks, "SessionLocal", market_api[1])
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "privacy-run-snapshot@example.com")
    group_id = _create_group(client, workspace_id, headers)
    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "competitor_facebook_page",
            "name": "Public page policy snapshot",
            "url": "https://www.facebook.com/policy.snapshot.page",
        },
    )
    assert source_response.status_code == 201, source_response.text
    source_id = source_response.json()["id"]
    policy_url = f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/privacy-policy"
    policy_v1 = {
        "purpose": "Tổng hợp câu hỏi công khai cho báo cáo nghiên cứu.",
        "processing_basis_reference": "Hồ sơ rà soát PR-1.",
        "policy_version": "PR-1",
        "requested_retention_days": 90,
    }
    saved = client.put(policy_url, headers=headers, json=policy_v1)
    assert saved.status_code == 200, saved.text

    accepted = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/crawl",
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]

    async def read_source_and_cycle():
        async with session_factory() as db:
            source = await db.get(ResearchSource, source_id)
            cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id))
            assert source is not None and cycle is not None
            return source, cycle.id

    source, cycle_id = asyncio.run(read_source_and_cycle())
    run_id = asyncio.run(research_tasks._open_competitor_run(
        workspace_id, group_id, source, cycle_id, job_id,
    ))

    policy_v2 = {**policy_v1, "policy_version": "PR-2", "requested_retention_days": 30}
    revised = client.put(policy_url, headers=headers, json=policy_v2)
    assert revised.status_code == 200, revised.text
    assert revised.json()["revision_no"] == 2

    runs = client.get(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/collection-runs",
        headers=headers,
    )
    assert runs.status_code == 200, runs.text
    captured = next(run for run in runs.json() if run["id"] == run_id)
    assert captured["privacy_policy_revision_no"] == 1
    assert captured["privacy_policy_version"] == "PR-1"
    assert captured["privacy_policy_ready_for_collection"] is True
    assert captured["privacy_policy_legal_basis_verified"] is False
    assert captured["privacy_policy_requested_retention_days"] == 90
    assert captured["retention_enforcement_status"] == "not_enforced"
    assert captured["comments_content_status"] == "privacy_hold"


def test_research_source_checkpoint_retries_only_retryable_outcomes() -> None:
    checkpointed = research_tasks._checkpointed_research_source_ids([
        {"source_id": "done", "status": "collected"},
        {"source_id": "blocked", "status": "blocked", "retryable": False},
        {"source_id": "retry", "status": "failed", "retryable": True},
        {"status": "failed"},
        None,
    ])

    assert checkpointed == {"done", "blocked"}


def test_research_policy_snapshot_is_explicitly_not_enforced() -> None:
    configured = research_tasks._policy_snapshot(SimpleNamespace(
        id="policy-revision-1",
        revision_no=1,
        policy_version="policy-v1",
        requested_retention_days=90,
        purpose="Tổng hợp câu hỏi công khai.",
        processing_basis_reference="PRIV-2026-09",
    ))
    missing = research_tasks._policy_snapshot(None)

    assert configured == {
        "configured": True,
        "ready_for_collection": True,
        "legal_basis_verified": False,
        "revision_id": "policy-revision-1",
        "revision_no": 1,
        "version": "policy-v1",
        "requested_retention_days": 90,
        "retention_enforcement_status": "not_enforced",
        "comments_content_status": "privacy_hold",
    }
    assert missing["configured"] is False
    assert missing["ready_for_collection"] is False
    assert missing["legal_basis_verified"] is False
    assert missing["revision_id"] is None
    assert missing["retention_enforcement_status"] == "not_enforced"


def test_research_worker_blocks_facebook_fetch_until_policy_fields_are_recorded(market_api, monkeypatch) -> None:
    async def no_redis_dispatch(_job_id: str) -> bool:
        return False

    monkeypatch.setattr(market_research_routes, "dispatch_research_job", no_redis_dispatch)
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "research-policy-gate@example.com")
    group_id = _create_group(client, workspace_id, headers)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "competitor_facebook_page",
            "name": "Public page without policy",
            "url": "https://www.facebook.com/policy.gate.page",
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    accepted = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/groups/{group_id}/crawl",
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]

    async def unexpected_collection(*_args, **_kwargs):
        pytest.fail("collector must not run before source policy fields are recorded")

    monkeypatch.setattr(research_tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(research_tasks, "_collect_competitor_page", unexpected_collection)

    async def run_job():
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            assert job is not None
            job.status = "running"
            await db.commit()
        await research_tasks._run(job_id)

    asyncio.run(run_job())

    async def read_blocked_state():
        async with session_factory() as db:
            source = await db.get(ResearchSource, source_id)
            cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id))
            assert source is not None and cycle is not None
            return source.status, source.collection_status, source.next_due_at, list(cycle.source_results_json)

    status, collection_status, next_due_at, results = asyncio.run(read_blocked_state())
    assert status == "needs_privacy_policy"
    assert collection_status == "privacy_policy_required"
    assert next_due_at is None
    assert results[0]["code"] == "privacy_policy_required"
    assert results[0]["privacy_policy_snapshot"]["legal_basis_verified"] is False


def test_research_cycle_persists_source_checkpoint_for_worker_recovery(market_api, monkeypatch) -> None:
    async def no_redis_dispatch(_job_id: str) -> bool:
        return False

    monkeypatch.setattr(market_research_routes, "dispatch_research_job", no_redis_dispatch)
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "research-checkpoint@example.com")
    group_id = _create_group(client, workspace_id, headers)
    source_ids = []
    for source_name in ("First checkpoint fixture", "Second checkpoint fixture"):
        source_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/market-research/sources",
            headers=headers,
            json={
                "group_id": group_id,
                "source_type": "website",
                "name": source_name,
                "url": f"https://example.test/{source_name.split()[0].lower()}",
            },
        )
        assert source_response.status_code == 201, source_response.text
        source_ids.append(source_response.json()["id"])

    accepted = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/groups/{group_id}/crawl",
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    collector_calls: list[str] = []
    interrupted_source_attempts = 0

    async def collect_once(_company_id, _group_id, source, _observed_at, **_kwargs):
        nonlocal interrupted_source_attempts
        collector_calls.append(source.id)
        if source.id == source_ids[1] and interrupted_source_attempts == 0:
            interrupted_source_attempts += 1
            raise asyncio.CancelledError()
        return 0, {"items_saved": 0, "pages_visited": 1}

    monkeypatch.setattr(research_tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(research_tasks, "_collect_website", collect_once)

    async def start_job():
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            assert job is not None
            job.status = "running"
            await db.commit()
        await research_tasks._run(job_id)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(start_job())

    async def read_interrupted_checkpoint():
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id))
            assert job is not None and cycle is not None
            return job.status, list(cycle.source_results_json)

    interrupted_status, first_checkpoint = asyncio.run(read_interrupted_checkpoint())
    assert interrupted_status == "running"
    assert collector_calls == source_ids
    assert first_checkpoint == [{
        "source_id": source_ids[0],
        "status": "collected",
        "items_saved": 0,
        "pages_visited": 1,
    }]

    asyncio.run(research_tasks._run(job_id))

    async def read_recovered_cycle():
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id))
            assert job is not None and cycle is not None
            return job.status, list(cycle.source_results_json)

    recovered_status, recovered_checkpoint = asyncio.run(read_recovered_cycle())
    assert recovered_status == "succeeded"
    assert collector_calls == [source_ids[0], source_ids[1], source_ids[1]]
    assert [item["source_id"] for item in recovered_checkpoint] == source_ids


def test_source_privacy_policy_write_requires_owner(market_api) -> None:
    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "privacy-policy-permissions@example.com")
    group_id = _create_group(client, workspace_id, headers)
    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "group_id": group_id,
            "source_type": "website",
            "name": "Public source",
            "url": "https://example.test/research",
        },
    )
    assert source_response.status_code == 201, source_response.text
    source_id = source_response.json()["id"]

    async def add_editor() -> User:
        async with session_factory() as db:
            editor = User(
                id=new_id(),
                email="privacy-policy-editor@example.com",
                full_name="Editor",
                password_hash=hash_password("safe-test-password"),
            )
            db.add(editor)
            await db.flush()
            db.add(Membership(
                id=new_id(), company_id=workspace_id, user_id=editor.id,
                role="editor", is_active=True,
            ))
            await db.commit()
            return editor

    editor = asyncio.run(add_editor())
    editor_token, _expires_at = create_access_token(editor)
    policy_url = f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/privacy-policy"
    with TestClient(app) as editor_client:
        response = editor_client.put(
            policy_url,
            headers={"Authorization": f"Bearer {editor_token}"},
            json={
                "purpose": "Tổng hợp câu hỏi công khai về sản phẩm.",
                "processing_basis_reference": "Hồ sơ rà soát nội bộ PRIV-2026-09.",
                "policy_version": "privacy-policy-2026-09-v1",
                "requested_retention_days": 90,
            },
        )
    assert response.status_code == 403, response.text


def test_public_group_source_uses_tier0_metadata_and_supports_schedule_toggle(market_api) -> None:
    client, _session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "public-group-source@example.com")
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "source_type": "facebook_group",
            "name": "Nhóm công khai",
            "url": "https://facebook.com/groups/public-market?ref=share",
        },
    )
    assert created.status_code == 201, created.text
    source = created.json()
    assert source["source_type"] == "facebook_group"
    assert source["url"] == "https://www.facebook.com/groups/public-market"
    assert source["status"] == "needs_privacy_policy"
    assert source["collection_mode"] == "public_web"
    assert source["schedule_enabled"] is True

    source_url = f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source['id']}"
    runs = client.get(source_url + "/collection-runs", headers=headers)
    assert runs.status_code == 200, runs.text
    assert runs.json() == []

    paused = client.patch(
        source_url + "/collection-settings",
        headers=headers,
        json={"collector": "public_web", "schedule_enabled": False, "post_limit": 50},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["schedule_enabled"] is False
    assert paused.json()["next_due_at"] is None

    wrong_collector = client.patch(
        source_url + "/collection-settings",
        headers=headers,
        json={"collector": "meta_api", "schedule_enabled": True, "post_limit": 50},
    )
    assert wrong_collector.status_code == 422, wrong_collector.text
    assert wrong_collector.json()["error"]["code"] == "group_collector_fixed"


def test_public_group_source_rejects_non_group_facebook_urls(market_api) -> None:
    client, _session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "public-group-validation@example.com")
    rejected = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={
            "source_type": "facebook_group",
            "name": "Not a group",
            "url": "https://www.facebook.com/not-a-group",
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "facebook_group_url_required"


def test_public_group_worker_persists_shell_metadata_as_partial_without_report(market_api, monkeypatch) -> None:
    async def no_redis_dispatch(_job_id: str) -> bool:
        return False

    async def no_facebook_slot() -> None:
        return None

    async def acquired_cli_lock():
        return None, True

    async def no_cli_lock_release(_session) -> None:
        return None

    async def fake_group_collect(_url: str, **_kwargs):
        return SimpleNamespace(
            group={"id": "123456789", "name": "Nhóm công khai", "url": "https://www.facebook.com/groups/demo",
                   "privacy": "Public group"},
            coverage={"coverage": "partial", "coverage_reason": "tier0_group_shell_only",
                      "history_complete": False, "discussion_posts_collected": False,
                      "http_requests": 2, "group_id": "123456789", "group_name": "Nhóm công khai",
                      "group_privacy": "Public group", "missing_fields": ["discussion_posts", "comments"]},
            engine_version="facebook-cli-fixture-test",
        )

    monkeypatch.setattr(market_research_routes, "dispatch_research_job", no_redis_dispatch)
    monkeypatch.setattr(research_tasks, "SessionLocal", market_api[1])
    monkeypatch.setattr(research_tasks, "settings", SimpleNamespace(facebook_cli_runner_path="/test/runner"))
    monkeypatch.setattr(research_tasks, "_acquire_facebook_cli_lock", acquired_cli_lock)
    monkeypatch.setattr(research_tasks, "_reserve_facebook_request_slot", no_facebook_slot)
    monkeypatch.setattr(research_tasks, "_advance_facebook_request_slot", no_facebook_slot)
    monkeypatch.setattr(research_tasks, "_release_facebook_cli_lock", no_cli_lock_release)
    monkeypatch.setattr(research_tasks, "collect_public_facebook_group", fake_group_collect)

    client, session_factory, _encryption_key = market_api
    workspace_id, headers = _owner(client, "public-group-worker@example.com")
    group_id = _create_group(client, workspace_id, headers)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources",
        headers=headers,
        json={"group_id": group_id, "source_type": "facebook_group", "name": "Public group",
              "url": "https://www.facebook.com/groups/demo"},
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    assert created.json()["status"] == "needs_privacy_policy"
    policy = client.put(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/privacy-policy",
        headers=headers,
        json={
            "purpose": "Đọc metadata nhóm công khai phục vụ nghiên cứu.",
            "processing_basis_reference": "Hồ sơ rà soát nội bộ PRIV-2026-09.",
            "policy_version": "privacy-policy-v1",
            "requested_retention_days": 90,
        },
    )
    assert policy.status_code == 200, policy.text
    accepted = client.post(
        f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/crawl",
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]

    async def run_and_read():
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            assert job is not None
            job.status = "running"
            await db.commit()
        await research_tasks._run(job_id)
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            source = await db.get(ResearchSource, source_id)
            run = await db.scalar(select(WebCrawlRun).where(WebCrawlRun.source_id == source_id))
            evidence = (await db.scalars(select(MarketEvidence).where(
                MarketEvidence.company_id == workspace_id,
                MarketEvidence.source_id == source_id,
            ))).all()
            assert job is not None and source is not None and run is not None
            return job, source, run, evidence

    job, source, run, evidence = asyncio.run(run_and_read())
    assert job.status == "succeeded"
    assert job.result["report_id"] is None
    assert job.result["analysis_status"] == "not_run_no_new_evidence"
    assert job.result["source_results"][0]["status"] == "partial"
    assert job.result["source_results"][0]["group_metadata"]["name"] == "Nhóm công khai"
    assert source.status == "active"
    assert source.collection_status == "partial"
    assert source.last_collection_success_at is None
    assert source.next_due_at is not None
    assert run.status == "partial"
    assert run.counters_json["items_saved"] == 0
    assert run.counters_json["coverage"]["discussion_posts_collected"] is False
    assert run.config_json["discussion_collection"] == "not_attempted_tier0_shell_only"
    assert evidence == []
