"""Small real-PostgreSQL API smoke across the existing product modules."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from database.models import (
    Brand,
    BrandProfileRevision,
    CampaignPost,
    Company,
    Document,
    Job,
    KnowledgeChunk,
    MarketEvidence,
    MarketEvidenceVersion,
    MarketObservation,
    MetaPageConnection,
    PostApproval,
    PostMetricSnapshot,
    WebEntity,
)
from services.api import documents as document_routes
from services.api import market_research as market_routes
from services.api import meta_tokens
from services.api.db import SessionLocal, engine
from services.api.main import app
from tests.helpers.page_workspace import activate_test_page
from services.api.meta_client import MetaPage
from services.worker import content_tasks, tasks
from services.worker.model_provider import AIConfigurationError


POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="POSTGRES_TEST_URL is not configured")


class TempStorage:
    def __init__(self, root: Path):
        self.root = root

    async def put(self, key: str, content: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    async def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    async def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)


class FakeMetaGraphClient:
    def __init__(self, page_id: str, token: str, graph_version: str):
        self.page_id = page_id
        self.token = token
        self.graph_version = graph_version

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def verify_page(self) -> MetaPage:
        return MetaPage(id=self.page_id, name="PostgreSQL integration Page")

    async def list_page_posts(self, limit: int = 1) -> SimpleNamespace:
        return SimpleNamespace(posts=[], next_cursor=None)


def test_postgres_api_persists_existing_product_modules(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert POSTGRES_TEST_URL
    assert make_url(POSTGRES_TEST_URL).database == make_url(os.environ["DATABASE_URL"]).database

    encryption_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(meta_tokens, "settings", SimpleNamespace(
        meta_token_encryption_key=encryption_key,
        meta_token_encryption_key_previous="",
    ))
    monkeypatch.setattr(market_routes, "settings", SimpleNamespace(
        meta_graph_version="v26.0",
        meta_public_content_access_token="",
        market_crawl_max_pages=10,
    ))
    monkeypatch.setattr(market_routes, "MetaGraphClient", FakeMetaGraphClient)

    temporary_storage = TempStorage(tmp_path / "objects")
    monkeypatch.setattr(document_routes, "storage", temporary_storage)
    monkeypatch.setattr(tasks, "storage", temporary_storage)
    monkeypatch.setattr(tasks, "configured_embedding_provider", lambda: None)

    def no_deepseek_key():
        raise AIConfigurationError("DEEPSEEK_API_KEY is not configured for this local test.")

    monkeypatch.setattr(content_tasks, "configured_structured_model", no_deepseek_key)

    async def record_document_dispatch(_job_id: str, _document_id: str, _document_ids=None) -> bool:
        return True

    monkeypatch.setattr(document_routes, "dispatch_document_job", record_document_dispatch)

    email = f"postgres-modules-{uuid.uuid4().hex}@example.com"
    page_id = str(10**14 + uuid.uuid4().int % 10**14)
    metric_source = f"manual-page:{page_id}"
    measured_at = datetime.now(timezone.utc).isoformat()

    async def read_persisted_rows():
        async with SessionLocal() as db:
            brand = await db.scalar(select(Brand).where(Brand.company_id == workspace_id))
            revision = await db.scalar(select(BrandProfileRevision).where(
                BrandProfileRevision.company_id == workspace_id,
                BrandProfileRevision.confirmed_at.is_not(None),
            ))
            document = await db.get(Document, document_id)
            document_job = await db.get(Job, job_id)
            chunks = (await db.scalars(select(KnowledgeChunk).where(
                KnowledgeChunk.company_id == workspace_id,
            ))).all()
            connection = await db.get(MetaPageConnection, connection_id)
            post = await db.get(CampaignPost, post_id)
            approval = await db.scalar(select(PostApproval).where(PostApproval.post_id == post_id))
            metric = await db.scalar(select(PostMetricSnapshot).where(PostMetricSnapshot.post_id == post_id))
            evidence = await db.scalar(select(MarketEvidence).where(MarketEvidence.source_id == competitor_id))
            observation = await db.scalar(select(MarketObservation).where(MarketObservation.evidence_id == evidence.id))
            version = await db.get(MarketEvidenceVersion, observation.evidence_version_id)
            return brand, revision, document, document_job, chunks, connection, post, approval, metric, evidence, observation, version

    async def set_page_connection_state(state: str) -> None:
        async with SessionLocal() as db:
            company = await db.get(Company, workspace_id)
            assert company is not None
            company.page_connection_state = state
            connection = await db.get(MetaPageConnection, connection_id)
            assert connection is not None
            connection.status = "verified" if state == "active" else "needs_reconnect"
            await db.commit()

    workspace_id = document_id = job_id = connection_id = post_id = competitor_id = None
    rows = None

    with TestClient(app, base_url="http://127.0.0.1") as client:
        registered = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "postgres-module-smoke-password",
            "full_name": "PostgreSQL module smoke",
            "company_name": f"Integration workspace {uuid.uuid4().hex[:8]}",
        })
        assert registered.status_code == 201, registered.text
        assert registered.json()["workspaces"] == []
        workspace = activate_test_page(client, page_id=page_id)
        workspace_id = workspace["id"]
        assert workspace["name"] == f"Test Page {page_id}"
        assert workspace["page_id"] == page_id
        assert workspace["page_connection_state"] == "active"
        assert workspace["page_avatar_url"] is None

        # Possessing the same Page token is not a workspace invitation.
        second_email = f"postgres-nonmember-{uuid.uuid4().hex}@example.com"
        second_registered = client.post("/api/v1/auth/register", json={
            "email": second_email,
            "password": "postgres-nonmember-smoke-password",
            "full_name": "PostgreSQL non-member",
            "company_name": "Ignored legacy workspace name",
        })
        assert second_registered.status_code == 201, second_registered.text
        assert second_registered.json()["workspaces"] == []
        assert client.get("/api/v1/workspaces").json() == []
        duplicate_page = client.post(
            "/api/v1/workspaces/from-page",
            headers={"X-CSRF-Token": client.cookies["agentic_csrf"]},
            json={"page_id": page_id, "page_access_token": "test-page-access-token-12345"},
        )
        assert duplicate_page.status_code == 409, duplicate_page.text
        assert duplicate_page.json()["error"]["code"] == "page_already_connected"
        assert client.get("/api/v1/workspaces").json() == []
        owner_login = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "postgres-module-smoke-password",
        })
        assert owner_login.status_code == 200, owner_login.text

        headers = {"X-CSRF-Token": client.cookies["agentic_csrf"]}

        profile = client.get(f"/api/v1/workspaces/{workspace_id}/brand-profile")
        assert profile.status_code == 200, profile.text
        confirmed = client.patch(
            f"/api/v1/workspaces/{workspace_id}/brand-profile",
            headers=headers,
            json={
                "version": profile.json()["version"],
                "profile_text": (
                    "PostgreSQL smoke brand sells a fixture product. "
                    "Write clearly for local customers."
                ),
            },
        )
        assert confirmed.status_code == 200, confirmed.text

        group_response = client.get(f"/api/v1/workspaces/{workspace_id}/market-research/groups")
        assert group_response.status_code == 200, group_response.text
        assert group_response.json()
        group_id = group_response.json()[0]["id"]

        connected_pages = client.get(f"/api/v1/workspaces/{workspace_id}/market-research/pages")
        assert connected_pages.status_code == 200, connected_pages.text
        assert len(connected_pages.json()) == 1
        assert connected_pages.json()[0]["page_id"] == page_id
        connection_id = connected_pages.json()[0]["id"]

        competitor = client.post(
            f"/api/v1/workspaces/{workspace_id}/market-research/sources",
            headers=headers,
            json={"group_id": group_id, "source_type": "competitor_facebook_page",
                  "name": "Public competitor fixture", "url": "https://www.facebook.com/pg-test",
                  "competitor_name": "Competitor fixture"},
        )
        assert competitor.status_code == 201, competitor.text
        competitor_id = competitor.json()["id"]
        policy = client.put(
            f"/api/v1/workspaces/{workspace_id}/market-research/sources/{competitor_id}/privacy-policy",
            headers=headers,
            json={
                "purpose": "Integration test with synthetic fixture content only.",
                "processing_basis_reference": "Synthetic data; no personal data is included.",
                "policy_version": "postgres-integration-v1",
                "requested_retention_days": 1,
            },
        )
        assert policy.status_code == 200, policy.text
        assert policy.json()["legal_basis_verified"] is False

        async def reject_invalid_latest_snapshot():
            async with SessionLocal() as db:
                db.add(WebEntity(
                    company_id=workspace_id,
                    group_id=group_id,
                    source_id=competitor_id,
                    kind="article",
                    identity_key=f"invalid-pointer:{uuid.uuid4().hex}",
                    title="Invalid snapshot pointer test",
                    canonical_url="https://www.facebook.com/pg-test/posts/invalid-pointer",
                    latest_snapshot_id=str(uuid.uuid4()),
                ))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()

        assert client.portal is not None
        client.portal.call(reject_invalid_latest_snapshot)
        evidence_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/market-research/sources/{competitor.json()['id']}/import",
            headers=headers,
            json={"rows": [{"url": "https://www.facebook.com/pg-test/posts/1", "title": "Public post",
                            "text": "Public catalog note", "observed_at": measured_at,
                            "metrics": {"reactions": 4, "comments": 2, "shares": 1}, "comments": []}]},
        )
        assert evidence_response.status_code == 201, evidence_response.text

        campaign_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/campaigns",
            headers=headers,
            json={"name": "PostgreSQL content smoke", "group_id": group_id,
                  "brief": {"objective": "engagement", "audience": ["Local customers"],
                            "product_ids": [], "key_message": "Fixture content persists.",
                            "must_include": [], "must_avoid": [], "start_date": "2026-09-27",
                            "end_date": "2026-10-01"},
                  "content_plan": {"strategy_summary": "Manual database smoke", "slots": []},
                  "pillars": ["product"], "channels": ["facebook_page"]},
        )
        assert campaign_response.status_code == 201, campaign_response.text
        campaign_id = campaign_response.json()["id"]
        post_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}/posts",
            headers=headers,
            json={"pillar": "product", "format": "text", "caption": "PostgreSQL persists this draft.",
                  "hashtags": ["#fixture"]},
        )
        assert post_response.status_code == 201, post_response.text
        post_id = post_response.json()["id"]
        submitted = client.post(
            f"/api/v1/workspaces/{workspace_id}/posts/{post_id}/submit-approval",
            headers=headers,
            json={"version": 1},
        )
        assert submitted.status_code == 200, submitted.text
        review = client.post(
            f"/api/v1/workspaces/{workspace_id}/posts/{post_id}/reviews",
            headers=headers,
            json={"version": 1},
        )
        assert review.status_code == 200, review.text
        approved = client.post(
            f"/api/v1/workspaces/{workspace_id}/posts/{post_id}/approval",
            headers=headers,
            json={"version": 1, "decision": "approved"},
        )
        assert approved.status_code == 200, approved.text

        tracking_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}/tracking-ids",
            headers=headers,
            json={"campaign_id": campaign_id, "post_id": post_id, "post_version": 1},
        )
        assert tracking_response.status_code == 201, tracking_response.text
        integration_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/integrations/mailguard", headers=headers,
        )
        assert integration_response.status_code == 200, integration_response.text
        integration_key = integration_response.json()["integration_key"]
        event_auth = {"Authorization": f"Bearer {integration_key}"}
        signup_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=40)
        signup_event = client.post("/api/v1/integrations/mailguard/events", headers=event_auth, json={
            "event_id": f"signup-{uuid.uuid4().hex}", "event_type": "signup_completed",
            "occurred_at": signup_at.isoformat(), "external_user_id": "opaque-pg-user-001",
            "tracking_id": tracking_response.json()["tracking_id"],
        })
        assert signup_event.status_code == 200, signup_event.text
        activation_event = client.post("/api/v1/integrations/mailguard/events", headers=event_auth, json={
            "event_id": f"analysis-{uuid.uuid4().hex}", "event_type": "first_analysis_completed",
            "occurred_at": (signup_at + timedelta(days=5)).isoformat(),
            "external_user_id": "opaque-pg-user-001",
            "tracking_id": tracking_response.json()["tracking_id"],
        })
        assert activation_event.status_code == 200, activation_event.text
        conversion = client.get(
            f"/api/v1/workspaces/{workspace_id}/analytics/conversions",
            params={"window_start": (signup_at - timedelta(days=1)).isoformat(),
                    "window_end": datetime.now(timezone.utc).isoformat()},
        )
        assert conversion.status_code == 200, conversion.text
        assert conversion.json()["signup_count"] == 1
        assert conversion.json()["first_analysis_count"] == 1
        assert conversion.json()["activated_within_window_count"] == 1
        assert conversion.json()["activation_rate"] == 1.0

        scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        schedule_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/meta/publications",
            headers=headers,
            json={"post_id": post_id, "version": 1, "connection_id": connection_id,
                  "scheduled_at": scheduled_at},
        )
        assert schedule_response.status_code == 202, schedule_response.text
        schedules_response = client.get(f"/api/v1/workspaces/{workspace_id}/meta/scheduled-publications")
        assert schedules_response.status_code == 200, schedules_response.text
        scheduled = next(row for row in schedules_response.json() if row["post_id"] == post_id)
        assert scheduled["status"] == "scheduled"
        client.portal.call(set_page_connection_state, "needs_reconnect")
        cancelled = client.post(
            f"/api/v1/workspaces/{workspace_id}/meta/scheduled-publications/{scheduled['id']}/cancel",
            headers=headers,
        )
        client.portal.call(set_page_connection_state, "active")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"

        schedule_setting = client.get(
            f"/api/v1/workspaces/{workspace_id}/meta/pages/{connection_id}/metrics-schedule"
        )
        assert schedule_setting.status_code == 200, schedule_setting.text
        assert schedule_setting.json()["enabled"] is False
        enabled_schedule = client.patch(
            f"/api/v1/workspaces/{workspace_id}/meta/pages/{connection_id}/metrics-schedule",
            headers=headers, json={"enabled": True},
        )
        assert enabled_schedule.status_code == 200, enabled_schedule.text
        assert enabled_schedule.json()["interval_hours"] == 6
        client.portal.call(set_page_connection_state, "needs_reconnect")
        disconnected_schedule = client.get(
            f"/api/v1/workspaces/{workspace_id}/meta/pages/{connection_id}/metrics-schedule"
        )
        assert disconnected_schedule.status_code == 200, disconnected_schedule.text
        assert disconnected_schedule.json()["enabled"] is True
        disabled_schedule = client.patch(
            f"/api/v1/workspaces/{workspace_id}/meta/pages/{connection_id}/metrics-schedule",
            headers=headers, json={"enabled": False},
        )
        assert disabled_schedule.status_code == 200, disabled_schedule.text
        blocked_schedule = client.patch(
            f"/api/v1/workspaces/{workspace_id}/meta/pages/{connection_id}/metrics-schedule",
            headers=headers, json={"enabled": True},
        )
        assert blocked_schedule.status_code == 409, blocked_schedule.text
        assert blocked_schedule.json()["error"]["code"] == "page_needs_reconnect"

        # A lost Page connection blocks re-enabling future metrics sync.
        client.portal.call(set_page_connection_state, "active")

        metric_import = client.post(
            f"/api/v1/workspaces/{workspace_id}/metrics/import",
            headers=headers,
            json={"source_id": metric_source, "measured_at": measured_at, "points": [{
                "post_id": post_id, "post_age_hours": 24, "reach": 100, "views": 120,
                "engagements": 12, "clicks": 5,
            }]},
        )
        assert metric_import.status_code == 201, metric_import.text
        dashboard = client.get(
            f"/api/v1/workspaces/{workspace_id}/analytics/dashboard",
            params={"source_id": metric_source},
        )
        assert dashboard.status_code == 200, dashboard.text
        assert dashboard.json()["report"]["observations"]

        uploaded = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers={**headers, "Idempotency-Key": f"pg-smoke-{uuid.uuid4().hex}"},
            files=[("files", ("pg-smoke.txt", b"A fixture paragraph for durable PostgreSQL knowledge indexing.", "text/plain"))],
        )
        assert uploaded.status_code == 202, uploaded.text
        job_id = uploaded.json()["job_id"]
        document_id = uploaded.json()["job"]["result"]["document_ids"][0]
        assert client.portal is not None
        client.portal.call(tasks.ingest_document_task_batch_async, job_id, [document_id])
        document_response = client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}")
        assert document_response.status_code == 200, document_response.text
        assert document_response.json()["status"] == "ready"
        assert document_response.json()["knowledge_status"] == "ready"
        assert document_response.json()["profile_status"] == "not_applicable"
        rows = client.portal.call(read_persisted_rows)
        # The application's async pool is tied to TestClient's portal loop.
        # Dispose it before that loop closes so later asyncio.run() tests can
        # safely reuse the application engine.
        client.portal.call(engine.dispose)

    assert rows is not None
    brand, revision, document, document_job, chunks, connection, post, approval, metric, evidence, observation, version = rows
    assert brand is not None and revision is not None
    assert document is not None and document_job is not None and document_job.status == "succeeded"
    assert document.status == "ready" and document.knowledge_status == "ready"
    assert document.profile_status == "not_applicable"
    assert document_job.result["profile_status"] == "not_applicable"
    assert chunks and chunks[0].embedding is None
    assert connection is not None and connection.encrypted_token != "fixture-page-token-never-sent-outside-test"
    assert post is not None and post.status == "approved"
    assert approval is not None and len(approval.content_sha256) == 64
    assert metric is not None and metric.reach == 100
    assert evidence is not None and observation is not None and version is not None
