"""Workspace, membership and tenant-scoped session endpoints."""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AuditEvent, Brand, Company, Invitation, Membership,
    MetaPageConnection, MetaPageGroup, MetaSyncState,
    ResearchSource, User, new_id, utcnow,
)
from .auth import _workspace_out
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .config import settings
from .errors import ApiProblem
from .email import EmailDeliveryError, send_email
from .schemas import InviteMemberRequest, InviteMemberResponse, MemberOut, PageWorkspaceCreate, SelectWorkspaceRequest, SessionResponse, UserOut, WorkspaceOut
from .security import is_expired, new_opaque_token, token_hash
from .auth import make_session
from .rate_limits import rate_limit
from .meta_client import MetaGraphClient, MetaGraphReadError, MetaGraphRejected, MetaGraphTokenExpired, MetaPage
from .meta_tokens import (
    TokenEncryptionUnavailable, decrypt_page_token, encrypt_page_token, token_fingerprint,
)


router = APIRouter(tags=["workspaces"])


def _page_slug(name: str, page_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-") or "doanh-nghiep"
    return f"{base[:100]}-{page_id[-8:]}"


async def _research_group(db: AsyncSession, company: Company) -> MetaPageGroup:
    group = await db.scalar(select(MetaPageGroup).where(
        MetaPageGroup.company_id == company.id,
        MetaPageGroup.active.is_(True),
    ).order_by(MetaPageGroup.created_at).limit(1))
    if group is None:
        group = MetaPageGroup(
            id=new_id(), company_id=company.id, name="Nghiên cứu",
            industry="Chưa xác định", region="Chưa xác định", locale="vi-VN",
            keywords_json=[], active=True,
        )
        db.add(group)
        await db.flush()
    return group


async def _bind_verified_page(
    db: AsyncSession, company: Company, page: MetaPage, encrypted_token: str,
    raw_token: str, user: User,
) -> MetaPageConnection:
    group = await _research_group(db, company)
    group.next_due_at = None
    rows = (await db.scalars(select(MetaPageConnection).where(
        MetaPageConnection.company_id == company.id,
    ).with_for_update())).all()
    connection = next((item for item in rows if item.page_id == page.id), None)
    # A workspace now represents one Page. Keep all old records for history,
    # but stop scheduling secondary Page connections after Owner selection.
    for secondary in rows:
        if secondary.page_id == page.id:
            continue
        secondary.active = False
        secondary.status = "needs_reconnect"
        secondary.last_error_code = "workspace_primary_page_changed"
        secondary.metrics_schedule_enabled = False
        secondary.next_metrics_sync_at = None
        other_sources = (await db.scalars(select(ResearchSource).where(
            ResearchSource.company_id == company.id,
            ResearchSource.connection_id == secondary.id,
            ResearchSource.active.is_(True),
        ))).all()
        for source in other_sources:
            source.active = False
            source.schedule_enabled = False
            source.next_due_at = None
            source.status = "disabled"
    if connection is None:
        connection = MetaPageConnection(
            id=new_id(), company_id=company.id, group_id=group.id, page_id=page.id,
            page_name=page.name, encrypted_token=encrypted_token,
            token_fingerprint=token_fingerprint(raw_token), status="verified",
            verified_at=utcnow(), active=True, metrics_schedule_enabled=False,
        )
        db.add(connection)
    else:
        connection.group_id = group.id
        connection.page_name = page.name
        connection.encrypted_token = encrypted_token
        connection.token_fingerprint = token_fingerprint(raw_token)
        connection.status = "verified"
        connection.last_error_code = None
        connection.verified_at = utcnow()
        connection.active = True
    if connection.metrics_schedule_enabled:
        interval = max(1, min(connection.metrics_sync_interval_hours or 6, 24 * 30))
        connection.next_metrics_sync_at = utcnow() + timedelta(hours=interval)
    company.page_id = page.id
    company.name = page.name[:200]
    company.page_avatar_url = page.picture_url
    company.page_connection_state = "active"
    sync = await db.scalar(select(MetaSyncState).where(
        MetaSyncState.company_id == company.id, MetaSyncState.page_id == page.id,
    ).with_for_update())
    if sync is None:
        db.add(MetaSyncState(
            id=new_id(), company_id=company.id, page_id=page.id,
            page_name=page.name[:200], verified_at=utcnow(), has_more=True,
        ))
    else:
        sync.page_name = page.name[:200]
        sync.verified_at = utcnow()
        sync.updated_at = utcnow()
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company.id,
        ResearchSource.connection_id == connection.id,
        ResearchSource.source_type == "owned_facebook_page",
    ).with_for_update())
    page_url = f"https://www.facebook.com/{page.id}"
    if source is None:
        source = ResearchSource(
            id=new_id(), company_id=company.id, group_id=group.id,
            connection_id=connection.id, source_type="owned_facebook_page",
            name=page.name[:200], url=page_url, normalized_url=page_url,
            status="active", active=True, crawl_mode="legacy", crawl_page_limit=1000,
            render_mode="http_only", resource_hosts_json=[], collection_mode="meta_api",
            collection_post_limit=100, collection_status="not_started",
            schedule_enabled=False, next_due_at=None, created_by=user.id,
        )
        db.add(source)
    else:
        source.group_id = group.id
        source.name = page.name[:200]
        source.url = source.normalized_url = page_url
        source.active = True
        source.status = "active"
        # schedule_enabled records the Owner's intent. A token outage pauses
        # execution by clearing next_due_at; reconnecting restores the saved
        # schedule without requiring the Owner to configure it again.
        source.next_due_at = utcnow() if source.schedule_enabled else None
    next_due = await db.scalar(select(ResearchSource.next_due_at).where(
        ResearchSource.company_id == company.id,
        ResearchSource.active.is_(True),
        ResearchSource.schedule_enabled.is_(True),
        ResearchSource.next_due_at.is_not(None),
    ).order_by(ResearchSource.next_due_at).limit(1))
    if next_due is not None:
        group.next_due_at = next_due
    db.add(AuditEvent(
        company_id=company.id, actor_user_id=user.id, action="workspace.page.bind",
        entity_type="company", entity_id=company.id,
        metadata_json={"page_id": page.id, "connection_id": connection.id},
    ))
    await db.flush()
    return connection


async def _invitation_response(
    company_id: str,
    invitation: Invitation,
    raw_token: str,
    db: AsyncSession,
) -> InviteMemberResponse:
    company = await db.get(Company, company_id)
    workspace_name = company.name if company else "doanh nghiệp của bạn"
    role_label = "biên tập viên" if invitation.role == "editor" else "người xem"
    invitation_url = f"{settings.web_base_url}/invite/{quote(raw_token, safe='')}"
    email_sent = False
    if settings.email_delivery_configured:
        body = (
            f"Bạn được mời tham gia {workspace_name} với vai trò {role_label}.\n\n"
            f"Mở liên kết này để chấp nhận lời mời: {invitation_url}\n\n"
            "Liên kết có hiệu lực trong 7 ngày. Nếu bạn không mong đợi lời mời này, "
            "hãy bỏ qua email."
        )
        try:
            await asyncio.to_thread(send_email, invitation.email, f"Lời mời tham gia {workspace_name}", body)
            email_sent = True
        except EmailDeliveryError:
            email_sent = False

    synthetic = Membership(
        id=invitation.id,
        company_id=company_id,
        user_id="pending",
        role=invitation.role,
        is_active=False,
    )
    return InviteMemberResponse(
        member=_member_out(synthetic, invitation=invitation),
        outcome="sent" if email_sent else "email_failed",
        invite_url=None if email_sent else invitation_url,
    )


@router.get("/me", response_model=SessionResponse)
async def me(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await make_session(db, user)


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Company, Membership)
        .join(Membership, Membership.company_id == Company.id)
        .where(Membership.user_id == user.id, Membership.is_active.is_(True))
        .order_by(Company.created_at)
    )
    return [_workspace_out(company, membership) for company, membership in result.all()]


@router.get("/workspaces/{company_id}", response_model=WorkspaceOut)
async def get_workspace(company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    membership = await membership_for(company_id, user, db)
    company = await db.get(Company, company_id)
    if company is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy doanh nghiệp.")
    return _workspace_out(company, membership)


@router.put("/me/active-workspace", response_model=SessionResponse, dependencies=[Depends(require_csrf)])
async def select_workspace(payload: SelectWorkspaceRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await membership_for(payload.workspace_id, user, db)
    return await make_session(db, user, active_workspace_id=payload.workspace_id)


@router.post(
    "/workspaces/from-page",
    response_model=WorkspaceOut,
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(rate_limit("workspace_page_activate", max_requests=10, window_seconds=3600)),
    ],
)
async def create_workspace_from_page(
    payload: PageWorkspaceCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceOut:
    """Verify a Page token and make that Page the identity of a new workspace."""
    encrypted = None
    try:
        encrypted = encrypt_page_token(payload.page_access_token)
    except TokenEncryptionUnavailable:
        raise ApiProblem(503, "token_encryption_unavailable", "Backend chưa cấu hình META_TOKEN_ENCRYPTION_KEY.") from None
    except ValueError:
        raise ApiProblem(422, "invalid_page_token", "Page Access Token không hợp lệ.") from None

    try:
        async with MetaGraphClient(payload.page_id, payload.page_access_token, settings.meta_graph_version) as client:
            page = await client.verify_page()
            # A successful public metadata lookup is not sufficient: require a
            # real, read-only call using this exact Page token. Never test by posting.
            await client.list_page_posts(limit=1)
    except MetaGraphTokenExpired:
        raise ApiProblem(422, "meta_token_invalid", "Page Access Token đã hết hạn hoặc bị thu hồi. Hãy tạo token mới.") from None
    except MetaGraphRejected:
        raise ApiProblem(422, "meta_page_permission_missing", "Không xác minh được Page ID và quyền đọc bằng token này.") from None
    except (MetaGraphReadError, ValueError):
        raise ApiProblem(502, "meta_verification_failed", "Meta chưa xác minh được Fanpage. Hãy kiểm tra Page ID, token và thử lại.", retryable=True) from None

    existing = await db.scalar(select(Company).where(Company.page_id == page.id))
    if existing is not None:
        membership = await db.scalar(select(Membership).where(
            Membership.company_id == existing.id, Membership.user_id == user.id,
            Membership.is_active.is_(True),
        ))
        if membership is None:
            raise ApiProblem(409, "page_already_connected", "Fanpage này đã được kết nối. Hãy nhờ Owner mời bạn vào doanh nghiệp.")
        return _workspace_out(existing, membership)

    company = Company(
        id=new_id(), name=page.name[:200], slug=_page_slug(page.name, page.id),
        industry=None, page_id=page.id, page_avatar_url=page.picture_url,
        page_connection_state="active",
    )
    owner = Membership(id=new_id(), company_id=company.id, user_id=user.id, role="owner", is_active=True)
    db.add(company)
    db.add(owner)
    db.add(Brand(id=new_id(), company_id=company.id, profile={}, version=1))
    try:
        await db.flush()
        await _bind_verified_page(db, company, page, encrypted, payload.page_access_token, user)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # A concurrent activation of the same Page is idempotent only for an
        # already-authorized member; a token never grants workspace membership.
        existing = await db.scalar(select(Company).where(Company.page_id == page.id))
        if existing is not None:
            membership = await db.scalar(select(Membership).where(
                Membership.company_id == existing.id, Membership.user_id == user.id,
                Membership.is_active.is_(True),
            ))
            if membership is not None:
                return _workspace_out(existing, membership)
            raise ApiProblem(409, "page_already_connected", "Fanpage này đã được kết nối. Hãy nhờ Owner mời bạn vào doanh nghiệp.") from None
        raise ApiProblem(409, "workspace_creation_conflict", "Không thể tạo không gian cho Fanpage đồng thời. Hãy thử lại.") from None
    return _workspace_out(company, owner)


@router.patch(
    "/workspaces/{company_id}/page-connection",
    response_model=WorkspaceOut,
    dependencies=[
        Depends(require_csrf),
        Depends(rate_limit("workspace_page_reconnect", max_requests=10, window_seconds=3600)),
    ],
)
async def reconnect_workspace_page(
    company_id: str,
    payload: PageWorkspaceCreate,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("connection:manage")),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceOut:
    company = await db.scalar(select(Company).where(Company.id == company_id))
    if company is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy doanh nghiệp.")
    if company.page_id and company.page_id != payload.page_id:
        raise ApiProblem(409, "workspace_page_change_not_allowed", "Workspace đã gắn với một Fanpage khác. Hãy tạo workspace riêng cho Page mới.")
    try:
        encrypted = encrypt_page_token(payload.page_access_token)
    except TokenEncryptionUnavailable:
        raise ApiProblem(503, "token_encryption_unavailable", "Backend chưa cấu hình META_TOKEN_ENCRYPTION_KEY.") from None
    except ValueError:
        raise ApiProblem(422, "invalid_page_token", "Page Access Token không hợp lệ.") from None
    try:
        async with MetaGraphClient(payload.page_id, payload.page_access_token, settings.meta_graph_version) as client:
            page = await client.verify_page()
            await client.list_page_posts(limit=1)
    except MetaGraphTokenExpired:
        raise ApiProblem(422, "meta_token_invalid", "Page Access Token đã hết hạn hoặc bị thu hồi.") from None
    except MetaGraphRejected:
        raise ApiProblem(422, "meta_page_permission_missing", "Token không xác minh được Page ID hoặc quyền đọc.") from None
    except (MetaGraphReadError, ValueError):
        raise ApiProblem(502, "meta_verification_failed", "Meta chưa xác minh được Fanpage. Hãy thử lại.", retryable=True) from None
    other_workspace = await db.scalar(select(Company.id).where(
        Company.page_id == page.id, Company.id != company_id,
    ))
    if other_workspace:
        raise ApiProblem(409, "page_already_connected", "Fanpage này đã được kết nối với workspace khác.")
    company = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if company is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy doanh nghiệp.")
    if company.page_id and company.page_id != page.id:
        raise ApiProblem(409, "workspace_page_change_not_allowed", "Workspace này đã đại diện cho một Fanpage khác.")
    await _bind_verified_page(db, company, page, encrypted, payload.page_access_token, user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiProblem(409, "page_already_connected", "Fanpage này đã được kết nối với workspace khác.") from None
    return _workspace_out(company, membership)


@router.post(
    "/workspaces/{company_id}/page-connection/refresh-metadata",
    response_model=WorkspaceOut,
    dependencies=[
        Depends(require_csrf),
        Depends(rate_limit("workspace_page_metadata_refresh", max_requests=20, window_seconds=3600)),
    ],
)
async def refresh_workspace_page_metadata(
    company_id: str,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("connection:manage")),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceOut:
    """Refresh workspace display identity from its already-bound Page token."""
    company = await db.scalar(select(Company).where(Company.id == company_id))
    if company is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy doanh nghiệp.")
    if not company.page_id or company.page_connection_state != "active":
        raise ApiProblem(409, "page_needs_reconnect", "Hãy kết nối lại Fanpage trước khi đồng bộ nhận diện.")
    page_id = company.page_id
    connection = await db.scalar(select(MetaPageConnection).where(
        MetaPageConnection.company_id == company_id,
        MetaPageConnection.page_id == page_id,
        MetaPageConnection.active.is_(True),
        MetaPageConnection.status == "verified",
    ))
    if connection is None:
        raise ApiProblem(409, "page_needs_reconnect", "Không tìm thấy kết nối đã xác minh của Fanpage.")
    connection_id = connection.id
    encrypted_token = connection.encrypted_token
    await db.commit()  # Do not hold a database transaction across the Meta request.

    try:
        token = decrypt_page_token(encrypted_token)
    except TokenEncryptionUnavailable:
        raise ApiProblem(503, "token_encryption_unavailable", "Backend chưa thể giải mã token Fanpage.") from None
    except ValueError:
        await _mark_workspace_page_needs_reconnect(
            db, company_id, connection_id, "token_decryption_failed",
        )
        raise ApiProblem(409, "page_token_unavailable", "Không giải mã được token Fanpage. Owner cần kết nối lại.") from None
    if not token:
        await _mark_workspace_page_needs_reconnect(db, company_id, connection_id, "token_empty")
        raise ApiProblem(409, "page_token_unavailable", "Không có token Fanpage khả dụng. Owner cần kết nối lại.")

    try:
        async with MetaGraphClient(page_id, token, settings.meta_graph_version) as client:
            page = await client.verify_page()
            if page.id != page_id:
                raise ValueError("verified Page identity changed")
            await client.list_page_posts(limit=1)
    except MetaGraphTokenExpired:
        await _mark_workspace_page_needs_reconnect(db, company_id, connection_id, "token_expired")
        raise ApiProblem(409, "page_needs_reconnect", "Page Access Token hết hạn hoặc bị thu hồi. Owner cần kết nối lại.") from None
    except MetaGraphRejected as error:
        if error.retryable:
            raise ApiProblem(429, "meta_rate_limited", "Meta đang giới hạn yêu cầu. Hãy thử đồng bộ lại sau.", retryable=True) from None
        await _mark_workspace_page_needs_reconnect(db, company_id, connection_id, "read_permission_missing")
        raise ApiProblem(409, "page_permission_missing", "Meta từ chối quyền đọc Page. Owner cần xác minh lại kết nối.") from None
    except (MetaGraphReadError, ValueError):
        raise ApiProblem(502, "meta_verification_failed", "Chưa đồng bộ được thông tin Fanpage từ Meta. Hãy thử lại.", retryable=True) from None

    page_name = page.name.strip()
    if not page_name:
        raise ApiProblem(502, "meta_verification_failed", "Meta không trả tên Fanpage hợp lệ.", retryable=True)
    company = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    connection = await db.scalar(select(MetaPageConnection).where(
        MetaPageConnection.company_id == company_id,
        MetaPageConnection.id == connection_id,
    ).with_for_update())
    if (
        company is None or connection is None or company.page_id != page_id
        or connection.page_id != page_id or connection.encrypted_token != encrypted_token
        or not connection.active or connection.status != "verified"
    ):
        raise ApiProblem(409, "page_connection_changed", "Kết nối Fanpage đã thay đổi trong lúc đồng bộ. Hãy tải lại trang.")

    company.name = page_name[:200]
    company.page_avatar_url = page.picture_url
    connection.page_name = page_name[:200]
    sync = await db.scalar(select(MetaSyncState).where(
        MetaSyncState.company_id == company_id,
        MetaSyncState.page_id == page_id,
    ).with_for_update())
    if sync is not None:
        sync.page_name = page_name[:200]
        sync.updated_at = utcnow()
    sources = (await db.scalars(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.connection_id == connection_id,
        ResearchSource.source_type == "owned_facebook_page",
        ResearchSource.active.is_(True),
    ).with_for_update())).all()
    for source in sources:
        source.name = page_name[:200]
    db.add(AuditEvent(
        company_id=company_id,
        actor_user_id=user.id,
        action="workspace.page_metadata.refresh",
        entity_type="meta_page",
        entity_id=page_id,
        metadata_json={"page_id": page_id, "avatar_available": bool(page.picture_url)},
    ))
    await db.commit()
    return _workspace_out(company, membership)


async def _mark_workspace_page_needs_reconnect(
    db: AsyncSession, company_id: str, connection_id: str, error_code: str,
) -> None:
    company = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    connection = await db.scalar(select(MetaPageConnection).where(
        MetaPageConnection.company_id == company_id,
        MetaPageConnection.id == connection_id,
    ).with_for_update())
    if connection is not None:
        connection.status = "needs_reconnect"
        connection.last_error_code = error_code
        connection.verified_at = None
        connection.next_metrics_sync_at = None
    if company is not None:
        company.page_connection_state = "needs_reconnect"
    sources = (await db.scalars(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.connection_id == connection_id,
        ResearchSource.source_type == "owned_facebook_page",
        ResearchSource.active.is_(True),
    ).with_for_update())).all()
    for source in sources:
        source.next_due_at = None
        source.status = "needs_access"
    await db.commit()


def _member_out(membership: Membership, user: User | None = None, *, invitation: Invitation | None = None) -> MemberOut:
    if invitation:
        return MemberOut(
            id=membership.id if membership else invitation.id,
            user=None,
            role=invitation.role,
            status="invited",
            invited_email=invitation.email,
            invited_by=invitation.invited_by,
            invitation_expires_at=invitation.expires_at,
        )
    return MemberOut(
        id=membership.id,
        user=UserOut.model_validate(user, from_attributes=True) if user else None,
        role=membership.role,
        status="active" if membership.is_active else "suspended",
        joined_at=membership.created_at,
    )


@router.get("/workspaces/{company_id}/members", response_model=list[MemberOut])
async def list_members(company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await membership_for(company_id, user, db)
    rows = (await db.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.company_id == company_id).order_by(Membership.created_at))).all()
    members = [_member_out(membership, member) for membership, member in rows]
    invitations = (await db.scalars(select(Invitation).where(Invitation.company_id == company_id, Invitation.accepted_at.is_(None)))).all()
    members.extend([_member_out(None, invitation=invitation) for invitation in invitations])
    return members


@router.post(
    "/workspaces/{company_id}/members",
    response_model=InviteMemberResponse,
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(rate_limit("member_invite", max_requests=20, window_seconds=3600)),
    ],
)
async def invite_member(company_id: str, payload: InviteMemberRequest, membership: Membership = Depends(require_permission("member:invite")), db: AsyncSession = Depends(get_db)):
    email = str(payload.email).lower()
    existing_user = await db.scalar(select(User).where(User.email == email))
    if existing_user:
        existing_membership = await db.scalar(select(Membership).where(Membership.company_id == company_id, Membership.user_id == existing_user.id))
        if existing_membership and existing_membership.is_active:
            return InviteMemberResponse(member=_member_out(existing_membership, existing_user), outcome="already_member")
    pending_invitation = await db.scalar(
        select(Invitation)
        .where(
            Invitation.company_id == company_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
        )
        .order_by(Invitation.expires_at.desc(), Invitation.created_at.desc())
    )
    if pending_invitation and not is_expired(pending_invitation.expires_at):
        synthetic = Membership(id=pending_invitation.id, company_id=company_id, user_id="pending", role=pending_invitation.role, is_active=False)
        return InviteMemberResponse(member=_member_out(synthetic, invitation=pending_invitation), outcome="already_invited")
    raw_token = new_opaque_token()
    if pending_invitation:
        invitation = pending_invitation
        invitation.invited_by = membership.user_id
        invitation.role = payload.role
        invitation.token_hash = token_hash(raw_token)
        invitation.expires_at = utcnow() + timedelta(days=7)
    else:
        invitation = Invitation(company_id=company_id, invited_by=membership.user_id, email=email, role=payload.role, token_hash=token_hash(raw_token), expires_at=utcnow() + timedelta(days=7))
        db.add(invitation)
    await db.commit()
    return await _invitation_response(company_id, invitation, raw_token, db)


@router.post(
    "/workspaces/{company_id}/members/{member_id}/resend-invitation",
    response_model=InviteMemberResponse,
    dependencies=[
        Depends(require_csrf),
        Depends(rate_limit("member_invite_resend", max_requests=20, window_seconds=3600)),
    ],
)
async def resend_invitation(
    company_id: str,
    member_id: str,
    membership: Membership = Depends(require_permission("member:invite")),
    db: AsyncSession = Depends(get_db),
) -> InviteMemberResponse:
    invitation = await db.scalar(
        select(Invitation).where(
            Invitation.id == member_id,
            Invitation.company_id == company_id,
            Invitation.accepted_at.is_(None),
        )
    )
    if invitation is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy lời mời đang chờ.")

    raw_token = new_opaque_token()
    invitation.token_hash = token_hash(raw_token)
    invitation.invited_by = membership.user_id
    invitation.expires_at = utcnow() + timedelta(days=7)
    await db.commit()
    return await _invitation_response(company_id, invitation, raw_token, db)
