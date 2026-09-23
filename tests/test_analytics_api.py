"""API checks for manual, tenant-scoped metric imports and reporting."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import Base
from services.api.db import get_db
from services.api.main import app


@pytest.fixture
def analytics_api():
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


def _register(client: TestClient, email: str) -> dict:
    response = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "safe-test-password",
        "full_name": "Metrics Owner",
        "company_name": "Metrics workspace",
    })
    assert response.status_code == 201, response.text
    return response.json()


def _campaign_body() -> dict:
    return {
        "name": "Thử nghiệm nội dung",
        "brief": {
            "objective": "engagement",
            "audience": ["Khách hàng địa phương"],
            "key_message": "Thông điệp thử nghiệm",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        "pillars": ["product", "education"],
        "channels": ["facebook_page"],
    }


def test_manual_metrics_are_tenant_scoped_deduplicated_and_evidence_backed(analytics_api) -> None:
    client = analytics_api
    owner = _register(client, "metrics-owner@example.com")
    workspace_id = owner["active_workspace_id"]
    csrf = client.cookies.get("agentic_csrf")
    headers = {"X-CSRF-Token": csrf}
    campaign = client.post(
        f"/api/v1/workspaces/{workspace_id}/campaigns",
        headers=headers,
        json=_campaign_body(),
    )
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["id"]

    post_ids: dict[str, list[str]] = {"product": [], "education": []}
    for pillar in post_ids:
        for number in range(5):
            created = client.post(
                f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}/posts",
                headers=headers,
                json={"pillar": pillar, "format": "text", "caption": f"{pillar} post {number}"},
            )
            assert created.status_code == 201, created.text
            post_ids[pillar].append(created.json()["id"])

    measured_at = datetime(2026, 9, 20, 12, tzinfo=timezone.utc).isoformat()
    points = []
    for pillar, ids in post_ids.items():
        for post_id in ids:
            points.append({
                "post_id": post_id,
                "post_age_hours": 168,
                "reach": 1000,
                "engagements": 120 if pillar == "product" else 60,
                "clicks": None,
            })
    body = {"source_id": "meta-page-main", "measured_at": measured_at, "points": points}
    imported = client.post(f"/api/v1/workspaces/{workspace_id}/metrics/import", headers=headers, json=body)
    assert imported.status_code == 201, imported.text
    assert imported.json()["imported_count"] == 10

    repeated = client.post(
        f"/api/v1/workspaces/{workspace_id}/metrics/import",
        headers=headers,
        json={"source_id": "meta-page-main", "measured_at": measured_at, "points": [points[0]]},
    )
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "duplicate_metric_snapshot"

    dashboard = client.get(
        f"/api/v1/workspaces/{workspace_id}/analytics/dashboard",
        params={"source_id": "meta-page-main", "min_post_age_hours": 168, "max_post_age_hours": 168},
    )
    assert dashboard.status_code == 200, dashboard.text
    data = dashboard.json()
    assert data["source_label"] == "Nhập thủ công"
    assert len(data["report"]["evidence"]) == 6
    pillar_groups = {row["name"]: row for row in data["groups"] if row["dimension"] == "pillar"}
    assert pillar_groups["product"]["post_count"] == 5
    assert pillar_groups["product"]["engagement_rate_by_reach"] == pytest.approx(0.12)
    assert data["report"]["observations"][3]["value"] is None  # missing clicks are not zero

    recommendation = client.get(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendation",
        params={"source_id": "meta-page-main", "min_post_age_hours": 168, "max_post_age_hours": 168},
    )
    assert recommendation.status_code == 200, recommendation.text
    assert recommendation.json()["status"] == "proposed"
    assert recommendation.json()["evidence_ids"]
    assert recommendation.json()["confidence"] < 0.5


def test_recommendation_abstains_for_small_sample_and_tenant_cannot_import_foreign_post(analytics_api) -> None:
    client = analytics_api
    owner = _register(client, "metrics-small@example.com")
    workspace_id = owner["active_workspace_id"]
    other = TestClient(app)
    with other:
        foreign = _register(other, "metrics-foreign@example.com")
        foreign_workspace = foreign["active_workspace_id"]
        campaign = other.post(
            f"/api/v1/workspaces/{foreign_workspace}/campaigns",
            headers={"X-CSRF-Token": other.cookies.get("agentic_csrf")},
            json=_campaign_body(),
        )
        foreign_post = other.post(
            f"/api/v1/workspaces/{foreign_workspace}/campaigns/{campaign.json()['id']}/posts",
            headers={"X-CSRF-Token": other.cookies.get("agentic_csrf")},
            json={"pillar": "product", "caption": "foreign"},
        )

    denied = client.post(
        f"/api/v1/workspaces/{workspace_id}/metrics/import",
        headers={"X-CSRF-Token": client.cookies.get("agentic_csrf")},
        json={
            "source_id": "meta-page-main",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "points": [{"post_id": foreign_post.json()["id"], "post_age_hours": 24, "reach": 100}],
        },
    )
    assert denied.status_code == 404
    recommendation = client.get(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendation",
        params={"source_id": "meta-page-main"},
    )
    assert recommendation.status_code == 200
    assert recommendation.json()["status"] == "abstain"
    assert recommendation.json()["confidence"] == 0
