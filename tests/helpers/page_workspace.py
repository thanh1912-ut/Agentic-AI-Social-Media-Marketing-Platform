"""Helpers for account registration followed by explicit Page activation."""

from __future__ import annotations

from fastapi.testclient import TestClient


def activate_test_page(client: TestClient, *, page_id: str | None = None) -> dict:
    if page_id is None:
        from services.api import workspaces as workspaces_module
        next_id = getattr(workspaces_module, "_next_test_page_id", None)
        if next_id is None:
            raise AssertionError("fake_page_activation_for_tests fixture is required")
        page_id = next_id()
    response = client.post(
        "/api/v1/workspaces/from-page",
        json={"page_id": page_id, "page_access_token": "test-page-access-token-12345"},
        headers={"X-CSRF-Token": client.cookies.get("agentic_csrf", "")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def attach_workspace_to_session(session: dict, workspace: dict) -> dict:
    return {
        **session,
        "workspaces": [workspace],
        "active_workspace_id": workspace["id"],
    }
