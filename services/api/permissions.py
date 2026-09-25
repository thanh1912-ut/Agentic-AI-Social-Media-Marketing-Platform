"""Backend-owned role and permission matrix."""

from __future__ import annotations

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            "workspace:manage",
            "member:invite",
            "brand:edit",
            "brand:confirm",
            "document:upload",
            "campaign:create",
            "campaign:edit",
            "post:edit",
            "post:generate",
            "post:approve",
            "post:reject",
            "export:create",
            "connection:manage",
            "market:manage",
            "publish:create",
            "metric:import",
            "recommendation:apply",
        }
    ),
    "editor": frozenset(
        {
            "brand:edit",
            "document:upload",
            "campaign:create",
            "campaign:edit",
            "post:edit",
            "post:generate",
            "export:create",
            "metric:import",
            "market:manage",
        }
    ),
    "viewer": frozenset(),
}


def permissions_for(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, frozenset()))


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
