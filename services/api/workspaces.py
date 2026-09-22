"""Workspace, membership and tenant-scoped session endpoints."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Company, Invitation, Membership, User, utcnow
from .auth import _workspace_out
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .schemas import InviteMemberRequest, InviteMemberResponse, MemberOut, SelectWorkspaceRequest, SessionResponse, UserOut, WorkspaceOut
from .security import new_opaque_token, token_hash
from .auth import make_session


router = APIRouter(tags=["workspaces"])


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
    invitations = (await db.scalars(select(Invitation).where(Invitation.company_id == company_id, Invitation.accepted_at.is_(None), Invitation.expires_at > utcnow()))).all()
    members.extend([_member_out(None, invitation=invitation) for invitation in invitations])
    return members


@router.post("/workspaces/{company_id}/members", response_model=InviteMemberResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def invite_member(company_id: str, payload: InviteMemberRequest, request: Request, membership: Membership = Depends(require_permission("member:invite")), db: AsyncSession = Depends(get_db)):
    email = str(payload.email).lower()
    existing_user = await db.scalar(select(User).where(User.email == email))
    if existing_user:
        existing_membership = await db.scalar(select(Membership).where(Membership.company_id == company_id, Membership.user_id == existing_user.id))
        if existing_membership and existing_membership.is_active:
            return InviteMemberResponse(member=_member_out(existing_membership, existing_user), outcome="already_member")
    current_invitation = await db.scalar(select(Invitation).where(Invitation.company_id == company_id, Invitation.email == email, Invitation.accepted_at.is_(None), Invitation.expires_at > utcnow()))
    if current_invitation:
        synthetic = Membership(id=current_invitation.id, company_id=company_id, user_id="pending", role=current_invitation.role, is_active=False)
        return InviteMemberResponse(member=_member_out(synthetic, invitation=current_invitation), outcome="already_invited")
    raw_token = new_opaque_token()
    invitation = Invitation(company_id=company_id, invited_by=membership.user_id, email=email, role=payload.role, token_hash=token_hash(raw_token), expires_at=utcnow() + timedelta(days=7))
    db.add(invitation)
    await db.commit()
    # Email delivery is deliberately an adapter boundary. The invitation is
    # durable even when SMTP/provider delivery is unavailable.
    member = Membership(id=invitation.id, company_id=company_id, user_id="pending", role=payload.role, is_active=False)
    return InviteMemberResponse(member=_member_out(member, invitation=invitation), outcome="email_failed", invite_url=f"/invite/{raw_token}")
