"""FastAPI dependencies for authentication and tenant isolation."""

from __future__ import annotations

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Membership, User
from .db import get_db
from .errors import ApiProblem
from .permissions import has_permission
from .security import decode_access_token


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
    # Bearer clients are not exposed to cookie CSRF. Browser clients use the
    # access cookie and must echo the readable CSRF cookie on mutations.
    if request.headers.get("Authorization"):
        return
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.cookies.get(ACCESS_COOKIE):
        expected = request.cookies.get(CSRF_COOKIE)
        received = request.headers.get(CSRF_HEADER)
        if not expected or not received or expected != received:
            raise ApiProblem(403, "csrf_failed", "Yêu cầu không hợp lệ. Hãy tải lại trang rồi thử lại.")
