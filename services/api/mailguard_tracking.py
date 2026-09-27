"""Private server-to-server MailGuard conversion intake and reporting."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AuditEvent, Campaign, MailGuardConversionEvent, MailGuardIntegration,
    MailGuardTrackingReference, Membership, User, new_id, utcnow,
)
from .config import settings
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .pilot_schemas import (
    MailGuardConversionAnalyticsOut, MailGuardEventIn, MailGuardEventReceipt,
    MailGuardIntegrationCreated, MailGuardIntegrationOut,
    MailGuardTrackingReferenceIn, MailGuardTrackingReferenceOut,
)
from .rate_limits import rate_limit


router = APIRouter(tags=["mailguard-conversions"])
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _integration_out(row: MailGuardIntegration) -> MailGuardIntegrationOut:
    return MailGuardIntegrationOut(
        id=row.id, key_prefix=row.key_prefix,
        status="revoked" if row.revoked_at else "active", created_at=row.created_at,
    )


@router.get("/workspaces/{company_id}/integrations/mailguard", response_model=MailGuardIntegrationOut | None)
async def get_mailguard_integration(
    company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    row = await db.scalar(select(MailGuardIntegration).where(MailGuardIntegration.company_id == company_id))
    return _integration_out(row) if row else None


@router.post("/workspaces/{company_id}/integrations/mailguard", response_model=MailGuardIntegrationCreated,
             dependencies=[Depends(require_csrf)])
async def create_mailguard_integration(
    company_id: str,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("workspace:manage")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(MailGuardIntegration).where(MailGuardIntegration.company_id == company_id).with_for_update())
    if row is not None and row.revoked_at is None:
        raise ApiProblem(409, "integration_already_active", "MailGuard đã có integration đang hoạt động; hãy thu hồi trước khi cấp lại.")
    raw_key = "mgint_" + secrets.token_urlsafe(36)
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    now = utcnow()
    if row is None:
        row = MailGuardIntegration(
            id=new_id(), company_id=company_id, key_hash=digest,
            key_prefix=raw_key[:16], created_by=user.id,
            created_at=now, updated_at=now,
        )
        db.add(row)
    else:
        row.key_hash = digest
        row.key_prefix = raw_key[:16]
        row.revoked_at = None
        row.created_by = user.id
        row.updated_at = now
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="mailguard.integration.create",
                      entity_type="mailguard_integration", entity_id=row.id,
                      metadata_json={"key_prefix": raw_key[:16]}))
    await db.commit()
    await db.refresh(row)
    return MailGuardIntegrationCreated(**_integration_out(row).model_dump(), integration_key=raw_key)


@router.post("/workspaces/{company_id}/integrations/mailguard/revoke", response_model=MailGuardIntegrationOut,
             dependencies=[Depends(require_csrf)])
async def revoke_mailguard_integration(
    company_id: str,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("workspace:manage")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(MailGuardIntegration).where(MailGuardIntegration.company_id == company_id).with_for_update())
    if row is None:
        raise ApiProblem(404, "not_found", "Chưa cấu hình MailGuard integration.")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        row.updated_at = row.revoked_at
        db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="mailguard.integration.revoke",
                          entity_type="mailguard_integration", entity_id=row.id,
                          metadata_json={"key_prefix": row.key_prefix}))
        await db.commit()
    return _integration_out(row)


@router.post("/workspaces/{company_id}/campaigns/{campaign_id}/tracking-ids",
             response_model=MailGuardTrackingReferenceOut, status_code=201,
             dependencies=[Depends(require_csrf)])
async def create_mailguard_tracking_reference(
    company_id: str,
    campaign_id: str,
    request: MailGuardTrackingReferenceIn,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("campaign:edit")),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.scalar(select(Campaign).where(Campaign.company_id == company_id, Campaign.id == campaign_id))
    if campaign is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy chiến dịch.")
    if request.campaign_id != campaign.id:
        raise ApiProblem(422, "tracking_campaign_mismatch", "Campaign trong request không khớp đường dẫn.")
    if request.post_id:
        from database.models import CampaignPost

        post = await db.scalar(select(CampaignPost).where(
            CampaignPost.company_id == company_id,
            CampaignPost.campaign_id == campaign_id,
            CampaignPost.id == request.post_id,
            CampaignPost.current_version == request.post_version,
            CampaignPost.status.in_(["approved", "scheduled", "published"]),
        ))
        if post is None:
            raise ApiProblem(409, "tracking_post_unavailable", "Chỉ tạo mã cho phiên bản bài đã duyệt hiện tại.")
    tracking_id = "trk_" + secrets.token_urlsafe(20)
    row = MailGuardTrackingReference(
        id=new_id(), company_id=company_id, tracking_id=tracking_id,
        campaign_id=campaign.id, post_id=request.post_id,
        post_version=request.post_version, created_by=user.id, created_at=utcnow(),
    )
    db.add(row)
    await db.commit()
    return MailGuardTrackingReferenceOut(
        tracking_id=row.tracking_id, campaign_id=row.campaign_id,
        post_id=row.post_id, post_version=row.post_version, created_at=row.created_at,
    )


async def _integration_from_authorization(authorization: str | None, db: AsyncSession) -> MailGuardIntegration:
    scheme, _, raw_key = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not raw_key.startswith("mgint_"):
        raise ApiProblem(401, "integration_unauthorized", "Integration key không hợp lệ.")
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    row = await db.scalar(select(MailGuardIntegration).where(
        MailGuardIntegration.key_hash == digest, MailGuardIntegration.revoked_at.is_(None),
    ))
    if row is None or not hmac.compare_digest(row.key_hash, digest):
        raise ApiProblem(401, "integration_unauthorized", "Integration key không hợp lệ hoặc đã bị thu hồi.")
    return row


@router.post("/integrations/mailguard/events", response_model=MailGuardEventReceipt,
             dependencies=[Depends(rate_limit("mailguard_conversion_events", max_requests=300, window_seconds=60))])
async def receive_mailguard_event(
    request: MailGuardEventIn,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    integration = await _integration_from_authorization(authorization, db)
    if _EMAIL.fullmatch(request.external_user_id):
        raise ApiProblem(422, "external_user_id_must_be_opaque", "Gửi ID opaque; không gửi email hoặc dữ liệu nhận dạng trực tiếp.")
    existing_id = await db.scalar(select(MailGuardConversionEvent).where(
        MailGuardConversionEvent.integration_id == integration.id,
        MailGuardConversionEvent.event_id == request.event_id,
    ))
    if existing_id:
        same = (
            existing_id.event_type == request.event_type
            and _as_utc(existing_id.occurred_at) == request.occurred_at.astimezone(timezone.utc)
            and existing_id.tracking_id == request.tracking_id
        )
        if not same:
            raise ApiProblem(409, "event_id_conflict", "event_id đã được dùng cho payload khác.")
        return MailGuardEventReceipt(accepted=False, duplicate=True, message="Sự kiện này đã được nhận trước đó.")
    tracking = None
    if request.tracking_id:
        tracking = await db.scalar(select(MailGuardTrackingReference).where(
            MailGuardTrackingReference.company_id == integration.company_id,
            MailGuardTrackingReference.tracking_id == request.tracking_id,
        ))
        if tracking is None:
            raise ApiProblem(422, "tracking_id_invalid", "tracking_id không thuộc integration/workspace này.")
    actor_hash = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"mailguard-actor:{integration.id}:{request.external_user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    actor_event = await db.scalar(select(MailGuardConversionEvent).where(
        MailGuardConversionEvent.integration_id == integration.id,
        MailGuardConversionEvent.event_type == request.event_type,
        MailGuardConversionEvent.actor_hash == actor_hash,
    ))
    if actor_event:
        return MailGuardEventReceipt(accepted=False, duplicate=True, message="Đã ghi nhận loại chuyển đổi này cho người dùng.")
    row = MailGuardConversionEvent(
        id=new_id(), company_id=integration.company_id, integration_id=integration.id,
        event_id=request.event_id, event_type=request.event_type,
        occurred_at=request.occurred_at.astimezone(timezone.utc), actor_hash=actor_hash,
        tracking_id=tracking.tracking_id if tracking else None, received_at=utcnow(),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return MailGuardEventReceipt(accepted=False, duplicate=True, message="Sự kiện trùng đã được xử lý.")
    return MailGuardEventReceipt(accepted=True, duplicate=False, message="Đã nhận sự kiện MailGuard.")


@router.get("/workspaces/{company_id}/analytics/conversions", response_model=MailGuardConversionAnalyticsOut)
async def get_mailguard_conversion_analytics(
    company_id: str,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    activation_window_days: int = Query(default=30, ge=1, le=180),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    now = utcnow()
    end = window_end or now
    start = window_start or end - timedelta(days=30)
    if start.tzinfo is None or end.tzinfo is None or start.utcoffset() is None or end.utcoffset() is None or end < start:
        raise ApiProblem(422, "invalid_time_window", "Khoảng thời gian phải có timezone hợp lệ.")
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    integration = await db.scalar(select(MailGuardIntegration).where(
        MailGuardIntegration.company_id == company_id,
        MailGuardIntegration.revoked_at.is_(None),
    ))
    base = dict(window_start=start, window_end=end, activation_window_days=activation_window_days,
                attribution=[], limitations=[])
    if integration is None:
        return MailGuardConversionAnalyticsOut(
            state="not_connected", signup_count=None, first_analysis_count=None,
            signup_cohort_count=None, activated_within_window_count=None,
            activation_rate=None, **base,
        )
    events = (await db.scalars(select(MailGuardConversionEvent).where(
        MailGuardConversionEvent.company_id == company_id,
        MailGuardConversionEvent.integration_id == integration.id,
        MailGuardConversionEvent.occurred_at >= start,
        MailGuardConversionEvent.occurred_at <= end,
    ))).all()
    if not events:
        return MailGuardConversionAnalyticsOut(
            state="no_data", signup_count=None, first_analysis_count=None,
            signup_cohort_count=None, activated_within_window_count=None,
            activation_rate=None,
            limitations=["Integration đã sẵn sàng nhưng chưa nhận event live từ website MailGuard."],
            **base,
        )
    signup_rows = [row for row in events if row.event_type == "signup_completed"]
    analysis_rows = [row for row in events if row.event_type == "first_analysis_completed"]
    all_analyses = (await db.scalars(select(MailGuardConversionEvent).where(
        MailGuardConversionEvent.company_id == company_id,
        MailGuardConversionEvent.integration_id == integration.id,
        MailGuardConversionEvent.event_type == "first_analysis_completed",
    ))).all()
    analyses_by_actor: dict[str, list[datetime]] = defaultdict(list)
    for row in all_analyses:
        analyses_by_actor[row.actor_hash].append(_as_utc(row.occurred_at))
    measurement_end = min(end, now)
    maturity_cutoff = measurement_end - timedelta(days=activation_window_days)
    cohort = [row for row in signup_rows if _as_utc(row.occurred_at) <= maturity_cutoff]
    activated = sum(
        1 for row in cohort
        if any(_as_utc(row.occurred_at) <= at <= min(
                   _as_utc(row.occurred_at) + timedelta(days=activation_window_days), measurement_end,
               )
               for at in analyses_by_actor.get(row.actor_hash, []))
    )
    refs = (await db.scalars(select(MailGuardTrackingReference).where(
        MailGuardTrackingReference.company_id == company_id,
    ))).all()
    refs_by_id = {row.tracking_id: row for row in refs}
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"signup_count": 0, "first_analysis_count": 0})
    for row in events:
        key = row.tracking_id or "unassigned"
        field = "signup_count" if row.event_type == "signup_completed" else "first_analysis_count"
        grouped[key][field] += 1
    attribution = []
    for tracking_id, counts in sorted(grouped.items()):
        ref = refs_by_id.get(tracking_id)
        attribution.append({
            "tracking_id": None if tracking_id == "unassigned" else tracking_id,
            "campaign_id": ref.campaign_id if ref else None,
            "post_id": ref.post_id if ref else None,
            **counts,
        })
    limitations = ["Conversion live chưa được nghiệm thu vì website MailGuard chưa có."]
    if len(cohort) < len(signup_rows):
        limitations.append(f"{len(signup_rows) - len(cohort)} signup chưa đủ cửa sổ {activation_window_days} ngày để đưa vào tỷ lệ kích hoạt.")
    return MailGuardConversionAnalyticsOut(
        state="available", signup_count=len(signup_rows), first_analysis_count=len(analysis_rows),
        signup_cohort_count=len(cohort), activated_within_window_count=activated,
        activation_rate=(activated / len(cohort)) if cohort else None,
        **{**base, "attribution": attribution, "limitations": limitations},
    )
