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

    saved = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendations",
        headers=headers,
        json={"source_id": "meta-page-main"},
    )
    assert saved.status_code == 201, saved.text
    saved_data = saved.json()
    assert saved_data["lifecycle_status"] == "new"
    recommendation_id = saved_data["id"]

    repeated_save = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendations",
        headers=headers,
        json={"source_id": "meta-page-main"},
    )
    assert repeated_save.status_code == 201
    assert repeated_save.json()["id"] == recommendation_id

    feedback = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendations/{recommendation_id}/feedback",
        headers=headers,
        json={"value": "useful", "note": "Sẽ thử trên campaign tiếp theo."},
    )
    assert feedback.status_code == 200, feedback.text
    assert feedback.json()["lifecycle_status"] == "acknowledged"
    assert feedback.json()["feedback"]["value"] == "useful"

    applied = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendations/{recommendation_id}/apply",
        headers=headers,
        json={"campaign_id": campaign_id, "evidence_ids": saved_data["recommendation"]["evidence_ids"]},
    )
    assert applied.status_code == 200, applied.text
    draft = applied.json()["created_draft"]
    assert draft["status"] == "pending_review"
    assert draft["base_version"] == 1
    assert applied.json()["notice"]

    campaign_before_accept = client.get(f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}")
    assert campaign_before_accept.status_code == 200
    assert campaign_before_accept.json()["version"] == 1
    assert campaign_before_accept.json()["brief"]["must_include"] == []

    later_measured_at = datetime(2026, 9, 21, 12, tzinfo=timezone.utc).isoformat()
    later_import = client.post(
        f"/api/v1/workspaces/{workspace_id}/metrics/import",
        headers=headers,
        json={"source_id": "meta-page-main", "measured_at": later_measured_at, "points": points},
    )
    assert later_import.status_code == 201, later_import.text
    newer_recommendation = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendations",
        headers=headers,
        json={"source_id": "meta-page-main"},
    )
    assert newer_recommendation.status_code == 201, newer_recommendation.text
    assert newer_recommendation.json()["id"] != recommendation_id
    newer_draft = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendations/{newer_recommendation.json()['id']}/apply",
        headers=headers,
        json={"campaign_id": campaign_id},
    )
    assert newer_draft.status_code == 200, newer_draft.text
    assert newer_draft.json()["created_draft"]["base_version"] == 1

    accepted = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendation-drafts/{draft['id']}/decision",
        headers=headers,
        json={"decision": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    campaign_after_accept = client.get(f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}")
    assert campaign_after_accept.json()["version"] == 2
    assert any("Thử nghiệm recommendation" in item for item in campaign_after_accept.json()["brief"]["must_include"])

    accepted_drafts = client.get(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendation-drafts",
        params={"campaign_id": campaign_id, "source_id": "meta-page-main"},
    )
    assert accepted_drafts.status_code == 200, accepted_drafts.text
    assert [item["id"] for item in accepted_drafts.json()["items"]] == [draft["id"]]

    baseline_at = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    followup_at = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
    for measured_at, reach_value in ((baseline_at, 1000), (followup_at, 1200)):
        recorded = client.post(
            f"/api/v1/workspaces/{workspace_id}/metrics/import",
            headers=headers,
            json={
                "source_id": "meta-page-main",
                "measured_at": measured_at.isoformat(),
                "points": [
                    {"post_id": post_id, "post_age_hours": 168, "reach": reach_value}
                    for ids in post_ids.values()
                    for post_id in ids
                ],
            },
        )
        assert recorded.status_code == 201, recorded.text

    outcome_body = {
        "source_id": "meta-page-main",
        "metric": "reach",
        "baseline_window_from": baseline_at.isoformat(),
        "baseline_window_to": baseline_at.isoformat(),
        "followup_window_from": followup_at.isoformat(),
        "followup_window_to": followup_at.isoformat(),
        "min_post_age_hours": 168,
        "max_post_age_hours": 168,
    }
    outcome_url = f"/api/v1/workspaces/{workspace_id}/analytics/recommendation-drafts/{draft['id']}/outcomes"
    outcome = client.post(outcome_url, headers=headers, json=outcome_body)
    assert outcome.status_code == 201, outcome.text
    outcome_data = outcome.json()
    assert outcome_data["baseline"]["value"] == pytest.approx(1000)
    assert outcome_data["followup"]["value"] == pytest.approx(1200)
    assert outcome_data["absolute_change"] == pytest.approx(200)
    assert outcome_data["relative_change"] == pytest.approx(0.2)
    assert outcome_data["baseline"]["sample_size"] == 10
    assert outcome_data["baseline"]["coverage"] == 1
    assert outcome_data["baseline"]["snapshot_ids"]
    assert outcome_data["baseline"]["evidence_id"].startswith("ev:")
    assert outcome_data["baseline"]["evidence_id"] != outcome_data["followup"]["evidence_id"]
    assert any("không chứng minh" in item for item in outcome_data["limitations"])

    repeated_outcome = client.post(outcome_url, headers=headers, json=outcome_body)
    assert repeated_outcome.status_code == 201
    assert repeated_outcome.json()["id"] == outcome_data["id"]
    stored_outcomes = client.get(outcome_url)
    assert stored_outcomes.status_code == 200, stored_outcomes.text
    assert [item["id"] for item in stored_outcomes.json()["items"]] == [outcome_data["id"]]

    overlapping_windows = {**outcome_body, "followup_window_from": baseline_at.isoformat()}
    invalid_window = client.post(outcome_url, headers=headers, json=overlapping_windows)
    assert invalid_window.status_code == 422
    wrong_source = client.post(
        outcome_url,
        headers=headers,
        json={**outcome_body, "source_id": "another-page"},
    )
    assert wrong_source.status_code == 422

    pending_outcome = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendation-drafts/{newer_draft.json()['created_draft']['id']}/outcomes",
        headers=headers,
        json=outcome_body,
    )
    assert pending_outcome.status_code == 409

    stale_decision = client.post(
        f"/api/v1/workspaces/{workspace_id}/analytics/recommendation-drafts/{newer_draft.json()['created_draft']['id']}/decision",
        headers=headers,
        json={"decision": "accepted"},
    )
    assert stale_decision.status_code == 409
    assert stale_decision.json()["error"]["code"] == "version_conflict"


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
