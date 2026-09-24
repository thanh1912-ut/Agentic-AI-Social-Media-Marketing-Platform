"""FastAPI dependencies for authentication and tenant isolation."""

from __future__ import annotations

from datetime import timezone

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Membership, User
from .db import get_db
from .errors import ApiProblem
from .permissions import has_permission
from .security import decode_access_token, password_version


ACCESS_COOKIE = "agentic_access"
REFRESH_COOKIE = "agentic_refresh"
CSRF_COOKIE = "agentic_csrf"
CSRF_HEADER = "X-CSRF-Token"


async def current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User:
    encoded = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            encoded = value
    if encoded is None:
        encoded = request.cookies.get(ACCESS_COOKIE)
    if not encoded:
        raise ApiProblem(401, "unauthenticated", "Bạn chưa đăng nhập hoặc phiên làm việc đã hết hạn.")
    try:
        claims = decode_access_token(encoded)
    except jwt.PyJWTError:
        raise ApiProblem(401, "session_expired", "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.")
    user = await db.get(User, str(claims["sub"]))
    if user is None or not user.is_active:
        raise ApiProblem(401, "unauthenticated", "Tài khoản không còn hoạt động.")
    issued_password_version = claims.get("password_version")
    if issued_password_version is not None:
        stale_password = issued_password_version != password_version(user)
    else:
        # Tokens issued before password-version claims were introduced remain
        # compatible until expiry, but a password reset still rejects older
        # tokens when their second-resolution `iat` predates the password change.
        changed_at = user.password_changed_at
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        issued_at = claims.get("iat")
        stale_password = not isinstance(issued_at, (int, float)) or issued_at < int(changed_at.timestamp())
    if stale_password:
        raise ApiProblem(401, "session_expired", "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.")
    return user


async def membership_for(
    company_id: str,
    user: User,
    db: AsyncSession,
) -> Membership:
    membership = await db.scalar(
        select(Membership).where(
            Membership.company_id == company_id,
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
        )
    )
    # 404 prevents a user from learning that another tenant's resource exists.
    if membership is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy doanh nghiệp.")
    return membership


def require_permission(permission: str):
    async def dependency(
        company_id: str,
        user: User = Depends(current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Membership:
        membership = await membership_for(company_id, user, db)
        if not has_permission(membership.role, permission):
            raise ApiProblem(
                403,
                "forbidden",
                "Bạn không có quyền thực hiện thao tác này.",
                details={
                    "required_permission": permission,
                    "required_role": "owner" if permission in {"member:invite", "brand:confirm", "connection:manage", "publish:create"} else None,
                },
            )
        return membership

    return dependency


async def require_csrf(request: Request) -> None:
    # Bearer-only clients are not exposed to cookie CSRF. If either session
    # cookie is present, browser mutations must echo the readable CSRF cookie.
    has_cookie_session = bool(
        request.cookies.get(ACCESS_COOKIE) or request.cookies.get(REFRESH_COOKIE)
    )
    if request.headers.get("Authorization") and not has_cookie_session:
        return
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and has_cookie_session:
        expected = request.cookies.get(CSRF_COOKIE)
        received = request.headers.get(CSRF_HEADER)
        if not expected or not received or expected != received:
            raise ApiProblem(403, "csrf_failed", "Yêu cầu không hợp lệ. Hãy tải lại trang rồi thử lại.")
