"""Authentication and invitation lifecycle endpoints."""

from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Brand, Company, Invitation, Membership, PasswordResetToken, RefreshSession, User, utcnow
from .config import settings
from .db import get_db
from .dependencies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE, require_csrf
from .errors import ApiProblem
from .permissions import permissions_for
from .schemas import (
    ForgotPasswordRequest,
    AcceptInvitationRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionResponse,
    UserOut,
    WorkspaceOut,
)
from .security import create_access_token, hash_password, is_expired, new_opaque_token, token_hash, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip()).strip("-") or "workspace"
    return slug


async def _workspace_rows(db: AsyncSession, user_id: str) -> list[tuple[Company, Membership]]:
    result = await db.execute(
        select(Company, Membership)
        .join(Membership, Membership.company_id == Company.id)
        .where(Membership.user_id == user_id, Membership.is_active.is_(True))
        .order_by(Company.created_at)
    )
    return list(result.all())


def _workspace_out(company: Company, membership: Membership) -> WorkspaceOut:
    return WorkspaceOut(
        id=company.id,
        name=company.name,
        slug=company.slug,
        industry=company.industry,
        role=membership.role,
        permissions=permissions_for(membership.role),
        created_at=company.created_at,
    )


async def _issue_session(
    response: Response,
    db: AsyncSession,
    user: User,
    request: Request | None = None,
) -> tuple[str, object]:
    access_token, expires_at = create_access_token(user)
    refresh_token = new_opaque_token()
    db.add(
        RefreshSession(
            user_id=user.id,
            token_hash=token_hash(refresh_token),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
            user_agent=request.headers.get("user-agent") if request else None,
            ip_address=request.client.host if request and request.client else None,
        )
    )
    await db.flush()
    csrf_token = new_opaque_token()
    cookie_args = {
        "secure": settings.cookie_secure,
        "httponly": True,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain,
        "path": "/",
    }
    response.set_cookie(ACCESS_COOKIE, access_token, max_age=settings.access_token_expire_minutes * 60, **cookie_args)
    response.set_cookie(REFRESH_COOKIE, refresh_token, max_age=settings.refresh_token_expire_days * 86400, **cookie_args)
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=settings.refresh_token_expire_days * 86400, httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_samesite, domain=settings.cookie_domain, path="/")
    return access_token, expires_at


async def _session_response(db: AsyncSession, user: User, access_token: str, expires_at: object) -> LoginResponse:
    workspaces = [_workspace_out(company, membership) for company, membership in await _workspace_rows(db, user.id)]
    return LoginResponse(
        user=UserOut.model_validate(user, from_attributes=True),
        workspaces=workspaces,
        active_workspace_id=workspaces[0].id if workspaces else None,
        access_token=access_token,
        expires_at=expires_at,
    )


@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise ApiProblem(409, "already_exists", "Email này đã được đăng ký.")
    slug = _slugify(payload.company_name)
    if await db.scalar(select(Company).where(Company.slug == slug)):
        slug = f"{slug}-{new_opaque_token()[:6].lower()}"
    user = User(email=email, full_name=payload.full_name, password_hash=hash_password(payload.password))
    company = Company(name=payload.company_name, slug=slug, industry=payload.industry)
    db.add_all([user, company])
    await db.flush()
    db.add_all([Membership(company_id=company.id, user_id=user.id, role="owner"), Brand(company_id=company.id, profile={})])
    access_token, expires_at = await _issue_session(response, db, user, request)
    await db.commit()
    return await _session_response(db, user, access_token, expires_at)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise ApiProblem(401, "unauthenticated", "Email hoặc mật khẩu không đúng. Vui lòng kiểm tra lại.")
    access_token, expires_at = await _issue_session(response, db, user, request)
    await db.commit()
    return await _session_response(db, user, access_token, expires_at)


@router.post("/refresh", response_model=LoginResponse, dependencies=[Depends(require_csrf)])
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise ApiProblem(401, "session_expired", "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.")
    session = await db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash(raw), RefreshSession.revoked_at.is_(None))
    )
    if session is None or is_expired(session.expires_at):
        raise ApiProblem(401, "session_expired", "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.")
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise ApiProblem(401, "unauthenticated", "Tài khoản không còn hoạt động.")
    session.revoked_at = utcnow()
    access_token, expires_at = await _issue_session(response, db, user, request)
    await db.commit()
    return await _session_response(db, user, access_token, expires_at)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        session = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash(raw), RefreshSession.revoked_at.is_(None)))
        if session:
            session.revoked_at = utcnow()
            await db.commit()
    for cookie in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(cookie, domain=settings.cookie_domain, path="/")


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user:
        raw = new_opaque_token()
        db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash(raw), expires_at=utcnow() + timedelta(minutes=settings.password_reset_expire_minutes)))
        await db.commit()
        # The raw token is intentionally not returned in production. A mail
        # adapter can consume it here; local operators can inspect the job log.
    return {"sent": True, "message": "Nếu email này có tài khoản, hệ thống đã gửi hướng dẫn đặt lại mật khẩu."}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    reset = await db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(payload.token), PasswordResetToken.used_at.is_(None)))
    if reset is None or is_expired(reset.expires_at):
        raise ApiProblem(400, "invalid_reset_token", "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.")
    user = await db.get(User, reset.user_id)
    if user is None:
        raise ApiProblem(400, "invalid_reset_token", "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.")
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utcnow()
    reset.used_at = utcnow()
    sessions = (await db.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)))).all()
    for session in sessions:
        session.revoked_at = utcnow()
    await db.commit()
    return {"ok": True}


@router.get("/invitations/{token}")
async def preview_invitation(token: str, db: AsyncSession = Depends(get_db)):
    invitation = await db.scalar(select(Invitation).where(Invitation.token_hash == token_hash(token), Invitation.accepted_at.is_(None)))
    if invitation is None or is_expired(invitation.expires_at):
        raise ApiProblem(404, "not_found", "Lời mời không tồn tại hoặc đã hết hạn.")
    company = await db.get(Company, invitation.company_id)
    return {"email": invitation.email, "workspace_name": company.name if company else "", "role": invitation.role}


@router.post("/invitations/{token}/accept", response_model=LoginResponse)
async def accept_invitation(token: str, payload: AcceptInvitationRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    invitation = await db.scalar(select(Invitation).where(Invitation.token_hash == token_hash(token), Invitation.accepted_at.is_(None)))
    if invitation is None or is_expired(invitation.expires_at):
        raise ApiProblem(404, "not_found", "Lời mời không tồn tại hoặc đã hết hạn.")
    if str(payload.email).lower() != invitation.email:
        raise ApiProblem(422, "validation_error", "Email phải trùng với email trong lời mời.", field_errors=[{"field": "email", "message": "Email không khớp lời mời."}])
    user = await db.scalar(select(User).where(User.email == invitation.email))
    if user is None:
        user = User(email=invitation.email, full_name=payload.full_name, password_hash=hash_password(payload.password))
        db.add(user)
        await db.flush()
    existing = await db.scalar(select(Membership).where(Membership.company_id == invitation.company_id, Membership.user_id == user.id))
    if existing is None:
        db.add(Membership(company_id=invitation.company_id, user_id=user.id, role=invitation.role))
    else:
        existing.is_active = True
        existing.role = invitation.role
    invitation.accepted_at = utcnow()
    access_token, expires_at = await _issue_session(response, db, user, request)
    await db.commit()
    return await _session_response(db, user, access_token, expires_at)


async def make_session(db: AsyncSession, user: User, *, active_workspace_id: str | None = None) -> SessionResponse:
    workspaces = [_workspace_out(company, membership) for company, membership in await _workspace_rows(db, user.id)]
    active = active_workspace_id if any(workspace.id == active_workspace_id for workspace in workspaces) else (workspaces[0].id if workspaces else None)
    return SessionResponse(
        user=UserOut.model_validate(user, from_attributes=True),
        workspaces=workspaces,
        active_workspace_id=active,
        expires_at=utcnow() + timedelta(minutes=settings.access_token_expire_minutes),
    )
