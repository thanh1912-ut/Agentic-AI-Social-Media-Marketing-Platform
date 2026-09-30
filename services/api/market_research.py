"""Tenant-scoped Page groups, token setup, and market research collection."""

from __future__ import annotations

import re
import hashlib
import base64
import json
import math
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.evidence_versions import ensure_evidence_version
from database.models import (
    AuditEvent,
    AIUsageBudgetDay,
    AIUsageLedger,
    Campaign,
    Company,
    Job,
    JobStep,
    MarketEvidence,
    MarketEvidenceVersion,
    MarketReportEvidence,
    MarketReportWebSnapshot,
    MarketObservation,
    MarketReport,
    MetaPageConnection,
    MetaPageGroup,
    ResearchSourceMetricSnapshot,
    WebCrawlRun, WebEntity, WebEntitySnapshot, WebOfferSnapshot,
    MetaSyncState,
    ResearchCycle,
    ResearchSource,
    ResearchSourceErasure,
    ResearchPrivacyPolicyRevision,
    User,
    new_id,
    utcnow,
)
from .config import settings
from .cache import cache_key, get_json_cache, set_json_cache
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .permissions import has_permission
from .job_service import accepted_response, dispatch_research_job, dispatch_research_source_erasure_job
from .market_research_schemas import (
    DraftFromReportIn,
    GroupCreate,
    GroupOut,
    GroupUpdate,
    ManualImportIn,
    PageConnectIn,
    PageConnectionOut,
    ResearchReportOut,
    ResearchAIBudgetOut,
    ResearchSourceCreate,
    ResearchSourceOut,
    WebCrawlSettingsIn, WebCrawlRunOut, WebItemOut, WebItemsPage, WebOfferOut,
    CollectionSettingsIn, CollectionRunOut, CompetitorPostOut, CompetitorPostsPage,
    ResearchPrivacyPolicyUpdate, ResearchPrivacyPolicyOut,
)
from .meta_client import (
    MetaGraphClient, MetaGraphReadError, MetaGraphRejected, MetaGraphTokenExpired,
    safe_external_link_url, safe_page_attachment_metadata,
)
from .meta_tokens import TokenEncryptionUnavailable, encrypt_page_token, token_fingerprint
from .rate_limits import rate_limit
from .schemas import AcceptedResponse
from services.research.web_crawler import CrawlError, canonicalize_url
from services.research.facebook_public_crawler import normalize_facebook_page_url
from services.research.privacy import hold_comment_text, redact_facebook_text


from services.research.facebook_cli_collector import safe_comment_coverage, safe_reaction_breakdown

router = APIRouter(prefix="/workspaces/{company_id}/market-research", tags=["market-research"])
MAX_ACTIVE_PAGES = 1
MAX_SOURCES_PER_WORKSPACE = 20
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
FACEBOOK_GROUP_PATH_RE = re.compile(r"^/groups/([A-Za-z0-9._-]{1,128})/?$", re.IGNORECASE)


def _require_market_manager(membership) -> None:
    if not has_permission(membership.role, "market:manage"):
        raise ApiProblem(
            403,
            "forbidden",
            "Bạn không có quyền thực hiện thao tác này.",
            details={"required_permission": "market:manage", "required_role": None},
        )


def _require_active_page(company: Company) -> None:
    if company.page_connection_state == "active" and company.page_id:
        return
    code = "page_connection_required" if not company.page_id else "page_needs_reconnect"
    message = (
        "Owner cần kết nối Fanpage doanh nghiệp trước khi dùng các tác vụ Agentic."
        if code == "page_connection_required"
        else "Fanpage cần được kết nối lại trước khi tiếp tục các tác vụ Agentic."
    )
    raise ApiProblem(409, code, message, details={"workspace_id": company.id})


def _group_out(row: MetaPageGroup, page_count: int, source_count: int) -> GroupOut:
    return GroupOut(
        id=row.id, name=row.name, industry=row.industry, region=row.region, locale=row.locale,
        keywords=row.keywords_json or [], active=row.active, page_count=page_count,
        source_count=source_count, next_due_at=row.next_due_at, last_cycle_at=row.last_cycle_at,
    )


def _page_out(row: MetaPageConnection) -> PageConnectionOut:
    return PageConnectionOut(
        id=row.id, group_id=row.group_id, page_id=row.page_id, page_name=row.page_name,
        status=row.status if row.status in {"configured", "verified", "error", "needs_reconnect"} else "error",
        verified_at=row.verified_at, last_error_code=row.last_error_code, active=row.active,
    )


def _source_out(row: ResearchSource) -> ResearchSourceOut:
    return ResearchSourceOut(
        id=row.id, group_id=row.group_id, source_type=row.source_type, name=row.name,
        url=row.url, competitor_name=row.competitor_name, status=row.status, active=row.active,
        next_due_at=row.next_due_at, last_crawled_at=row.last_crawled_at,
        error=row.error_json, connection_id=row.connection_id,
        crawl_mode=row.crawl_mode, crawl_page_limit=row.crawl_page_limit,
        render_mode=row.render_mode, resource_hosts=row.resource_hosts_json or [],
        schedule_enabled=row.schedule_enabled,
        collection_mode=row.collection_mode, collection_post_limit=row.collection_post_limit,
        collection_status=row.collection_status, collection_last_method=row.collection_last_method,
        last_collection_attempt_at=row.last_collection_attempt_at,
        last_collection_success_at=row.last_collection_success_at,
    )


def _explicit_group_audience(group: MetaPageGroup) -> list[str]:
    unknown_values = {"chưa xác định", "unknown", "not specified", "n/a"}
    industry = group.industry.strip() if isinstance(group.industry, str) else ""
    region = group.region.strip() if isinstance(group.region, str) else ""
    if industry.casefold() in unknown_values:
        industry = ""
    if region.casefold() in unknown_values:
        region = ""
    if industry and region:
        return [f"Khách hàng thuộc ngành {industry} tại {region}"]
    if industry:
        return [f"Khách hàng thuộc ngành {industry}"]
    if region:
        return [f"Khách hàng tại {region}"]
    return []


async def _tenant_group(db: AsyncSession, company_id: str, group_id: str, *, lock: bool = False) -> MetaPageGroup:
    statement = select(MetaPageGroup).where(
        MetaPageGroup.company_id == company_id, MetaPageGroup.id == group_id,
    )
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nhóm Fanpage.")
    return row


async def _default_research_group(db: AsyncSession, company_id: str) -> MetaPageGroup:
    group = await db.scalar(select(MetaPageGroup).where(
        MetaPageGroup.company_id == company_id,
        MetaPageGroup.active.is_(True),
        MetaPageGroup.name == "Nghiên cứu",
    ).order_by(MetaPageGroup.created_at).limit(1))
    if group is None:
        group = await db.scalar(select(MetaPageGroup).where(
            MetaPageGroup.company_id == company_id,
            MetaPageGroup.active.is_(True),
        ).order_by(MetaPageGroup.created_at).limit(1))
    if group is None:
        group = MetaPageGroup(
            id=new_id(), company_id=company_id, name="Nghiên cứu",
            industry="Chưa xác định", region="Chưa xác định", locale="vi-VN",
            keywords_json=[], active=True,
        )
        db.add(group)
        await db.flush()
    return group


async def _group_counts(db: AsyncSession, company_id: str, group_id: str) -> tuple[int, int]:
    pages = int(await db.scalar(select(func.count(MetaPageConnection.id)).where(
        MetaPageConnection.company_id == company_id, MetaPageConnection.group_id == group_id,
        MetaPageConnection.active.is_(True),
    )) or 0)
    sources = int(await db.scalar(select(func.count(ResearchSource.id)).where(
        ResearchSource.company_id == company_id, ResearchSource.group_id == group_id,
        ResearchSource.active.is_(True),
    )) or 0)
    return pages, sources


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    rows = (await db.scalars(select(MetaPageGroup).where(
        MetaPageGroup.company_id == company_id,
    ).order_by(MetaPageGroup.created_at))).all()
    output = []
    for row in rows:
        page_count, source_count = await _group_counts(db, company_id, row.id)
        output.append(_group_out(row, page_count, source_count))
    return output


def _encode_web_cursor(created_at: datetime, entity_id: str) -> str:
    raw = json.dumps([created_at.isoformat(), entity_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_web_cursor(value: str | None) -> tuple[datetime, str] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        created, entity_id = json.loads(base64.urlsafe_b64decode(padded.encode()))
        parsed = datetime.fromisoformat(created)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if not isinstance(entity_id, str) or len(entity_id) > 36:
            raise ValueError
        return parsed, entity_id
    except (ValueError, TypeError, json.JSONDecodeError):
        raise ApiProblem(422, "invalid_cursor", "Con trỏ phân trang không hợp lệ.") from None


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


async def _web_item_out(db: AsyncSession, entity: WebEntity, snapshot: WebEntitySnapshot | None) -> WebItemOut:
    offers: list[WebOfferOut] = []
    if snapshot:
        rows = (await db.scalars(select(WebOfferSnapshot).where(
            WebOfferSnapshot.company_id == entity.company_id,
            WebOfferSnapshot.entity_snapshot_id == snapshot.id,
        ).order_by(WebOfferSnapshot.currency, WebOfferSnapshot.price, WebOfferSnapshot.id))).all()
        offers = [WebOfferOut(
            id=row.id, offer_key=row.offer_key, price_kind=row.price_kind,
            price=_decimal_text(row.price), low_price=_decimal_text(row.low_price),
            original_price=_decimal_text(row.original_price),
            high_price=_decimal_text(row.high_price), currency=row.currency,
            availability=row.availability, billing_unit=row.billing_unit, seller=row.seller,
            offer_url=row.offer_url, provenance=row.provenance_json,
        ) for row in rows]
    return WebItemOut(
        id=entity.id, source_id=entity.source_id, kind=entity.kind, title=entity.title,
        url=entity.canonical_url, observed_at=snapshot.observed_at if snapshot else None,
        data=snapshot.data_json if snapshot else None, offers=offers,
    )


@router.patch("/sources/{source_id}/crawl-settings", response_model=ResearchSourceOut,
              dependencies=[Depends(require_csrf)])
async def update_web_crawl_settings(
    company_id: str, source_id: str, request: WebCrawlSettingsIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await membership_for(company_id, user, db)
    _require_market_manager(membership)
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id, ResearchSource.id == source_id,
        ResearchSource.source_type == "website", ResearchSource.active.is_(True),
    ).with_for_update())
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn website.")
    if request.render_mode == "javascript":
        raise ApiProblem(409, "renderer_unavailable", "Trình duyệt JavaScript chưa được bật vì môi trường hiện tại chưa xác minh được cô lập mạng ra ngoài.")
    hosts: list[str] = []
    for host in request.resource_hosts:
        candidate = host.strip().rstrip(".").encode("idna").decode("ascii").lower()
        if (not candidate or "/" in candidate or ":" in candidate or "@" in candidate
                or candidate.startswith(".") or len(candidate) > 253):
            raise ApiProblem(422, "invalid_resource_host", "Host tài nguyên cần là hostname riêng lẻ, không gồm scheme hoặc path.")
        hosts.append(candidate)
    company = await db.get(Company, company_id)
    if company is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy doanh nghiệp.")
    if company.page_connection_state != "active" or not company.page_id:
        pause_only = (
            request.schedule_enabled is False
            and request.crawl_mode == source.crawl_mode
            and request.crawl_page_limit == source.crawl_page_limit
            and request.render_mode == source.render_mode
            and sorted(set(hosts)) == sorted(source.resource_hosts_json or [])
        )
        if not pause_only:
            _require_active_page(company)
    source.crawl_mode = request.crawl_mode
    source.crawl_page_limit = request.crawl_page_limit
    source.render_mode = request.render_mode
    source.resource_hosts_json = sorted(set(hosts))
    source.schedule_enabled = request.schedule_enabled
    source.next_due_at = (utcnow() if request.schedule_enabled else None)
    source.updated_at = utcnow()
    group = await _tenant_group(db, company_id, source.group_id, lock=True)
    scheduled_due_times = (await db.scalars(select(ResearchSource.next_due_at).where(
        ResearchSource.company_id == company_id,
        ResearchSource.group_id == source.group_id,
        ResearchSource.active.is_(True),
        ResearchSource.schedule_enabled.is_(True),
    ))).all()
    group.next_due_at = min((value for value in scheduled_due_times if value is not None), default=None)
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.source.crawl_settings",
                      entity_type="research_source", entity_id=source.id,
                      metadata_json={"crawl_mode": source.crawl_mode, "page_limit": source.crawl_page_limit,
                                     "render_mode": source.render_mode, "schedule_enabled": source.schedule_enabled}))
    await db.commit()
    return _source_out(source)


@router.get("/sources/{source_id}/crawl-runs", response_model=list[WebCrawlRunOut])
async def list_web_crawl_runs(
    company_id: str, source_id: str,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    source = await db.scalar(select(ResearchSource.id).where(
        ResearchSource.company_id == company_id, ResearchSource.id == source_id,
    ))
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn website.")
    runs = (await db.scalars(select(WebCrawlRun).where(
        WebCrawlRun.company_id == company_id, WebCrawlRun.source_id == source_id,
    ).order_by(WebCrawlRun.created_at.desc()).limit(50))).all()
    return [WebCrawlRunOut(id=row.id, source_id=row.source_id, status=row.status,
                           page_limit=row.page_limit, counters=row.counters_json or {},
                           started_at=row.started_at, completed_at=row.completed_at,
                           created_at=row.created_at) for row in runs]


@router.patch("/sources/{source_id}/collection-settings", response_model=ResearchSourceOut,
              dependencies=[Depends(require_csrf)])
async def update_collection_settings(
    company_id: str, source_id: str, request: CollectionSettingsIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await membership_for(company_id, user, db)
    _require_market_manager(membership)
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id, ResearchSource.id == source_id,
        ResearchSource.source_type.in_(["owned_facebook_page", "competitor_facebook_page", "facebook_group"]),
        ResearchSource.active.is_(True),
    ).with_for_update())
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn Facebook.")
    company = await db.get(Company, company_id)
    if company is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy doanh nghiệp.")
    if company.page_connection_state != "active" or not company.page_id:
        pause_only = (
            request.schedule_enabled is False
            and request.collector == source.collection_mode
            and request.post_limit == (source.collection_post_limit or 50)
        )
        if not pause_only:
            _require_active_page(company)
    previous_mode = source.collection_mode
    if source.source_type == "owned_facebook_page" and request.collector != "meta_api":
        raise ApiProblem(422, "owned_page_collector_fixed", "Fanpage doanh nghiệp chỉ dùng Meta API của Page đã kết nối.")
    if source.source_type == "facebook_group" and request.collector != "public_web":
        raise ApiProblem(422, "group_collector_fixed", "Nhóm công khai chỉ dùng facebook-cli Tier 0 metadata.")
    source.collection_mode = request.collector
    source.collection_post_limit = request.post_limit
    source.schedule_enabled = request.schedule_enabled
    if previous_mode != request.collector:
        source.collection_status = "not_started"
        source.error_json = None
        source.status = "active"
    blocked = source.collection_status in {
        "login_required", "access_denied", "challenge", "challenge_required", "group_not_public",
        "page_needs_reconnect", "page_token_unavailable", "page_token_expired", "page_permission_missing",
    }
    source.next_due_at = (
        utcnow() if request.schedule_enabled and request.collector != "manual" and not blocked else None
    )
    source.updated_at = utcnow()
    group = await _tenant_group(db, company_id, source.group_id, lock=True)
    due_times = (await db.scalars(select(ResearchSource.next_due_at).where(
        ResearchSource.company_id == company_id, ResearchSource.group_id == source.group_id,
        ResearchSource.active.is_(True), ResearchSource.schedule_enabled.is_(True),
    ))).all()
    group.next_due_at = min((value for value in due_times if value is not None), default=None)
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.source.collection_settings",
                      entity_type="research_source", entity_id=source.id,
                      metadata_json={"collector": request.collector, "post_limit": request.post_limit,
                                     "schedule_enabled": request.schedule_enabled}))
    await db.commit()
    return _source_out(source)


@router.get("/sources/{source_id}/collection-runs", response_model=list[CollectionRunOut])
async def list_competitor_collection_runs(
    company_id: str, source_id: str,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    source = await db.scalar(select(ResearchSource.id).where(
        ResearchSource.company_id == company_id, ResearchSource.id == source_id,
        ResearchSource.source_type.in_(["competitor_facebook_page", "facebook_group"]),
    ))
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn Facebook công khai.")
    rows = (await db.scalars(select(WebCrawlRun).where(
        WebCrawlRun.company_id == company_id, WebCrawlRun.source_id == source_id,
    ).order_by(WebCrawlRun.created_at.desc()).limit(50))).all()
    return [
        CollectionRunOut(
            id=row.id, source_id=row.source_id, job_id=row.job_id,
            collector=str((row.config_json or {}).get("collector", "unknown")),
            engine=(row.config_json or {}).get("engine"),
            engine_version=(row.config_json or {}).get("engine_version"),
            access_tier=(row.config_json or {}).get("access_tier"),
            privacy_policy_revision_id=(row.config_json or {}).get("privacy_policy_revision_id"),
            privacy_policy_revision_no=(row.config_json or {}).get("privacy_policy_revision_no"),
            privacy_policy_version=(row.config_json or {}).get("privacy_policy_version"),
            privacy_policy_ready_for_collection=(row.config_json or {}).get(
                "privacy_policy_ready_for_collection"
            ),
            privacy_policy_legal_basis_verified=(row.config_json or {}).get(
                "privacy_policy_legal_basis_verified"
            ),
            privacy_policy_requested_retention_days=(row.config_json or {}).get(
                "privacy_policy_requested_retention_days"
            ),
            retention_enforcement_status=(row.config_json or {}).get("retention_enforcement_status", "not_enforced"),
            comments_content_status=(row.config_json or {}).get("comments_content_status", "privacy_hold"),
            status=row.status, post_limit=row.page_limit,
            counters=row.counters_json or {}, coverage=(row.counters_json or {}).get("coverage", {}),
            blocked_reason=(row.counters_json or {}).get("blocked_reason"),
            started_at=row.started_at, completed_at=row.completed_at, created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/sources/{source_id}/posts", response_model=CompetitorPostsPage)
async def list_competitor_posts(
    company_id: str, source_id: str, limit: int = 25, cursor: str | None = None,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id, ResearchSource.id == source_id,
        ResearchSource.source_type == "competitor_facebook_page",
    ))
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy Fanpage đối thủ.")
    if not 1 <= limit <= 100:
        raise ApiProblem(422, "invalid_limit", "Giới hạn cần nằm trong khoảng 1 đến 100.")
    statement = select(MarketEvidence).where(
        MarketEvidence.company_id == company_id, MarketEvidence.source_id == source_id,
    )
    decoded = _decode_web_cursor(cursor)
    if decoded:
        seen_at, evidence_id = decoded
        statement = statement.where(
            (MarketEvidence.last_seen_at < seen_at)
            | ((MarketEvidence.last_seen_at == seen_at) & (MarketEvidence.id < evidence_id))
        )
    rows = (await db.scalars(statement.order_by(
        MarketEvidence.last_seen_at.desc(), MarketEvidence.id.desc(),
    ).limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    observations = (await db.scalars(select(MarketObservation).where(
        MarketObservation.company_id == company_id,
        MarketObservation.evidence_id.in_([evidence.id for evidence in rows] or ["__none__"]),
    ).order_by(MarketObservation.evidence_id, MarketObservation.observed_at.desc()))).all()
    latest_by_evidence: dict[str, MarketObservation] = {}
    for observation in observations:
        latest_by_evidence.setdefault(observation.evidence_id, observation)
    posts: list[CompetitorPostOut] = []
    for evidence in rows:
        observation = latest_by_evidence.get(evidence.id)
        raw_metrics = observation.metrics_json if observation and isinstance(observation.metrics_json, dict) else {}
        metrics = {
            key: value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
            for key, value in raw_metrics.items()
            if key in {"reactions", "comments", "shares", "views"}
        }
        attachments = safe_page_attachment_metadata(raw_metrics.get("attachments"))
        attachment_status = raw_metrics.get("attachment_metadata_status")
        if attachment_status not in {"returned", "none_returned", "not_returned", "truncated"}:
            attachment_status = "not_returned"
        provenance = raw_metrics.get("_provenance", {})
        posts.append(CompetitorPostOut(
            id=evidence.id, source_id=source_id, external_id=evidence.external_id,
            url=evidence.canonical_url, title=evidence.title, text=evidence.text,
            published_at=evidence.published_at,
            observed_at=observation.observed_at if observation else None,
            metrics=metrics, metric_provenance=provenance if isinstance(provenance, dict) else {},
            link_url=safe_external_link_url(raw_metrics.get("link_url")),
            attachments=attachments, attachment_metadata_status=attachment_status,
            content_truncated=bool(raw_metrics.get("content_truncated", False)),
            reaction_breakdown=safe_reaction_breakdown(raw_metrics.get("reaction_breakdown")),
            comment_coverage=safe_comment_coverage(raw_metrics.get("comment_coverage")),
        ))
    audience = await db.scalar(select(ResearchSourceMetricSnapshot).where(
        ResearchSourceMetricSnapshot.company_id == company_id,
        ResearchSourceMetricSnapshot.source_id == source_id,
    ).order_by(ResearchSourceMetricSnapshot.observed_at.desc()).limit(1))
    next_cursor = _encode_web_cursor(rows[-1].last_seen_at, rows[-1].id) if has_more and rows else None
    return CompetitorPostsPage(
        posts=posts, next_cursor=next_cursor,
        followers=audience.followers if audience else None,
        followers_observed_at=audience.observed_at if audience else None,
        followers_missing_reason=(
            None if audience and audience.followers is not None
            else "not_published_or_not_available" if audience
            else "not_observed"
        ),
    )


@router.post("/sources/{source_id}/crawl", response_model=AcceptedResponse, status_code=202,
             dependencies=[Depends(require_csrf)])
async def crawl_competitor_source_now(
    company_id: str, source_id: str, user: User = Depends(current_user),
    membership=Depends(require_permission("market:manage")),
    _rate_limit: None = Depends(rate_limit("market_research_crawl", max_requests=6, window_seconds=3600)),
    db: AsyncSession = Depends(get_db),
):
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id, ResearchSource.id == source_id,
        ResearchSource.active.is_(True),
    ).with_for_update())
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn nghiên cứu.")
    if source.source_type == "competitor_facebook_page" and source.collection_mode == "manual":
        raise ApiProblem(409, "manual_collection_selected", "Nguồn đang ở chế độ nhập thủ công; hãy chọn public_web hoặc meta_api.")
    if source.source_type == "competitor_facebook_page" and source.collection_mode == "meta_api" and not getattr(settings, "meta_public_content_access_token", ""):
        raise ApiProblem(409, "meta_public_access_unconfigured", "Meta App chưa cấu hình quyền Page Public Content Access.")
    group = await _tenant_group(db, company_id, source.group_id, lock=True)
    pending = (await db.scalars(select(ResearchCycle).where(
        ResearchCycle.company_id == company_id, ResearchCycle.group_id == group.id,
        ResearchCycle.status.in_(["queued", "running"]),
    ).order_by(ResearchCycle.created_at.desc()).limit(20))).all()
    for cycle in pending:
        job = await db.get(Job, cycle.job_id)
        result = (job.result or {}) if job else {}
        selected = result.get("source_ids")
        if job and (not selected or source.id in selected):
            return await accepted_response(db, job)
    now = utcnow()
    cycle_key = f"source-manual:{source.id}:{now.strftime('%Y%m%dT%H%M%S%f')}"
    job = Job(
        id=new_id(), company_id=company_id, created_by=user.id, kind="market_research",
        title=f"Thu thập nghiên cứu: {source.name}", status="queued", progress=0,
        result={"group_id": group.id, "source_ids": [source.id]},
        idempotency_key=f"market-source:{source.id}:{cycle_key}",
    )
    db.add(job)
    await db.flush()
    db.add(JobStep(job_id=job.id, step_key="collect_sources",
                   label="Kiểm tra quyền truy cập và thu thập bài viết công khai", status="pending"))
    db.add(ResearchCycle(
        id=new_id(), company_id=company_id, group_id=group.id, job_id=job.id,
        cycle_key=cycle_key, status="queued", source_results_json=[],
    ))
    source.latest_job_id = job.id
    source.collection_status = "queued"
    group.next_due_at = None
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.source.crawl_request",
                      entity_type="research_source", entity_id=source.id,
                      metadata_json={"collector": source.collection_mode}))
    await db.commit()
    await dispatch_research_job(job.id)
    return await accepted_response(db, job)


@router.get("/groups/{group_id}/web-items", response_model=WebItemsPage)
async def list_group_web_items(
    company_id: str, group_id: str, kind: str | None = None, source_id: str | None = None,
    category: str | None = None, query: str | None = None, currency: str | None = None,
    minimum_price: Decimal | None = None, maximum_price: Decimal | None = None,
    limit: int = 25, cursor: str | None = None,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    await _tenant_group(db, company_id, group_id)
    if not 1 <= limit <= 100:
        raise ApiProblem(422, "invalid_limit", "Giới hạn cần nằm trong khoảng 1 đến 100.")
    if kind and kind not in {"product", "article", "business_info"}:
        raise ApiProblem(422, "invalid_kind", "Loại mục website không hợp lệ.")
    if (minimum_price is not None or maximum_price is not None) and not currency:
        raise ApiProblem(422, "currency_required", "Lọc giá cần chỉ định tiền tệ; hệ thống không tự quy đổi.")
    statement = select(WebEntity, WebEntitySnapshot).outerjoin(
        WebEntitySnapshot,
        (WebEntitySnapshot.company_id == WebEntity.company_id)
        & (WebEntitySnapshot.id == WebEntity.latest_snapshot_id),
    ).where(WebEntity.company_id == company_id, WebEntity.group_id == group_id)
    if kind:
        statement = statement.where(WebEntity.kind == kind)
    if source_id:
        statement = statement.where(WebEntity.source_id == source_id)
    if query:
        statement = statement.where(WebEntity.title.ilike(f"%{query[:100]}%"))
    if category:
        statement = statement.where(WebEntitySnapshot.data_json["category"].as_string() == category[:300])
    if currency:
        statement = statement.where(select(WebOfferSnapshot.id).where(
            WebOfferSnapshot.company_id == company_id,
            WebOfferSnapshot.entity_snapshot_id == WebEntitySnapshot.id,
            WebOfferSnapshot.currency == currency.upper()[:8],
            WebOfferSnapshot.price.is_not(None),
            WebOfferSnapshot.price >= minimum_price if minimum_price is not None else True,
            WebOfferSnapshot.price <= maximum_price if maximum_price is not None else True,
        ).exists())
    decoded = _decode_web_cursor(cursor)
    if decoded:
        created_at, entity_id = decoded
        statement = statement.where(
            (WebEntity.created_at < created_at)
            | ((WebEntity.created_at == created_at) & (WebEntity.id < entity_id))
        )
    rows = (await db.execute(statement.order_by(WebEntity.created_at.desc(), WebEntity.id.desc()).limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_web_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None
    return WebItemsPage(items=[await _web_item_out(db, entity, snapshot) for entity, snapshot in rows],
                         next_cursor=next_cursor)


@router.get("/web-items/{item_id}", response_model=WebItemOut)
async def get_web_item(
    company_id: str, item_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    entity = await db.scalar(select(WebEntity).where(
        WebEntity.company_id == company_id, WebEntity.id == item_id,
    ))
    if entity is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy mục website.")
    snapshot = await db.scalar(select(WebEntitySnapshot).where(
        WebEntitySnapshot.company_id == company_id,
        WebEntitySnapshot.id == entity.latest_snapshot_id,
    )) if entity.latest_snapshot_id else None
    return await _web_item_out(db, entity, snapshot)


@router.get("/web-items/{item_id}/snapshots", response_model=list[WebItemOut])
async def list_web_item_snapshots(
    company_id: str, item_id: str, limit: int = 25,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    if not 1 <= limit <= 100:
        raise ApiProblem(422, "invalid_limit", "Giới hạn cần nằm trong khoảng 1 đến 100.")
    entity = await db.scalar(select(WebEntity).where(
        WebEntity.company_id == company_id, WebEntity.id == item_id,
    ))
    if entity is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy mục website.")
    snapshots = (await db.scalars(select(WebEntitySnapshot).where(
        WebEntitySnapshot.company_id == company_id, WebEntitySnapshot.entity_id == entity.id,
    ).order_by(WebEntitySnapshot.observed_at.desc()).limit(limit))).all()
    return [await _web_item_out(db, entity, snapshot) for snapshot in snapshots]


@router.post("/groups", response_model=GroupOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_group(
    company_id: str,
    request: GroupCreate,
    user: User = Depends(current_user),
    membership=Depends(require_permission("market:manage")),
    db: AsyncSession = Depends(get_db),
):
    count = int(await db.scalar(select(func.count(MetaPageGroup.id)).where(MetaPageGroup.company_id == company_id)) or 0)
    if count >= 10:
        raise ApiProblem(409, "group_limit", "Workspace đã đạt giới hạn 10 nhóm thị trường.")
    row = MetaPageGroup(
        id=new_id(), company_id=company_id, name=request.name, industry=request.industry,
        region=request.region, locale=request.locale, keywords_json=request.keywords,
        active=True, next_due_at=None,
    )
    db.add(row)
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.group.create",
                      entity_type="meta_page_group", entity_id=row.id,
                      metadata_json={"industry": row.industry, "region": row.region}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiProblem(409, "group_name_exists", "Tên nhóm đã được dùng trong workspace này.") from None
    return _group_out(row, 0, 0)


@router.patch("/groups/{group_id}", response_model=GroupOut, dependencies=[Depends(require_csrf)])
async def update_group(
    company_id: str, group_id: str, request: GroupUpdate,
    user: User = Depends(current_user), membership=Depends(require_permission("market:manage")),
    db: AsyncSession = Depends(get_db),
):
    row = await _tenant_group(db, company_id, group_id, lock=True)
    for key, value in request.model_dump().items():
        setattr(row, "keywords_json" if key == "keywords" else key, value)
    row.updated_at = utcnow()
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.group.update",
                      entity_type="meta_page_group", entity_id=row.id, metadata_json={"active": row.active}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiProblem(409, "group_name_exists", "Tên nhóm đã được dùng trong workspace này.") from None
    page_count, source_count = await _group_counts(db, company_id, row.id)
    return _group_out(row, page_count, source_count)


@router.get("/groups/{group_id}/pages", response_model=list[PageConnectionOut])
async def list_pages(
    company_id: str, group_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    await _tenant_group(db, company_id, group_id)
    rows = (await db.scalars(select(MetaPageConnection).where(
        MetaPageConnection.company_id == company_id, MetaPageConnection.group_id == group_id,
        MetaPageConnection.active.is_(True),
    ).order_by(MetaPageConnection.created_at))).all()
    return [_page_out(row) for row in rows]


@router.get("/pages", response_model=list[PageConnectionOut])
async def list_all_pages(
    company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    rows = (await db.scalars(select(MetaPageConnection).where(
        MetaPageConnection.company_id == company_id, MetaPageConnection.active.is_(True),
    ).order_by(MetaPageConnection.created_at))).all()
    return [_page_out(row) for row in rows]


@router.post("/groups/{group_id}/pages", response_model=PageConnectionOut, status_code=201,
            dependencies=[Depends(require_csrf)])
async def connect_page(
    company_id: str, group_id: str, request: PageConnectIn,
    user: User = Depends(current_user), membership=Depends(require_permission("connection:manage")),
    _rate_limit: None = Depends(rate_limit("meta_page_verify", max_requests=10, window_seconds=3600)),
    db: AsyncSession = Depends(get_db),
):
    await _tenant_group(db, company_id, group_id)
    try:
        encrypted = encrypt_page_token(request.page_access_token)
    except TokenEncryptionUnavailable:
        raise ApiProblem(503, "token_encryption_unavailable", "Backend chưa cấu hình META_TOKEN_ENCRYPTION_KEY.") from None
    try:
        async with MetaGraphClient(request.page_id, request.page_access_token, settings.meta_graph_version) as client:
            page = await client.verify_page()
            await client.list_page_posts(limit=1)
    except MetaGraphRejected as error:
        code = "meta_token_invalid" if isinstance(error, MetaGraphTokenExpired) else "meta_permission_missing"
        raise ApiProblem(422, code, "Meta từ chối Page ID hoặc token. Kiểm tra token, Page ID và quyền đọc Page.") from None
    except (MetaGraphReadError, ValueError):
        raise ApiProblem(502, "meta_verification_failed", "Không xác minh được Fanpage với Meta Graph API.", retryable=True) from None

    company = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if company is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy doanh nghiệp.")
    if company.page_id and company.page_id != page.id:
        raise ApiProblem(409, "workspace_page_change_not_allowed", "Workspace này đã đại diện cho một Fanpage khác. Hãy tạo workspace riêng cho Page mới.")
    other_company = await db.scalar(select(Company.id).where(
        Company.page_id == page.id, Company.id != company_id,
    ))
    if other_company:
        raise ApiProblem(409, "page_already_connected", "Fanpage này đã được kết nối với workspace khác.")

    async with db.begin_nested():
        await db.scalar(select(Company.id).where(Company.id == company_id).with_for_update())
        await db.execute(select(MetaPageGroup.id).where(MetaPageGroup.id == group_id).with_for_update())
        row = await db.scalar(select(MetaPageConnection).where(
            MetaPageConnection.company_id == company_id, MetaPageConnection.page_id == page.id,
        ).with_for_update())
        if row is not None and row.active and row.group_id != group_id:
            raise ApiProblem(409, "page_already_in_group", "Fanpage này đang thuộc nhóm khác. Ngắt kết nối trước khi chuyển nhóm.")
        if row is None or not row.active:
            page_count = int(await db.scalar(select(func.count(MetaPageConnection.id)).where(
                MetaPageConnection.company_id == company_id, MetaPageConnection.active.is_(True),
            )) or 0)
            if page_count >= MAX_ACTIVE_PAGES:
                raise ApiProblem(409, "page_limit", f"Workspace chỉ kết nối tối đa {MAX_ACTIVE_PAGES} Fanpage.")
            if row is None:
                row = MetaPageConnection(
                    id=new_id(), company_id=company_id, group_id=group_id, page_id=page.id,
                    page_name=page.name, encrypted_token=encrypted,
                    token_fingerprint=token_fingerprint(request.page_access_token),
                    status="verified", verified_at=utcnow(), active=True,
                )
                db.add(row)
            else:
                # Page IDs stay unique for the workspace even after disconnect.
                # Reactivate the row so reconnecting cannot violate that key.
                row.group_id = group_id
                row.page_name = page.name
                row.encrypted_token = encrypted
                row.token_fingerprint = token_fingerprint(request.page_access_token)
                row.status = "verified"
                row.last_error_code = None
                row.verified_at = utcnow()
                row.active = True
        else:
            row.page_name = page.name
            row.encrypted_token = encrypted
            row.token_fingerprint = token_fingerprint(request.page_access_token)
            row.status = "verified"
            row.last_error_code = None
            row.verified_at = utcnow()
        row.active = True
        company.page_id = page.id
        company.name = page.name[:200]
        company.page_avatar_url = page.picture_url
        company.page_connection_state = "active"
        other_connections = (await db.scalars(select(MetaPageConnection).where(
            MetaPageConnection.company_id == company_id,
            MetaPageConnection.id != row.id,
            MetaPageConnection.active.is_(True),
        ).with_for_update())).all()
        for secondary in other_connections:
            secondary.active = False
            secondary.status = "needs_reconnect"
            secondary.last_error_code = "workspace_primary_page_changed"
            secondary.metrics_schedule_enabled = False
            secondary.next_metrics_sync_at = None
            secondary_sources = (await db.scalars(select(ResearchSource).where(
                ResearchSource.company_id == company_id,
                ResearchSource.connection_id == secondary.id,
                ResearchSource.active.is_(True),
            ))).all()
            for secondary_source in secondary_sources:
                secondary_source.active = False
                secondary_source.schedule_enabled = False
                secondary_source.next_due_at = None
                secondary_source.status = "disabled"
        sync_state = await db.scalar(select(MetaSyncState).where(
            MetaSyncState.company_id == company_id, MetaSyncState.page_id == page.id,
        ).with_for_update())
        if sync_state is None:
            sync_state = MetaSyncState(company_id=company_id, page_id=page.id, page_name=page.name,
                                       verified_at=utcnow(), has_more=True)
            db.add(sync_state)
        else:
            sync_state.page_name = page.name
            sync_state.verified_at = utcnow()
            sync_state.updated_at = utcnow()
        owned_source = await db.scalar(select(ResearchSource).where(
            ResearchSource.company_id == company_id,
            ResearchSource.connection_id == row.id,
            ResearchSource.source_type == "owned_facebook_page",
        ).with_for_update())
        page_url = f"https://www.facebook.com/{page.id}"
        if owned_source is None:
            db.add(ResearchSource(
                id=new_id(), company_id=company_id, group_id=group_id, connection_id=row.id,
                source_type="owned_facebook_page", name=page.name[:200], url=page_url,
                normalized_url=page_url, status="active", active=True, crawl_mode="legacy",
                crawl_page_limit=1000, render_mode="http_only", resource_hosts_json=[],
                collection_mode="meta_api", collection_post_limit=100, collection_status="not_started",
                schedule_enabled=False, next_due_at=None, created_by=user.id,
            ))
        else:
            owned_source.name = page.name[:200]
            owned_source.group_id = group_id
            owned_source.url = owned_source.normalized_url = page_url
            owned_source.active = True
            owned_source.status = "active"
        db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.page.connect",
                          entity_type="meta_page_connection", entity_id=row.id,
                          metadata_json={"page_id": row.page_id, "group_id": group_id, "token_fingerprint": row.token_fingerprint[:12]}))
        await db.flush()
    await db.commit()
    return _page_out(row)


@router.delete("/pages/{connection_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def disconnect_page(
    company_id: str, connection_id: str, user: User = Depends(current_user),
    membership=Depends(require_permission("connection:manage")), db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(MetaPageConnection).where(
        MetaPageConnection.company_id == company_id, MetaPageConnection.id == connection_id,
        MetaPageConnection.active.is_(True),
    ).with_for_update())
    if row is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy Fanpage đang kết nối.")
    if row.page_id != await db.scalar(select(Company.page_id).where(Company.id == company_id)):
        raise ApiProblem(409, "workspace_primary_page_required", "Page nhận diện workspace không thể ngắt tại đây; hãy thay token ở cài đặt doanh nghiệp.")
    row.active = False
    row.status = "needs_reconnect"
    row.encrypted_token = ""
    row.last_error_code = "disconnected_by_user"
    company = await db.get(Company, company_id)
    if company:
        company.page_connection_state = "needs_reconnect"
    row.metrics_schedule_enabled = False
    row.next_metrics_sync_at = None
    owned_sources = (await db.scalars(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.connection_id == row.id,
        ResearchSource.active.is_(True),
    ))).all()
    for source in owned_sources:
        source.schedule_enabled = False
        source.next_due_at = None
    sync_state = await db.scalar(select(MetaSyncState).where(
        MetaSyncState.company_id == company_id, MetaSyncState.page_id == row.page_id,
    ).with_for_update())
    if sync_state:
        sync_state.verified_at = None
        sync_state.updated_at = utcnow()
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.page.disconnect",
                      entity_type="meta_page_connection", entity_id=row.id,
                      metadata_json={"page_id": row.page_id}))
    await db.commit()
    return None


@router.get("/sources", response_model=list[ResearchSourceOut])
async def list_sources(
    company_id: str, group_id: str | None = None,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    statement = select(ResearchSource).where(ResearchSource.company_id == company_id, ResearchSource.active.is_(True))
    if group_id:
        await _tenant_group(db, company_id, group_id)
        statement = statement.where(ResearchSource.group_id == group_id)
    rows = (await db.scalars(statement.order_by(ResearchSource.created_at.desc()))).all()
    return [_source_out(row) for row in rows]


@router.post("/sources", response_model=ResearchSourceOut, status_code=201,
            dependencies=[Depends(require_csrf)])
async def create_source(
    company_id: str, request: ResearchSourceCreate,
    user: User = Depends(current_user), membership=Depends(require_permission("market:manage")),
    db: AsyncSession = Depends(get_db),
):
    group = (
        await _tenant_group(db, company_id, request.group_id, lock=True)
        if request.group_id
        else await _default_research_group(db, company_id)
    )
    source_count = int(await db.scalar(select(func.count(ResearchSource.id)).where(
        ResearchSource.company_id == company_id, ResearchSource.active.is_(True),
    )) or 0)
    if source_count >= MAX_SOURCES_PER_WORKSPACE:
        raise ApiProblem(409, "source_limit", f"Workspace chỉ lưu tối đa {MAX_SOURCES_PER_WORKSPACE} nguồn nghiên cứu.")
    try:
        normalized = canonicalize_url(request.url)
    except CrawlError as error:
        raise ApiProblem(422, error.code, str(error)) from None
    connection = None
    status = "active"
    collection_mode = "legacy"
    if request.source_type == "owned_facebook_page":
        if not request.connection_id:
            raise ApiProblem(422, "page_connection_required", "Chọn Fanpage đã kết nối cho nguồn này.")
        connection = await db.scalar(select(MetaPageConnection).where(
            MetaPageConnection.company_id == company_id,
            MetaPageConnection.group_id == group.id,
            MetaPageConnection.id == request.connection_id,
            MetaPageConnection.active.is_(True), MetaPageConnection.status == "verified",
        ))
        if connection is None:
            raise ApiProblem(422, "page_connection_invalid", "Fanpage không thuộc nhóm hoặc chưa được xác minh.")
        parsed = urlsplit(normalized)
        if (parsed.hostname or "").casefold() not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
            raise ApiProblem(422, "facebook_url_required", "Nguồn Fanpage cần là liên kết facebook.com.")
        normalized = f"https://www.facebook.com/{connection.page_id}"
        status = "needs_privacy_policy"
    elif request.source_type == "competitor_facebook_page":
        try:
            normalized = normalize_facebook_page_url(normalized)
        except CrawlError as error:
            raise ApiProblem(422, error.code, str(error)) from None
        # A user-selected public collector uses the pinned facebook-cli Tier 0 runner.
        # Availability and access outcome are recorded by the first durable worker run.
        collection_mode = "public_web"
        status = "needs_privacy_policy"
    elif request.source_type == "facebook_group":
        parsed = urlsplit(normalized)
        host = (parsed.hostname or "").casefold()
        match = FACEBOOK_GROUP_PATH_RE.fullmatch(parsed.path)
        if host not in {"facebook.com", "www.facebook.com", "m.facebook.com"} or match is None:
            raise ApiProblem(
                422, "facebook_group_url_required",
                "Nhập trang chủ nhóm dạng https://www.facebook.com/groups/{id-hoặc-slug}.",
            )
        normalized = f"https://www.facebook.com/groups/{match.group(1)}"
        collection_mode = "public_web"
        status = "needs_privacy_policy"
    else:
        connection = None
    now = utcnow()
    row = ResearchSource(
        id=new_id(), company_id=company_id, group_id=group.id,
        connection_id=connection.id if connection else None,
        source_type=request.source_type, name=request.name, url=normalized, normalized_url=normalized,
        competitor_name=request.competitor_name, status=status, active=True,
        crawl_mode="site_catalog" if request.source_type == "website" else "legacy",
        crawl_page_limit=1000, render_mode="http_only", resource_hosts_json=[], schedule_enabled=True,
        collection_mode=collection_mode, collection_post_limit=50,
        collection_status="privacy_policy_required" if status == "needs_privacy_policy" else "not_started",
        next_due_at=now if status == "active" else None, created_by=user.id,
    )
    db.add(row)
    group.next_due_at = now
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.source.create",
                      entity_type="research_source", entity_id=row.id,
                      metadata_json={"source_type": row.source_type, "url_host": urlsplit(normalized).hostname,
                                     "collection_mode": row.collection_mode}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiProblem(409, "source_exists", "Liên kết này đã có trong nhóm nguồn.") from None
    return _source_out(row)


@router.delete("/sources/{source_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_source(
    company_id: str, source_id: str, user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await membership_for(company_id, user, db)
    _require_market_manager(membership)
    row = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id, ResearchSource.id == source_id,
        ResearchSource.active.is_(True),
    ).with_for_update())
    if row is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn nghiên cứu.")
    row.active = False
    row.status = "disabled"
    row.next_due_at = None
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.source.disable",
                      entity_type="research_source", entity_id=row.id,
                      metadata_json={"source_type": row.source_type}))
    await db.commit()
    return None


@router.post(
    "/sources/{source_id}/purge-collected-data",
    response_model=AcceptedResponse,
    status_code=202,
    dependencies=[Depends(require_csrf)],
)
async def purge_source_collected_data(
    company_id: str,
    source_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue removal of source-collected research rows and derived reports.

    This action is deliberately distinct from disabling a source. It does not
    certify legal erasure of copies already exported, published, or retained by
    external providers/backups.
    """
    membership = await membership_for(company_id, user, db)
    if membership.role != "owner":
        raise ApiProblem(403, "owner_required", "Chỉ Owner mới được yêu cầu xóa dữ liệu thu thập của nguồn này.")

    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.id == source_id,
    ).with_for_update())
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn nghiên cứu.")

    existing = await db.scalar(select(ResearchSourceErasure).where(
        ResearchSourceErasure.company_id == company_id,
        ResearchSourceErasure.source_id == source_id,
    ))
    if existing is not None:
        job = await db.scalar(select(Job).where(Job.company_id == company_id, Job.id == existing.job_id))
        if job is None:
            raise ApiProblem(409, "purge_job_missing", "Không tìm thấy tiến trình xóa dữ liệu đã tạo.")
        return await accepted_response(db, job)
    if source.status == "erased":
        raise ApiProblem(409, "source_already_purged", "Dữ liệu thu thập của nguồn này đã được xóa.")

    now = utcnow()
    source.active = False
    source.status = "erasure_pending"
    source.collection_status = "erasure_pending"
    source.schedule_enabled = False
    source.next_due_at = None
    source.error_json = None

    job = Job(
        id=new_id(), company_id=company_id, created_by=user.id,
        kind="research_source_erasure", title="Xóa dữ liệu đã thu thập từ nguồn nghiên cứu",
        status="queued", progress=0,
        result={"source_id": source.id, "phase": "queued"},
        idempotency_key=f"research-source-erasure:{source.id}",
    )
    db.add(job)
    await db.flush()
    erasure = ResearchSourceErasure(
        id=new_id(), company_id=company_id, source_id=source.id, job_id=job.id,
        requested_by=user.id, status="queued",
    )
    db.add(erasure)
    db.add(JobStep(
        job_id=job.id, step_key="purge_source_data", label="Xóa dữ liệu thu thập và vô hiệu báo cáo",
        status="pending",
    ))
    db.add(AuditEvent(
        company_id=company_id, actor_user_id=user.id, action="market.source.purge_requested",
        entity_type="research_source_erasure", entity_id=erasure.id,
        metadata_json={"source_type": source.source_type, "scope": "collected_source_data_and_reports"},
    ))
    await db.commit()

    sent = await dispatch_research_source_erasure_job(job.id)
    job.dispatch_attempts += 1
    job.last_dispatch_at = now
    job.last_dispatch_error = None if sent else "queue_unavailable"
    await db.commit()
    return await accepted_response(db, job)


def _privacy_policy_out(source_id: str, row: ResearchPrivacyPolicyRevision | None) -> ResearchPrivacyPolicyOut:
    if row is None:
        return ResearchPrivacyPolicyOut(source_id=source_id, configured=False, collection_ready=False)
    return ResearchPrivacyPolicyOut(
        source_id=source_id,
        configured=True,
        collection_ready=bool(row.purpose.strip() and row.processing_basis_reference.strip()),
        legal_basis_verified=False,
        revision_no=row.revision_no,
        purpose=row.purpose,
        processing_basis_reference=row.processing_basis_reference,
        policy_version=row.policy_version,
        requested_retention_days=row.requested_retention_days,
        configured_by=row.configured_by,
        configured_at=row.configured_at,
    )


async def _resume_source_after_policy(db: AsyncSession, source: ResearchSource, now: datetime) -> None:
    if not source.active or source.status != "needs_privacy_policy":
        return
    source.status = "active"
    source.collection_status = "not_started"
    source.error_json = None
    if source.schedule_enabled:
        source.next_due_at = now
        group = await db.scalar(select(MetaPageGroup).where(
            MetaPageGroup.company_id == source.company_id,
            MetaPageGroup.id == source.group_id,
        ).with_for_update())
        if group is not None:
            group.next_due_at = now


@router.get("/sources/{source_id}/privacy-policy", response_model=ResearchPrivacyPolicyOut)
async def get_source_privacy_policy(
    company_id: str,
    source_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.id == source_id,
    ))
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn nghiên cứu.")
    row = await db.scalar(select(ResearchPrivacyPolicyRevision).where(
        ResearchPrivacyPolicyRevision.company_id == company_id,
        ResearchPrivacyPolicyRevision.source_id == source_id,
    ).order_by(ResearchPrivacyPolicyRevision.revision_no.desc()).limit(1))
    return _privacy_policy_out(source_id, row)


@router.put("/sources/{source_id}/privacy-policy", response_model=ResearchPrivacyPolicyOut,
           dependencies=[Depends(require_csrf)])
async def put_source_privacy_policy(
    company_id: str,
    source_id: str,
    request: ResearchPrivacyPolicyUpdate,
    user: User = Depends(current_user),
    membership=Depends(require_permission("connection:manage")),
    db: AsyncSession = Depends(get_db),
):
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.id == source_id,
    ).with_for_update())
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn nghiên cứu.")
    row = await db.scalar(select(ResearchPrivacyPolicyRevision).where(
        ResearchPrivacyPolicyRevision.company_id == company_id,
        ResearchPrivacyPolicyRevision.source_id == source_id,
    ).order_by(ResearchPrivacyPolicyRevision.revision_no.desc()).limit(1).with_for_update())
    now = utcnow()
    if row is not None and (
        row.purpose == request.purpose
        and row.processing_basis_reference == request.processing_basis_reference
        and row.policy_version == request.policy_version
        and row.requested_retention_days == request.requested_retention_days
    ):
        await _resume_source_after_policy(db, source, now)
        await db.commit()
        return _privacy_policy_out(source_id, row)
    revision_no = 1 if row is None else row.revision_no + 1
    row = ResearchPrivacyPolicyRevision(
        id=new_id(),
        company_id=company_id,
        source_id=source_id,
        revision_no=revision_no,
        purpose=request.purpose,
        processing_basis_reference=request.processing_basis_reference,
        policy_version=request.policy_version,
        requested_retention_days=request.requested_retention_days,
        configured_by=user.id,
        configured_at=now,
    )
    db.add(row)
    await _resume_source_after_policy(db, source, now)
    db.add(AuditEvent(
        company_id=company_id,
        actor_user_id=user.id,
        action="market.privacy_policy.record",
        entity_type="research_privacy_policy",
        entity_id=source_id,
        metadata_json={
            "policy_version": request.policy_version,
            "requested_retention_days": request.requested_retention_days,
            "enforcement_status": "not_enforced",
            "comment_processing_status": "privacy_hold",
        },
    ))
    await db.commit()
    await db.refresh(row)
    return _privacy_policy_out(source_id, row)


@router.post("/groups/{group_id}/crawl", response_model=AcceptedResponse,
            status_code=202, dependencies=[Depends(require_csrf)])
async def crawl_group_now(
    company_id: str, group_id: str, user: User = Depends(current_user),
    membership=Depends(require_permission("market:manage")),
    _rate_limit: None = Depends(rate_limit("market_research_crawl", max_requests=6, window_seconds=3600)),
    db: AsyncSession = Depends(get_db),
):
    group = await _tenant_group(db, company_id, group_id, lock=True)
    existing = await db.scalar(select(ResearchCycle).where(
        ResearchCycle.company_id == company_id, ResearchCycle.group_id == group.id,
        ResearchCycle.status.in_(["queued", "running"]),
    ))
    if existing:
        job = await db.get(Job, existing.job_id)
        if job:
            return await accepted_response(db, job)
    if not await db.scalar(select(ResearchSource.id).where(
        ResearchSource.company_id == company_id, ResearchSource.group_id == group.id,
        ResearchSource.active.is_(True),
    ).limit(1)):
        raise ApiProblem(409, "no_research_sources", "Thêm ít nhất một nguồn trước khi bắt đầu thu thập.")
    now = utcnow()
    key = f"manual:{now.strftime('%Y%m%d%H%M')}"
    job = Job(id=new_id(), company_id=company_id, created_by=user.id, kind="market_research",
              title=f"Thu thập dữ liệu thị trường: {group.name}", status="queued", progress=0,
              result={"group_id": group.id}, idempotency_key=f"market:{group.id}:{key}")
    db.add(job)
    await db.flush()
    db.add(JobStep(job_id=job.id, step_key="collect_sources", label="Đọc nguồn công khai và Fanpage đã kết nối", status="pending"))
    cycle = ResearchCycle(id=new_id(), company_id=company_id, group_id=group.id, job_id=job.id,
                          cycle_key=key, status="queued", source_results_json=[])
    db.add(cycle)
    group.next_due_at = None
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.cycle.request",
                      entity_type="research_cycle", entity_id=cycle.id,
                      metadata_json={"group_id": group.id, "manual": True}))
    await db.commit()
    await dispatch_research_job(job.id)
    return await accepted_response(db, job)


@router.post("/sources/{source_id}/import", status_code=201, dependencies=[Depends(require_csrf)])
async def import_source_observations(
    company_id: str, source_id: str, request: ManualImportIn,
    user: User = Depends(current_user), membership=Depends(require_permission("market:manage")),
    db: AsyncSession = Depends(get_db),
):
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id, ResearchSource.id == source_id,
        ResearchSource.active.is_(True),
    ).with_for_update())
    if source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn nghiên cứu.")
    if source.source_type == "website":
        raise ApiProblem(409, "manual_import_not_allowed", "Nguồn web đang được thu thập tự động.")
    if source.source_type in {"owned_facebook_page", "competitor_facebook_page", "facebook_group"}:
        policy = await db.scalar(select(ResearchPrivacyPolicyRevision).where(
            ResearchPrivacyPolicyRevision.company_id == company_id,
            ResearchPrivacyPolicyRevision.source_id == source.id,
        ).order_by(ResearchPrivacyPolicyRevision.revision_no.desc()).limit(1))
        if policy is None or not policy.purpose.strip() or not policy.processing_basis_reference.strip():
            raise ApiProblem(
                409,
                "privacy_policy_required",
                "Ghi nhận mục đích và tài liệu tham chiếu căn cứ xử lý trước khi nhập dữ liệu Facebook.",
            )
    now = utcnow()
    created = 0
    withheld_comments = 0
    for item in request.rows:
        try:
            canonical = canonicalize_url(item.url)
        except CrawlError as error:
            raise ApiProblem(422, error.code, str(error)) from None
        text, content_redaction = redact_facebook_text(item.text)
        text = text[:12000]
        title, title_redaction = redact_facebook_text(item.title)
        title = title[:1000]
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
        evidence = await db.scalar(select(MarketEvidence).where(
            MarketEvidence.company_id == company_id, MarketEvidence.source_id == source.id,
            MarketEvidence.canonical_url == canonical,
        ).with_for_update())
        if evidence is None:
            evidence = MarketEvidence(
                id=new_id(), company_id=company_id, group_id=source.group_id, source_id=source.id,
                canonical_url=canonical, title=title, published_at=item.published_at,
                text=text, content_hash=fingerprint, trust_level="manual_external_unverified",
                first_seen_at=now, last_seen_at=now,
            )
            db.add(evidence)
            await db.flush()
        else:
            evidence.title = title or evidence.title
            evidence.text = text
            evidence.content_hash = fingerprint
            evidence.last_seen_at = now
            if item.published_at:
                evidence.published_at = item.published_at
        version = await ensure_evidence_version(
            db, evidence, title=title or evidence.title, text=text,
            published_at=item.published_at or evidence.published_at, captured_at=item.observed_at or now,
            parser_version="manual-import-v1",
        )
        metrics = {
            key: value for key, value in item.metrics.items()
            if value is None or (type(value) in {int, float} and math.isfinite(value) and value >= 0)
        }
        metrics["privacy_redaction"] = {
            "content": content_redaction,
            "title": title_redaction,
        }
        observed = item.observed_at or now
        # Manual imports have no verified processing basis or complete
        # privacy/deletion controls yet. Keep aggregate comment counts in
        # metrics, but do not persist comment text based on regex masking.
        comments, withheld_count = hold_comment_text(item.comments)
        withheld_comments += withheld_count
        observation = await db.scalar(select(MarketObservation).where(
            MarketObservation.company_id == company_id, MarketObservation.evidence_id == evidence.id,
            MarketObservation.observed_at == observed,
        ).with_for_update())
        if observation is None:
            db.add(MarketObservation(
                company_id=company_id, evidence_id=evidence.id, observed_at=observed,
                evidence_version_id=version.id,
                metrics_json=metrics, comments_json=comments,
            ))
        else:
            if observation.evidence_version_id != version.id:
                raise ApiProblem(
                    409, "observation_version_conflict",
                    "Thời điểm này đã được lưu với nội dung khác; hãy nhập lại với thời điểm quan sát chính xác.",
                )
            if observation.metrics_json != metrics or observation.comments_json != comments:
                raise ApiProblem(
                    409, "observation_snapshot_conflict",
                    "Snapshot tại thời điểm này đã tồn tại và không thể sửa; hãy dùng thời điểm quan sát mới.",
                )
        if source.source_type != "owned_facebook_page":
            followers = item.metrics.get("followers")
            members = item.metrics.get("members")
            followers = followers if type(followers) is int and followers >= 0 else None
            members = members if type(members) is int and members >= 0 else None
            if "followers" in item.metrics or "members" in item.metrics:
                key = f"manual:{source.id}:{observed.isoformat()}"
                snapshot = await db.scalar(select(ResearchSourceMetricSnapshot).where(
                    ResearchSourceMetricSnapshot.company_id == company_id,
                    ResearchSourceMetricSnapshot.source_id == source.id,
                    ResearchSourceMetricSnapshot.snapshot_key == key,
                ).with_for_update())
                missing = [name for name, value in (("followers", followers), ("members", members)) if value is None]
                if snapshot is None:
                    db.add(ResearchSourceMetricSnapshot(
                        company_id=company_id, source_id=source.id, snapshot_key=key,
                        observed_at=observed, source="manual_import",
                        metric_definition="source_audience_v1", followers=followers,
                        members=members, missing_metrics_json=missing,
                    ))
                elif (snapshot.followers != followers or snapshot.members != members
                      or snapshot.missing_metrics_json != missing):
                    raise ApiProblem(
                        409, "audience_snapshot_conflict",
                        "Snapshot quy mô nguồn đã tồn tại và không thể sửa; hãy dùng thời điểm đo mới.",
                    )
        created += 1
    source.last_crawled_at = now
    source.status = "manual_import_only" if source.source_type != "owned_facebook_page" else "active"
    source.error_json = None
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.source.import",
                      entity_type="research_source", entity_id=source.id,
                      metadata_json={"rows": created, "comments_withheld_count": withheld_comments,
                                     "comments_content_status": "privacy_hold"}))
    await db.commit()
    return {
        "imported": created,
        "observed_at": now,
        "comments_content_status": "privacy_hold",
        "comments_withheld_count": withheld_comments,
    }


@router.get("/reports", response_model=list[ResearchReportOut])
async def list_workspace_reports(
    company_id: str, request: Request,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    """Workspace-level report facade; legacy storage remains group-scoped."""
    await membership_for(company_id, user, db)
    group_ids = (await db.scalars(select(MetaPageGroup.id).where(
        MetaPageGroup.company_id == company_id,
    ).order_by(MetaPageGroup.created_at))).all()
    reports: list[ResearchReportOut] = []
    for group_id in group_ids:
        reports.extend(await list_reports(company_id, group_id, request, user, db))
    reports.sort(key=lambda report: report.created_at, reverse=True)
    return reports[:100]


@router.get("/ai-budget", response_model=ResearchAIBudgetOut)
async def get_workspace_ai_budget(
    company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    """Return the current automatic-AI budget without exposing provider usage details."""

    await membership_for(company_id, user, db)
    local_now = datetime.now(timezone.utc).astimezone(VN_TZ)
    budget_date = local_now.date()
    day = await db.get(AIUsageBudgetDay, (company_id, budget_date))
    configured_limit = min(
        int(getattr(settings, "auto_ai_daily_budget_micro_usd", 2_000_000)), 2_000_000,
    )
    limit = day.limit_micro_usd if day else configured_limit
    reserved = day.reserved_micro_usd if day else 0
    spent = day.spent_micro_usd if day else 0
    uncertain = int(await db.scalar(select(func.count(AIUsageLedger.id)).where(
        AIUsageLedger.company_id == company_id,
        AIUsageLedger.budget_class == "automatic",
        AIUsageLedger.budget_date == budget_date,
        AIUsageLedger.status.in_(["reserved", "unknown"]),
    )) or 0)
    pending = int(await db.scalar(select(func.count(MarketReport.id)).where(
        MarketReport.company_id == company_id,
        MarketReport.report_json["analysis_status"].as_string().in_([
            "deferred_budget", "provider_outcome_unknown", "deepseek_not_configured", "provider_not_configured",
            "pricing_unavailable", "input_limit_exceeded",
        ]),
    )) or 0)
    resets_at = datetime.combine(budget_date + timedelta(days=1), time.min, VN_TZ)
    return ResearchAIBudgetOut(
        budget_date=budget_date,
        resets_at=resets_at,
        limit_micro_usd=limit,
        reserved_micro_usd=reserved,
        spent_micro_usd=spent,
        available_micro_usd=max(0, limit - reserved - spent),
        unsettled_requests=uncertain,
        pending_reports=pending,
    )


@router.get("/groups/{group_id}/reports", response_model=list[ResearchReportOut])
async def list_reports(
    company_id: str, group_id: str, request: Request,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    await _tenant_group(db, company_id, group_id)
    revision = await db.execute(select(func.count(MarketReport.id), func.max(MarketReport.updated_at)).where(
        MarketReport.company_id == company_id, MarketReport.group_id == group_id,
    ))
    count, latest = revision.one()
    key = cache_key("market-reports", company_id,
                    f"{group_id}|{count}|{latest.isoformat() if latest else 'none'}")
    cache = getattr(request.app.state, "response_cache", None)
    cached = await get_json_cache(cache, key)
    if isinstance(cached, list):
        try:
            return [ResearchReportOut.model_validate(item) for item in cached]
        except ValueError:
            pass
    rows = (await db.scalars(select(MarketReport).where(
        MarketReport.company_id == company_id, MarketReport.group_id == group_id,
    ).order_by(MarketReport.created_at.desc()).limit(30))).all()
    output = []
    for row in rows:
        linked = (await db.execute(
            select(MarketReportEvidence, MarketEvidence, MarketEvidenceVersion, MarketObservation)
            .join(MarketEvidence, (MarketEvidence.company_id == MarketReportEvidence.company_id)
                  & (MarketEvidence.group_id == MarketReportEvidence.group_id)
                  & (MarketEvidence.id == MarketReportEvidence.evidence_id))
            .join(MarketEvidenceVersion, (MarketEvidenceVersion.company_id == MarketReportEvidence.company_id)
                  & (MarketEvidenceVersion.evidence_id == MarketReportEvidence.evidence_id)
                  & (MarketEvidenceVersion.id == MarketReportEvidence.evidence_version_id))
            .join(MarketObservation, (MarketObservation.company_id == MarketReportEvidence.company_id)
                  & (MarketObservation.evidence_id == MarketReportEvidence.evidence_id)
                  & (MarketObservation.id == MarketReportEvidence.observation_id)
                  & (MarketObservation.evidence_version_id == MarketReportEvidence.evidence_version_id))
            .where(MarketReportEvidence.company_id == company_id,
                   MarketReportEvidence.report_id == row.id)
            .order_by(MarketObservation.observed_at.desc())
        )).all()
        evidence_refs = [{
            "id": evidence.id,
            "title": version.title,
            "url": evidence.canonical_url,
            "observed_at": observation.observed_at,
            "evidence_version_id": version.id,
            "observation_id": observation.id,
            "content_hash": version.content_hash,
            "provenance_status": "verified",
        } for _link, evidence, version, observation in linked]
        report_json = row.report_json if isinstance(row.report_json, dict) else {}
        coverage = dict(row.coverage_json or {})
        coverage["provenance_status"] = (
            "verified" if len(evidence_refs) == len(row.evidence_ids_json or []) and evidence_refs
            else "legacy_unverifiable" if row.evidence_ids_json
            else "no_evidence"
        )
        output.append(ResearchReportOut(
            id=row.id, group_id=row.group_id, window_start=row.window_start,
            window_end=row.window_end, report=report_json,
            evidence_ids=row.evidence_ids_json, coverage=coverage,
            model_name=row.model_name, created_at=row.created_at,
            evidence_refs=evidence_refs,
            source_audience=report_json.get("source_audience", []),
        ))
    await set_json_cache(cache, key, [item.model_dump(mode="json") for item in output], 300)
    return output


@router.post("/reports/{report_id}/draft", status_code=201, dependencies=[Depends(require_csrf)])
async def create_draft_from_report(
    company_id: str, report_id: str, request: DraftFromReportIn,
    user: User = Depends(current_user), membership=Depends(require_permission("campaign:create")),
    db: AsyncSession = Depends(get_db),
):
    # The campaign workflow owns campaign DTO validation and drafting. Keep this
    # action explicit: a report never creates or publishes content by itself.
    report = await db.scalar(select(MarketReport).where(
        MarketReport.company_id == company_id, MarketReport.id == report_id,
    ))
    if report is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy báo cáo thị trường.")
    report_json = report.report_json if isinstance(report.report_json, dict) else {}
    suggestions = report_json.get("suggestions", [])
    if request.suggestion_index >= len(suggestions):
        raise ApiProblem(422, "suggestion_not_found", "Không tìm thấy đề xuất đã chọn trong báo cáo.")
    suggestion = suggestions[request.suggestion_index]
    if not isinstance(suggestion, dict):
        raise ApiProblem(422, "suggestion_invalid", "Đề xuất trong báo cáo không đúng định dạng.")
    raw_ids = suggestion.get("evidence_ids", [])
    if not isinstance(raw_ids, list) or any(not isinstance(item, str) for item in raw_ids):
        raise ApiProblem(422, "suggestion_invalid", "Danh sách nguồn trong đề xuất không đúng định dạng.")
    valid_ids = set(report.evidence_ids_json or [])
    selected_ids = list(dict.fromkeys(raw_ids))
    if any(item not in valid_ids for item in selected_ids):
        raise ApiProblem(409, "report_evidence_unavailable", "Báo cáo tham chiếu nguồn không còn thuộc phiên phân tích này.")

    report_refs = report_json.get("evidence_refs", [])
    refs_by_id = {
        item.get("id"): item for item in report_refs
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(report_refs, list) else {}
    if any(
        not isinstance(refs_by_id.get(evidence_id), dict)
        or not isinstance(refs_by_id[evidence_id].get("evidence_version_id"), str)
        or not isinstance(refs_by_id[evidence_id].get("observation_id"), str)
        for evidence_id in selected_ids
    ):
        raise ApiProblem(409, "report_evidence_unavailable", "Báo cáo này chưa có phiên bản nguồn cố định. Hãy tạo báo cáo nghiên cứu mới.")

    pinned_rows = (await db.execute(
        select(MarketReportEvidence, MarketEvidence, MarketEvidenceVersion, MarketObservation)
        .join(MarketEvidence, (MarketEvidence.company_id == MarketReportEvidence.company_id)
              & (MarketEvidence.group_id == MarketReportEvidence.group_id)
              & (MarketEvidence.id == MarketReportEvidence.evidence_id))
        .join(MarketEvidenceVersion, (MarketEvidenceVersion.company_id == MarketReportEvidence.company_id)
              & (MarketEvidenceVersion.evidence_id == MarketReportEvidence.evidence_id)
              & (MarketEvidenceVersion.id == MarketReportEvidence.evidence_version_id))
        .join(MarketObservation, (MarketObservation.company_id == MarketReportEvidence.company_id)
              & (MarketObservation.evidence_id == MarketReportEvidence.evidence_id)
              & (MarketObservation.id == MarketReportEvidence.observation_id)
              & (MarketObservation.evidence_version_id == MarketReportEvidence.evidence_version_id))
        .where(
            MarketReportEvidence.company_id == company_id,
            MarketReportEvidence.group_id == report.group_id,
            MarketReportEvidence.report_id == report.id,
            MarketReportEvidence.evidence_id.in_(selected_ids or ["__none__"]),
        )
    )).all()
    rows_by_pin = {
        (evidence.id, version.id, observation.id): (evidence, version, observation)
        for _link, evidence, version, observation in pinned_rows
    }
    sources = []
    for evidence_id in selected_ids:
        reference = refs_by_id[evidence_id]
        pin = (evidence_id, reference["evidence_version_id"], reference["observation_id"])
        row = rows_by_pin.get(pin)
        if row is None:
            raise ApiProblem(409, "report_evidence_unavailable", "Một nguồn hoặc snapshot của báo cáo không còn khả dụng.")
        evidence, version, observation = row
        sources.append({
            "id": evidence.id,
            "title": version.title,
            "url": evidence.canonical_url,
            "published_at": version.published_at.isoformat() if version.published_at else None,
            "evidence_version_id": version.id,
            "observation_id": observation.id,
            "content_hash": version.content_hash,
            "observed_at": observation.observed_at.isoformat(),
            "metrics": observation.metrics_json if isinstance(observation.metrics_json, dict) else {},
        })

    raw_web_ids = suggestion.get("web_snapshot_ids", [])
    if not isinstance(raw_web_ids, list) or any(not isinstance(item, str) for item in raw_web_ids):
        raise ApiProblem(422, "suggestion_invalid", "Danh sách snapshot website trong đề xuất không đúng định dạng.")
    selected_web_ids = list(dict.fromkeys(raw_web_ids))
    if len(selected_ids) + len(selected_web_ids) > 10:
        raise ApiProblem(422, "suggestion_invalid", "Hướng viết có quá 10 nguồn; hãy chọn hướng có phạm vi hẹp hơn.")
    if selected_web_ids:
        linked_web_ids = set((await db.scalars(select(MarketReportWebSnapshot.snapshot_id).where(
            MarketReportWebSnapshot.company_id == company_id,
            MarketReportWebSnapshot.report_id == report.id,
            MarketReportWebSnapshot.snapshot_id.in_(selected_web_ids),
        ))).all())
        if linked_web_ids != set(selected_web_ids):
            raise ApiProblem(409, "report_snapshot_unavailable", "Một snapshot website trong đề xuất không còn thuộc báo cáo này.")
    group = await _tenant_group(db, company_id, report.group_id)
    today = utcnow().date()
    slot_date = today + timedelta(days=1)
    supported_formats = {"text", "image", "carousel", "video", "reel", "story"}
    slot_format = suggestion.get("format") if suggestion.get("format") in supported_formats else "text"
    campaign_id = new_id()
    slot_id = new_id()
    title = str(suggestion.get("title") or "Nội dung theo xu hướng thị trường")[:200]
    angle = str(suggestion.get("angle") or "")[:1000]
    hook = str(suggestion.get("hook") or "")[:500]
    reference_lines = "\n".join(f"- {item['title']}: {item['url']}" for item in sources)
    strategy = (
        f"Góc nội dung người dùng chọn: {title}. {angle} "
        f"Gợi ý mở bài: {hook}. Dữ liệu thị trường là nguồn bên ngoài chưa xác minh; "
        "dùng để hiểu chủ đề/định dạng được quan tâm, không biến thành sự thật về sản phẩm hoặc thương hiệu. "
        f"Nguồn tham khảo:\n{reference_lines}"
    )[:5000]
    brief = {
        "objective": "engagement",
        "objective_note": f"Tạo tương tác cho chủ đề: {title}",
        "audience": _explicit_group_audience(group),
        "product_ids": [],
        "key_message": angle or title,
        "must_include": [],
        "must_avoid": [],
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=14)).isoformat(),
        "market_research_context": {
            "report_id": report.id, "group_id": group.id, "suggestion": suggestion,
            "evidence": sources, "web_snapshot_ids": selected_web_ids,
            "business_profile_context": (
                report_json.get("business_profile_context")
                if isinstance(report_json.get("business_profile_context"), dict)
                else {"status": "legacy_unknown"}
            ),
            "trust_level": "external_unverified",
        },
    }
    campaign = Campaign(
        id=campaign_id, company_id=company_id, group_id=group.id, name=title,
        status="draft", brief_json=brief,
        content_plan_json={
            "strategy_summary": strategy,
            "slots": [{
                "id": slot_id, "scheduled_date": slot_date.isoformat(), "pillar": "education",
                "format": slot_format, "topic": title,
            }],
        },
        pillars_json=["education"],
        channels_json=["facebook_page"], version=1, created_by=user.id,
    )
    db.add(campaign)
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="market.suggestion.create_draft",
                      entity_type="campaign", entity_id=campaign.id,
                      metadata_json={"report_id": report.id, "suggestion_index": request.suggestion_index,
                                     "evidence_ids": selected_ids,
                                     "evidence_version_ids": [item["evidence_version_id"] for item in sources],
                                     "observation_ids": [item["observation_id"] for item in sources],
                                     "web_snapshot_ids": selected_web_ids, "group_id": group.id}))
    await db.commit()
    return {
        "campaign_id": campaign.id, "group_id": campaign.group_id, "report_id": report.id,
        "suggestion": suggestion, "evidence": sources,
        "message": "Đã tạo chiến dịch nháp. Mở chiến dịch để xem lại và yêu cầu AI sinh bài.",
    }
