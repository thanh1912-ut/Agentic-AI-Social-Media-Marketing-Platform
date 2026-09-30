"""Account email, invitation, and password-reset integration tests."""

from __future__ import annotations

import asyncio
from itertools import count
import re
from types import SimpleNamespace
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.models import Base, Brand, Company, MetaPageConnection, MetaPageGroup, ResearchSource
from services.api import auth as auth_module
from services.api import email as email_module
from services.api import workspaces as workspaces_module
from services.api.db import get_db
from services.api.email import EmailDeliveryError
from services.api.main import app


_TEST_PAGE_IDS = count(1001)


@pytest.fixture
def account_client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    database_path = tmp_path / "account-lifecycle.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_db():
        async with session_factory() as session:
            yield session

    asyncio.run(create_schema())
    app.dependency_overrides[get_db] = override_db
    app.state.test_session_factory = session_factory

    class FakeMetaClient:
        def __init__(self, page_id, _token, _version):
            self.page_id = page_id

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def verify_page(self):
            from services.api.meta_client import MetaPage
            return MetaPage(id=self.page_id, name=f"Test Page {self.page_id}", picture_url=None)

        async def verify_posts_read_access(self):
            return None

        async def list_page_posts(self, **_kwargs):
            return SimpleNamespace(posts=[], next_cursor=None)

    monkeypatch.setattr(workspaces_module, "MetaGraphClient", FakeMetaClient)
    monkeypatch.setattr(workspaces_module, "encrypt_page_token", lambda token: f"test-encrypted:{len(token)}")
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        del app.state.test_session_factory
        asyncio.run(engine.dispose())


def register_owner(
    client: TestClient, email: str = "owner@example.com"
) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "old-password-123",
            "full_name": "Workspace Owner",
            "company_name": "Owner Workspace",
        },
    )
    assert response.status_code == 201, response.text
    page_id = str(next(_TEST_PAGE_IDS))
    connected = client.post(
        "/api/v1/workspaces/from-page",
        json={"page_id": page_id, "page_access_token": "test-page-token-value-12345"},
        headers={"X-CSRF-Token": client.cookies["agentic_csrf"]},
    )
    assert connected.status_code == 201, connected.text
    return connected.json()["id"], client.cookies["agentic_csrf"]


def test_register_creates_user_only_and_preserves_password_exactly(
    account_client: TestClient,
) -> None:
    password = "  spaced-password-123  "
    registered = account_client.post(
        "/api/v1/auth/register",
        json={
            "email": "New.Owner@Example.com",
            "password": password,
            "full_name": "New Owner",
            "company_name": "New Brand",
        },
    )
    assert registered.status_code == 201, registered.text
    assert registered.json()["user"]["email"] == "new.owner@example.com"
    assert registered.json()["workspaces"] == []
    assert registered.json()["active_workspace_id"] is None
    assert account_client.get("/api/v1/workspaces").json() == []
    assert account_client.get("/api/v1/me").status_code == 200

    duplicate = account_client.post(
        "/api/v1/auth/register",
        json={
            "email": "new.owner@example.com",
            "password": "another-password-123",
            "full_name": "Another Owner",
            "company_name": "Another Workspace",
        },
    )
    assert duplicate.status_code == 409
    assert account_client.get("/api/v1/workspaces").json() == []

    logout = account_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": account_client.cookies["agentic_csrf"]},
    )
    assert logout.status_code == 204
    rejected_trimmed = account_client.post(
        "/api/v1/auth/login",
        json={"email": "NEW.OWNER@example.com", "password": password.strip()},
    )
    assert rejected_trimmed.status_code == 401
    login = account_client.post(
        "/api/v1/auth/login",
        json={"email": "NEW.OWNER@example.com", "password": password},
    )
    assert login.status_code == 200, login.text
    assert login.json()["active_workspace_id"] is None


def test_page_activation_owns_workspace_and_token_does_not_grant_membership(
    account_client: TestClient,
) -> None:
    first = account_client.post("/api/v1/auth/register", json={
        "email": "page-owner@example.com", "password": "safe-password-123",
        "full_name": "Page Owner",
    })
    assert first.status_code == 201
    page_id = "881234567890"
    activated = account_client.post(
        "/api/v1/workspaces/from-page",
        json={"page_id": page_id, "page_access_token": "test-page-token-value-12345"},
        headers={"X-CSRF-Token": account_client.cookies["agentic_csrf"]},
    )
    assert activated.status_code == 201, activated.text
    workspace = activated.json()
    assert workspace["name"] == f"Test Page {page_id}"
    assert workspace["page_id"] == page_id
    assert workspace["page_connection_state"] == "active"
    assert workspace["role"] == "owner"
    assert account_client.get("/api/v1/workspaces").json()[0]["id"] == workspace["id"]

    account_client.cookies.clear()
    second = account_client.post("/api/v1/auth/register", json={
        "email": "second-page-user@example.com", "password": "safe-password-456",
        "full_name": "Second User",
    })
    assert second.status_code == 201
    conflict = account_client.post(
        "/api/v1/workspaces/from-page",
        json={"page_id": page_id, "page_access_token": "test-page-token-value-12345"},
        headers={"X-CSRF-Token": account_client.cookies["agentic_csrf"]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "page_already_connected"
    assert account_client.get("/api/v1/workspaces").json() == []


@pytest.mark.parametrize(("step", "failure", "expected_code", "status"), [
    ("token_identity", "mismatch", "meta_page_identity_mismatch", 422),
    ("token_identity", "type", "meta_page_type_unverified", 422),
    ("token_identity", "expired", "meta_token_invalid", 422),
    ("token_identity", "rejected", "meta_page_identity_rejected", 422),
    ("posts_read_access", "rejected", "meta_page_permission_missing", 422),
    ("posts_read_access", "rate", "meta_rate_limited", 429),
    ("posts_read_access", "read", "meta_verification_failed", 502),
])
@pytest.mark.parametrize("reconnect", [False, True])
def test_page_verification_reports_step_and_safe_codes_without_changing_binding(
    account_client, monkeypatch, caplog, step, failure, expected_code, status, reconnect,
):
    from services.api.meta_client import (
        MetaGraphReadError, MetaGraphRejected, MetaGraphTokenExpired, MetaPage, MetaPageIdentityMismatch, MetaPageTypeUnverified,
    )

    if reconnect:
        workspace_id, csrf = register_owner(account_client, "verification-owner@example.com")
        original = account_client.get(f"/api/v1/workspaces/{workspace_id}").json()
        page_id = original["page_id"]
        endpoint = f"/api/v1/workspaces/{workspace_id}/page-connection"
        method = account_client.patch
    else:
        response = account_client.post("/api/v1/auth/register", json={
            "email": "verification-new@example.com", "password": "synthetic-password-123", "full_name": "Verification Owner",
        })
        assert response.status_code == 201
        csrf = account_client.cookies["agentic_csrf"]
        page_id = "123"
        endpoint, method = "/api/v1/workspaces/from-page", account_client.post

    failures = {
        "mismatch": MetaPageIdentityMismatch(403), "expired": MetaGraphTokenExpired(400, 190, 463),
        "type": MetaPageTypeUnverified(403),
        "rejected": MetaGraphRejected(400, 10, 33), "rate": MetaGraphRejected(429, 4),
        "read": MetaGraphReadError("Synthetic response unavailable"),
    }

    class FailingClient:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def verify_page(self):
            if step == "token_identity":
                raise failures[failure]
            return MetaPage(id=page_id, name="Verified identity fixture")

        async def verify_posts_read_access(self):
            raise failures[failure]

    monkeypatch.setattr(workspaces_module, "MetaGraphClient", FailingClient)
    token = "synthetic-secret-token-must-never-appear"
    response = method(endpoint, headers={"X-CSRF-Token": csrf}, json={"page_id": page_id, "page_access_token": token})
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == expected_code
    assert error["details"]["verification_step"] == step
    assert error["retryable"] is (failure in {"rate", "read"})
    assert token not in response.text and token not in caplog.text
    assert error["request_id"] in caplog.text
    assert step in caplog.text
    if failure == "rejected":
        assert error["details"]["meta_code"] == 10
        assert error["details"]["meta_subcode"] == 33
    if failure in {"mismatch", "type"}:
        assert "meta_http_status" not in error["details"]  # Local identity check, not an upstream 403.
    if reconnect:
        assert account_client.get(f"/api/v1/workspaces/{workspace_id}").json() == original
    else:
        assert account_client.get("/api/v1/workspaces").json() == []


def test_refresh_page_metadata_uses_stored_token_without_touching_brand(
    account_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.api.meta_client import MetaPage

    workspace_id, csrf = register_owner(account_client, "metadata-refresh@example.com")
    stored_token: list[str] = []
    list_calls: list[int] = []

    class RefreshedMetaClient:
        def __init__(self, page_id, token, _version):
            self.page_id = page_id
            stored_token.append(token)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def verify_page(self):
            return MetaPage(
                id=self.page_id,
                name="Tên Fanpage mới",
                picture_url="https://cdn.example.test/page-avatar.png",
            )

        async def verify_posts_read_access(self):
            list_calls.append(1)
            return None

    monkeypatch.setattr(workspaces_module, "decrypt_page_token", lambda _value: "stored-page-token")
    monkeypatch.setattr(workspaces_module, "MetaGraphClient", RefreshedMetaClient)

    async def seed_brand_profile() -> None:
        async with account_client.app.state.test_session_factory() as db:
            company = await db.get(Company, workspace_id)
            brand = await db.scalar(select(Brand).where(Brand.company_id == workspace_id))
            connection = await db.scalar(select(MetaPageConnection).where(
                MetaPageConnection.company_id == workspace_id,
            ))
            source = await db.scalar(select(ResearchSource).where(
                ResearchSource.company_id == workspace_id,
                ResearchSource.source_type == "owned_facebook_page",
            ))
            assert company is not None and brand is not None and connection is not None and source is not None
            brand.profile = {"profile_text": "Hồ sơ do Owner tự viết."}
            brand.version = 4
            await db.commit()

    asyncio.run(seed_brand_profile())
    response = account_client.post(
        f"/api/v1/workspaces/{workspace_id}/page-connection/refresh-metadata",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Tên Fanpage mới"
    assert response.json()["page_avatar_url"] == "https://cdn.example.test/page-avatar.png"
    assert "stored-page-token" not in response.text
    assert stored_token == ["stored-page-token"]
    assert list_calls == [1]

    async def read_saved_identity():
        async with account_client.app.state.test_session_factory() as db:
            company = await db.get(Company, workspace_id)
            brand = await db.scalar(select(Brand).where(Brand.company_id == workspace_id))
            connection = await db.scalar(select(MetaPageConnection).where(
                MetaPageConnection.company_id == workspace_id,
            ))
            source = await db.scalar(select(ResearchSource).where(
                ResearchSource.company_id == workspace_id,
                ResearchSource.source_type == "owned_facebook_page",
            ))
            assert company is not None and brand is not None and connection is not None and source is not None
            return company.name, company.page_avatar_url, connection.page_name, source.name, brand.profile, brand.version

    assert asyncio.run(read_saved_identity()) == (
        "Tên Fanpage mới", "https://cdn.example.test/page-avatar.png",
        "Tên Fanpage mới", "Tên Fanpage mới", {"profile_text": "Hồ sơ do Owner tự viết."}, 4,
    )


def test_metadata_refresh_expired_token_pauses_page_work_but_keeps_workspace(
    account_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.api.meta_client import MetaGraphTokenExpired, MetaPage
    from database.models import utcnow

    workspace_id, csrf = register_owner(account_client, "metadata-expired@example.com")
    monkeypatch.setattr(workspaces_module, "decrypt_page_token", lambda _value: "stored-page-token")

    class ExpiredMetaClient:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def verify_page(self):
            raise MetaGraphTokenExpired(401, 190)

    monkeypatch.setattr(workspaces_module, "MetaGraphClient", ExpiredMetaClient)

    async def enable_test_schedules() -> None:
        async with account_client.app.state.test_session_factory() as db:
            connection = await db.scalar(select(MetaPageConnection).where(
                MetaPageConnection.company_id == workspace_id,
            ))
            source = await db.scalar(select(ResearchSource).where(
                ResearchSource.company_id == workspace_id,
                ResearchSource.source_type == "owned_facebook_page",
            ))
            assert connection is not None and source is not None
            connection.metrics_schedule_enabled = True
            connection.next_metrics_sync_at = utcnow()
            source.schedule_enabled = True
            source.next_due_at = utcnow()
            await db.commit()

    asyncio.run(enable_test_schedules())
    response = account_client.post(
        f"/api/v1/workspaces/{workspace_id}/page-connection/refresh-metadata",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "page_needs_reconnect"

    async def read_paused_state():
        async with account_client.app.state.test_session_factory() as db:
            company = await db.get(Company, workspace_id)
            connection = await db.scalar(select(MetaPageConnection).where(
                MetaPageConnection.company_id == workspace_id,
            ))
            source = await db.scalar(select(ResearchSource).where(
                ResearchSource.company_id == workspace_id,
                ResearchSource.source_type == "owned_facebook_page",
            ))
            assert company is not None and connection is not None and source is not None
            return (
                company.page_id,
                company.name,
                company.page_connection_state,
                connection.status,
                connection.metrics_schedule_enabled,
                connection.next_metrics_sync_at,
                source.schedule_enabled,
                source.next_due_at,
            )

    saved = asyncio.run(read_paused_state())
    assert saved[1].startswith("Test Page ")
    assert saved[2:5] == ("needs_reconnect", "needs_reconnect", True)
    assert saved[5] is None
    assert saved[6:] == (True, None)

    class ReconnectedMetaClient:
        def __init__(self, page_id, *_args):
            self.page_id = page_id

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def verify_page(self):
            return MetaPage(id=self.page_id, name="Page sau kết nối lại", picture_url=None)

        async def verify_posts_read_access(self):
            return None

        async def list_page_posts(self, **_kwargs):
            return SimpleNamespace(posts=[], next_cursor=None)

    monkeypatch.setattr(workspaces_module, "MetaGraphClient", ReconnectedMetaClient)
    reconnected = account_client.patch(
        f"/api/v1/workspaces/{workspace_id}/page-connection",
        headers={"X-CSRF-Token": csrf},
        json={"page_id": saved[0], "page_access_token": "new-page-token-for-the-same-page"},
    )
    assert reconnected.status_code == 200, reconnected.text
    assert reconnected.json()["page_connection_state"] == "active"

    async def read_restored_schedules():
        async with account_client.app.state.test_session_factory() as db:
            connection = await db.scalar(select(MetaPageConnection).where(
                MetaPageConnection.company_id == workspace_id,
            ))
            group = await db.scalar(select(MetaPageGroup).where(
                MetaPageGroup.company_id == workspace_id,
                MetaPageGroup.active.is_(True),
            ))
            source = await db.scalar(select(ResearchSource).where(
                ResearchSource.company_id == workspace_id,
                ResearchSource.source_type == "owned_facebook_page",
            ))
            assert connection is not None and group is not None and source is not None
            return (
                connection.metrics_schedule_enabled,
                connection.next_metrics_sync_at,
                source.schedule_enabled,
                source.next_due_at,
                group.next_due_at,
            )

    restored = asyncio.run(read_restored_schedules())
    assert restored[0] is True and restored[1] is not None
    assert restored[2] is True and restored[3] is not None
    assert restored[4] == restored[3]


def test_legacy_workspace_requires_page_before_agentic_writes(account_client: TestClient) -> None:
    from database.models import Brand, Company, Membership, new_id

    registered = account_client.post("/api/v1/auth/register", json={
        "email": "legacy-workspace-owner@example.com",
        "password": "safe-password-789",
        "full_name": "Legacy Owner",
    })
    assert registered.status_code == 201
    user_id = registered.json()["user"]["id"]
    company_id = new_id()

    async def create_legacy_workspace():
        async with account_client.app.state.test_session_factory() as db:
            db.add(Company(id=company_id, name="Legacy workspace", slug=f"legacy-{company_id[:8]}"))
            db.add(Membership(company_id=company_id, user_id=user_id, role="owner", is_active=True))
            db.add(Brand(company_id=company_id, profile={}, version=1))
            await db.commit()

    asyncio.run(create_legacy_workspace())
    response = account_client.patch(
        f"/api/v1/workspaces/{company_id}/brand-profile",
        headers={"X-CSRF-Token": account_client.cookies["agentic_csrf"]},
        json={"version": 1, "profile_text": "Không được ghi trước khi Page hợp lệ."},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "page_connection_required"


def test_existing_invitee_must_sign_in_as_invited_account(
    account_client: TestClient,
) -> None:
    invited_workspace, _ = register_owner(account_client, "owner@example.com")
    inviter_workspace, inviter_csrf = register_owner(
        account_client, "inviter@example.com"
    )
    invitation = account_client.post(
        f"/api/v1/workspaces/{inviter_workspace}/members",
        json={"email": "owner@example.com", "role": "editor"},
        headers={"X-CSRF-Token": inviter_csrf},
    )
    assert invitation.status_code == 201, invitation.text
    token = urlsplit(invitation.json()["invite_url"]).path.rsplit("/", 1)[1]

    account_client.cookies.clear()
    unsigned = account_client.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"email": "owner@example.com"},
    )
    assert unsigned.status_code == 401
    assert unsigned.json()["error"]["code"] == "invitation_sign_in_required"

    wrong_account = account_client.post(
        "/api/v1/auth/login",
        json={"email": "inviter@example.com", "password": "old-password-123"},
    )
    assert wrong_account.status_code == 200
    rejected_wrong_account = account_client.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"email": "owner@example.com"},
        headers={"X-CSRF-Token": account_client.cookies["agentic_csrf"]},
    )
    assert rejected_wrong_account.status_code == 403
    assert (
        rejected_wrong_account.json()["error"]["code"] == "invitation_account_mismatch"
    )

    signed_in = account_client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "old-password-123"},
    )
    assert signed_in.status_code == 200
    accepted = account_client.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"email": "owner@example.com"},
        headers={"X-CSRF-Token": account_client.cookies["agentic_csrf"]},
    )
    assert accepted.status_code == 200, accepted.text
    workspaces = {
        workspace["id"]: workspace for workspace in accepted.json()["workspaces"]
    }
    assert workspaces[invited_workspace]["role"] == "owner"
    assert workspaces[inviter_workspace]["role"] == "editor"


def test_password_reset_sends_one_time_link_and_revokes_refresh_sessions(
    account_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_messages: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        auth_module,
        "settings",
        replace(
            auth_module.settings,
            smtp_host="smtp.example.test",
            email_from="no-reply@example.com",
            web_base_url="https://marketing.example.test",
        ),
    )

    def capture_email(to: str, subject: str, body: str) -> None:
        sent_messages.append((to, subject, body))

    monkeypatch.setattr(auth_module, "send_email", capture_email)
    register_owner(account_client)

    response = account_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "owner@example.com"},
    )
    second_request = account_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "owner@example.com"},
    )
    assert response.status_code == 200
    assert second_request.status_code == 200
    assert response.json()["accepted"] is True
    assert "owner@example.com" not in response.text
    assert len(sent_messages) == 2
    recipient, subject, body = sent_messages[1]
    assert recipient == "owner@example.com"
    assert "Đặt lại mật khẩu" in subject
    reset_url = re.search(r"https://\S+", body).group(0)
    token = parse_qs(urlsplit(reset_url).query)["token"][0]
    stale_reset_url = re.search(r"https://\S+", sent_messages[0][2]).group(0)
    stale_token = parse_qs(urlsplit(stale_reset_url).query)["token"][0]
    assert token not in response.text

    reset = account_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "new-password-456"},
    )
    assert reset.status_code == 200
    assert reset.json() == {"ok": True}
    assert account_client.get("/api/v1/me").status_code == 401
    old_refresh = account_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": account_client.cookies["agentic_csrf"]},
    )
    assert old_refresh.status_code == 401
    replay = account_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "another-password-789"},
    )
    assert replay.status_code == 400
    stale_reset = account_client.post(
        "/api/v1/auth/reset-password",
        json={"token": stale_token, "new_password": "stale-password-789"},
    )
    assert stale_reset.status_code == 400
    assert (
        account_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "old-password-123"},
        ).status_code
        == 401
    )
    assert (
        account_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "new-password-456"},
        ).status_code
        == 200
    )


def test_forgot_password_is_neutral_without_smtp_and_does_not_claim_delivery(
    account_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth_module,
        "settings",
        replace(auth_module.settings, smtp_host="", email_from=""),
    )
    monkeypatch.setattr(
        auth_module,
        "send_email",
        lambda *_args: pytest.fail(
            "SMTP must not be called when mail is not configured"
        ),
    )
    register_owner(account_client)

    known = account_client.post(
        "/api/v1/auth/forgot-password", json={"email": "owner@example.com"}
    )
    unknown = account_client.post(
        "/api/v1/auth/forgot-password", json={"email": "missing@example.com"}
    )
    assert known.status_code == unknown.status_code == 503
    assert known.json()["error"]["code"] == "password_reset_unavailable"
    assert "smtp" not in known.text.lower()


def test_smtp_failure_keeps_forgot_password_response_neutral(
    account_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_body: list[str] = []
    monkeypatch.setattr(
        auth_module,
        "settings",
        replace(
            auth_module.settings,
            smtp_host="smtp.example.test",
            email_from="no-reply@example.com",
            web_base_url="https://marketing.example.test",
        ),
    )

    def reject_email(_to: str, _subject: str, body: str) -> None:
        captured_body.append(body)
        raise EmailDeliveryError("private smtp diagnostic")

    monkeypatch.setattr(auth_module, "send_email", reject_email)
    register_owner(account_client)
    response = account_client.post(
        "/api/v1/auth/forgot-password", json={"email": "owner@example.com"}
    )
    assert response.status_code == 200
    assert "private smtp diagnostic" not in response.text
    assert captured_body
    assert "token" not in response.text


def test_invitation_manual_fallback_resend_and_acceptance(
    account_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id, csrf_token = register_owner(account_client)
    monkeypatch.setattr(
        workspaces_module,
        "settings",
        replace(
            workspaces_module.settings,
            smtp_host="",
            email_from="",
            web_base_url="https://marketing.example.test",
        ),
    )
    monkeypatch.setattr(
        workspaces_module,
        "send_email",
        lambda *_args: pytest.fail(
            "SMTP must not be called when mail is not configured"
        ),
    )
    headers = {"X-CSRF-Token": csrf_token}
    created = account_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "editor@example.com", "role": "editor"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    created_body = created.json()
    assert created_body["outcome"] == "email_failed"
    assert created_body["invite_url"].startswith(
        "https://marketing.example.test/invite/"
    )
    old_token = urlsplit(created_body["invite_url"]).path.rsplit("/", 1)[1]
    member_id = created_body["member"]["id"]
    duplicate = account_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "editor@example.com", "role": "editor"},
        headers=headers,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["outcome"] == "already_invited"
    assert duplicate.json()["member"]["id"] == member_id

    # Re-inviting an expired pending address rotates the existing record/token
    # instead of creating duplicate pending rows.
    monkeypatch.setattr(workspaces_module, "is_expired", lambda _expires_at: True)
    renewed = account_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "editor@example.com", "role": "viewer"},
        headers=headers,
    )
    assert renewed.status_code == 201
    assert renewed.json()["outcome"] == "email_failed"
    assert renewed.json()["member"]["id"] == member_id
    renewed_token = urlsplit(renewed.json()["invite_url"]).path.rsplit("/", 1)[1]
    assert renewed_token != old_token
    assert renewed.json()["member"]["role"] == "viewer"
    monkeypatch.setattr(workspaces_module, "is_expired", lambda _expires_at: False)

    delivered: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        workspaces_module,
        "settings",
        replace(
            workspaces_module.settings,
            smtp_host="smtp.example.test",
            email_from="no-reply@example.com",
            web_base_url="https://marketing.example.test",
        ),
    )
    monkeypatch.setattr(
        workspaces_module,
        "send_email",
        lambda to, subject, body: delivered.append((to, subject, body)),
    )
    resent = account_client.post(
        f"/api/v1/workspaces/{workspace_id}/members/{member_id}/resend-invitation",
        headers=headers,
    )
    assert resent.status_code == 200, resent.text
    assert resent.json()["outcome"] == "sent"
    assert resent.json()["invite_url"] is None
    assert len(delivered) == 1
    new_url = re.search(r"https://\S+", delivered[0][2]).group(0)
    new_token = urlsplit(new_url).path.rsplit("/", 1)[1]
    assert new_token != renewed_token

    invitee = TestClient(app)
    with invitee:
        stale_preview = invitee.get(f"/api/v1/auth/invitations/{renewed_token}")
        assert stale_preview.status_code == 404
        preview = invitee.get(f"/api/v1/auth/invitations/{new_token}")
        assert preview.status_code == 200
        assert preview.headers["cache-control"] == "no-store"
        assert preview.headers["referrer-policy"] == "no-referrer"
        assert preview.json()["workspace_name"].startswith("Test Page ")
        assert preview.json()["role"] == "viewer"

        accepted = invitee.post(
            f"/api/v1/auth/invitations/{new_token}/accept",
            json={
                "email": "editor@example.com",
                "full_name": "Workspace Editor",
                "password": "editor-password-123",
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["workspaces"][0]["role"] == "viewer"
        assert invitee.get("/api/v1/me").status_code == 200


def test_smtp_adapter_uses_starttls_and_keeps_credentials_out_of_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            events.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def starttls(self, *, context) -> None:
            events.append(("starttls", context.protocol))

        def login(self, username: str, password: str) -> None:
            events.append(("login", username, password))

        def send_message(self, message) -> None:
            events.append(message)

    monkeypatch.setattr(
        email_module,
        "settings",
        replace(
            email_module.settings,
            smtp_host="smtp.example.test",
            smtp_port=587,
            smtp_username="mailer-user",
            smtp_password="mailer-password",
            smtp_starttls=True,
            smtp_ssl=False,
            smtp_timeout_seconds=7,
            email_from="no-reply@example.com",
        ),
    )
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)

    email_module.send_email(
        "member@example.com",
        "Workspace invitation\r\nBcc: attacker@example.net",
        "Open the invite link.",
    )

    assert events[0] == ("smtp.example.test", 587, 7)
    assert events[1][0] == "starttls"
    assert events[2] == ("login", "mailer-user", "mailer-password")
    message = events[3]
    assert message["To"] == "member@example.com"
    assert message["From"] == "no-reply@example.com"
    assert message["Subject"] == "Workspace invitation Bcc: attacker@example.net"
    assert message.get_all("Bcc") is None
    assert "mailer-password" not in message.as_string()
