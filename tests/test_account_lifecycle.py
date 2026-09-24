"""Account email, invitation, and password-reset integration tests."""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.models import Base
from services.api import auth as auth_module
from services.api import email as email_module
from services.api import workspaces as workspaces_module
from services.api.db import get_db
from services.api.email import EmailDeliveryError
from services.api.main import app


@pytest.fixture
def account_client(tmp_path):
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
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def register_owner(client: TestClient, email: str = "owner@example.com") -> tuple[str, str]:
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
    return response.json()["active_workspace_id"], client.cookies["agentic_csrf"]


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
    assert account_client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "old-password-123"},
    ).status_code == 401
    assert account_client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "new-password-456"},
    ).status_code == 200


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
        lambda *_args: pytest.fail("SMTP must not be called when mail is not configured"),
    )
    register_owner(account_client)

    known = account_client.post(
        "/api/v1/auth/forgot-password", json={"email": "owner@example.com"}
    )
    unknown = account_client.post(
        "/api/v1/auth/forgot-password", json={"email": "missing@example.com"}
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert known.json()["accepted"] is True
    assert "đã gửi" not in known.json()["message"].lower()


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
        lambda *_args: pytest.fail("SMTP must not be called when mail is not configured"),
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
    assert created_body["invite_url"].startswith("https://marketing.example.test/invite/")
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
        assert preview.json()["workspace_name"] == "Owner Workspace"
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
