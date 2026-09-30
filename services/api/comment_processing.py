"""Owner decisions for bounded local comment quarantine, never AI approval.

Candidate bodies are available only through the bounded Owner review route;
Page tokens and personal author identities are never returned.
An operator's recorded assessment is not a platform legal certification or
commenter consent. It only scopes the existing local quarantine executor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AuditEvent, Company, Job, MarketEvidence, MarketObservation, Membership, MetaPageConnection, ResearchCommentCheckpoint,
    ResearchCommentProcessingDecision, ResearchCommentVersion, ResearchPrivacyPolicyRevision,
    ResearchSource, User, new_id, utcnow,
)
from services.research.comment_quarantine import CommentQuarantineUnavailable, decrypt_candidate, encrypt_candidate
from services.research.facebook_cli_collector import safe_comment_coverage, safe_reaction_breakdown
from services.research.public_comments import active_public_comment_decision
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .market_research_schemas import CommentProcessingIn, CommentProcessingOut, CommentProcessingRevokeIn, CommentCandidatesPage, CommentCandidateOut


router = APIRouter(prefix="/workspaces/{company_id}/market-research", tags=["market-research"])
DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
Owner = Annotated[Membership, Depends(require_permission("connection:manage"))]


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _source(db: AsyncSession, company_id: str, source_id: str, *, lock: bool = False):
    # Match the executor's company -> source -> decision lock order.
    company_query = select(Company).where(Company.id == company_id)
    source_query = select(ResearchSource).where(ResearchSource.company_id == company_id, ResearchSource.id == source_id)
    if lock:
        company_query = company_query.with_for_update()
        source_query = source_query.with_for_update()
    company = await db.scalar(company_query)
    source = await db.scalar(source_query)
    if company is None or source is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy nguồn nghiên cứu.")
    return company, source


async def _latest(db: AsyncSession, company_id: str, source_id: str, *, lock: bool = False):
    query = select(ResearchCommentProcessingDecision).where(
        ResearchCommentProcessingDecision.company_id == company_id,
        ResearchCommentProcessingDecision.source_id == source_id,
    ).order_by(ResearchCommentProcessingDecision.created_at.desc(), ResearchCommentProcessingDecision.id.desc()).limit(1)
    return await db.scalar(query.with_for_update() if lock else query)


async def _policy(db: AsyncSession, source: ResearchSource):
    return await db.scalar(select(ResearchPrivacyPolicyRevision).where(
        ResearchPrivacyPolicyRevision.company_id == source.company_id,
        ResearchPrivacyPolicyRevision.source_id == source.id,
    ).order_by(ResearchPrivacyPolicyRevision.revision_no.desc()).limit(1))


async def _active_connection(db: AsyncSession, company: Company, source: ResearchSource) -> bool:
    if company.page_connection_state != "active" or not company.page_id:
        return False
    if source.source_type == "competitor_facebook_page":
        return source.collection_mode == "public_web"
    return bool(await db.scalar(select(MetaPageConnection.id).where(
        MetaPageConnection.company_id == company.id, MetaPageConnection.id == source.connection_id,
        MetaPageConnection.page_id == company.page_id, MetaPageConnection.status == "verified",
        MetaPageConnection.active.is_(True), MetaPageConnection.verified_at.is_not(None),
        MetaPageConnection.encrypted_token.is_not(None),
    )))


def _require_encryption() -> None:
    try:
        # Validate the persistent cipher without decrypting any token/content.
        encrypt_candidate("", binding={"scope": "configuration-validation"})
    except CommentQuarantineUnavailable:
        raise ApiProblem(409, "comment_quarantine_unavailable", "Backend chưa sẵn sàng mã hóa vùng xử lý bình luận.") from None


async def _out(db: AsyncSession, company: Company, source: ResearchSource, decision) -> CommentProcessingOut:
    supported = source.source_type == "owned_facebook_page" or (source.source_type == "competitor_facebook_page" and source.collection_mode == "public_web")
    policy = await _policy(db, source)
    status = "unsupported" if not supported else "not_configured"
    if supported and decision is not None:
        status = decision.status
        if status == "active":
            if _aware(decision.valid_until) <= utcnow():
                status = "expired"
            elif policy is None or policy.id != decision.policy_revision_id:
                status = "policy_changed"
            elif not source.active:
                status = "source_unavailable"
            elif not await _active_connection(db, company, source):
                status = "page_unavailable"
            elif not await db.scalar(select(Membership.id).where(
                Membership.company_id == company.id, Membership.user_id == decision.assessed_by,
                Membership.role == "owner", Membership.is_active.is_(True),
            )):
                status = "assessor_unavailable"
            else:
                try:
                    _require_encryption()
                except ApiProblem:
                    status = "engine_unavailable"
    counts = (await db.execute(select(
        func.count(ResearchCommentVersion.id),
        func.count(ResearchCommentVersion.id).filter(
            ResearchCommentVersion.candidate_ciphertext.is_not(None), ResearchCommentVersion.expires_at > utcnow(),
        ),
    ).where(ResearchCommentVersion.company_id == company.id, ResearchCommentVersion.source_id == source.id))).one()
    pending = await db.scalar(select(func.count(ResearchCommentCheckpoint.id)).where(
        ResearchCommentCheckpoint.company_id == company.id, ResearchCommentCheckpoint.source_id == source.id,
        ResearchCommentCheckpoint.pagination_exhausted.is_(False),
        ResearchCommentCheckpoint.status.in_(["privacy_hold", "queued", "partial"]),
    ))
    job_id = await db.scalar(select(Job.id).where(
        Job.company_id == company.id, Job.kind == "research_comments", Job.status.in_(["queued", "running"]),
        Job.result["source_id"].as_string() == source.id,
    ).order_by(Job.created_at.desc()).limit(1))
    return CommentProcessingOut(
        source_id=source.id, supported=supported, effective_status=status, collection_allowed=status == "active",
        decision_id=decision.id if decision else None, status=decision.status if decision else None,
        policy_revision_no=policy.revision_no if policy else None,
        assessment_reference=decision.assessment_reference if decision else None,
        assessed_by=decision.assessed_by if decision else None,
        created_at=decision.created_at if decision else None, valid_until=decision.valid_until if decision else None,
        candidate_versions_count=counts[0], quarantined_candidate_versions_count=counts[1],
        pending_edges=int(pending or 0), job_id=job_id,
    )


async def _expire_candidates(db: AsyncSession, source: ResearchSource) -> int:
    result = await db.execute(update(ResearchCommentVersion).where(
        ResearchCommentVersion.company_id == source.company_id, ResearchCommentVersion.source_id == source.id,
        ResearchCommentVersion.candidate_ciphertext.is_not(None),
    ).values(candidate_ciphertext=None, status="expired"))
    return result.rowcount


@router.get("/sources/{source_id}/comment-processing", response_model=CommentProcessingOut)
async def get_comment_processing(company_id: str, source_id: str, user: CurrentUser, db: DB):
    await membership_for(company_id, user, db)
    company, source = await _source(db, company_id, source_id)
    return await _out(db, company, source, await _latest(db, company_id, source_id))


@router.put("/sources/{source_id}/comment-processing", response_model=CommentProcessingOut,
            dependencies=[Depends(require_csrf)])
async def record_comment_processing(company_id: str, source_id: str, request: CommentProcessingIn,
                                    user: CurrentUser, owner: Owner, db: DB):
    company, source = await _source(db, company_id, source_id, lock=True)
    await _locked_owner(db, company_id, user.id)
    if source.source_type != "owned_facebook_page" and not (source.source_type == "competitor_facebook_page" and source.collection_mode == "public_web"):
        raise ApiProblem(409, "comment_collection_unsupported", "Bình luận dùng Meta API cho Page doanh nghiệp hoặc facebook-cli Tier 0 cho Page công khai.")
    policy = await _policy(db, source)
    if (policy is None or policy.revision_no != request.policy_revision_no
            or not policy.purpose.strip() or not policy.processing_basis_reference.strip()):
        raise ApiProblem(409, "comment_policy_changed", "Hãy ghi nhận mục đích/phạm vi nguồn và tải lại phiên bản chính sách trước khi tiếp tục.")
    latest = await _latest(db, company_id, source_id, lock=True)
    expires = _aware(request.valid_until)
    # A network-uncertain replay may repeat exactly the latest immutable input.
    if latest is not None and latest.policy_revision_id == policy.id and latest.assessed_by == user.id and (
        latest.assessment_reference == request.assessment_reference and latest.status == request.status
        and _aware(latest.valid_until) == expires
    ):
        return await _out(db, company, source, latest)
    if request.expected_decision_id != (latest.id if latest else None):
        raise ApiProblem(409, "comment_decision_conflict", "Phạm vi bình luận đã được thay đổi. Tải lại trước khi lưu.")
    now = utcnow()
    if not now < expires <= now + timedelta(days=30):
        raise ApiProblem(422, "comment_decision_expiry_invalid", "Thời hạn phải ở tương lai và trong 30 ngày. Đây là giới hạn vận hành, không phải thời hạn do luật ấn định.")
    if request.status == "active":
        if not source.active:
            raise ApiProblem(409, "comment_source_unavailable", "Nguồn đã ngừng theo dõi; không thể mở xử lý bình luận.")
        if not await _active_connection(db, company, source):
            raise ApiProblem(409, "page_needs_reconnect", "Owner cần kết nối lại đúng Fanpage trước khi mở xử lý bình luận.")
        _require_encryption()
    # Superseding a decision immediately invalidates its encrypted candidates.
    await db.execute(update(ResearchCommentProcessingDecision).where(
        ResearchCommentProcessingDecision.company_id == company_id,
        ResearchCommentProcessingDecision.source_id == source_id,
        ResearchCommentProcessingDecision.status.in_(["active", "pending"]),
    ).values(status="revoked"))
    removed = await _expire_candidates(db, source)
    decision = ResearchCommentProcessingDecision(
        id=new_id(), company_id=company_id, source_id=source_id, policy_revision_id=policy.id,
        assessment_reference=request.assessment_reference, status=request.status,
        assessed_by=user.id, created_at=now, valid_until=expires,
    )
    db.add(decision)
    db.add(AuditEvent(
        company_id=company_id, actor_user_id=user.id, action="research.comment_processing.record",
        entity_type="research_comment_processing_decision", entity_id=decision.id,
        metadata_json={"scope": decision.scope or "local_comment_quarantine_v1", "status": request.status,
                       "policy_revision_no": policy.revision_no, "removed_candidates": removed,
                       "provider_transmission_allowed": False},
    ))
    await db.commit()
    return await _out(db, company, source, decision)


@router.post("/sources/{source_id}/comment-processing/revoke", response_model=CommentProcessingOut,
             dependencies=[Depends(require_csrf)])
async def revoke_comment_processing(company_id: str, source_id: str, request: CommentProcessingRevokeIn,
                                    user: CurrentUser, owner: Owner, db: DB):
    company, source = await _source(db, company_id, source_id, lock=True)
    await _locked_owner(db, company_id, user.id)
    decision = await _latest(db, company_id, source_id, lock=True)
    if decision is None or request.expected_decision_id != decision.id:
        raise ApiProblem(409, "comment_decision_conflict", "Phạm vi bình luận đã được thay đổi. Tải lại trước khi thu hồi.")
    if decision.status != "revoked":
        decision.status = "revoked"
        removed = await _expire_candidates(db, source)
        db.add(AuditEvent(
            company_id=company_id, actor_user_id=user.id, action="research.comment_processing.revoke",
            entity_type="research_comment_processing_decision", entity_id=decision.id,
            metadata_json={"removed_candidates": removed, "provider_transmission_allowed": False},
        ))
        await db.commit()
    return await _out(db, company, source, decision)


async def _locked_owner(db, company_id, user_id):
    if not await db.scalar(select(Membership.id).where(
        Membership.company_id == company_id, Membership.user_id == user_id,
        Membership.role == "owner", Membership.is_active.is_(True),
    ).with_for_update()):
        raise ApiProblem(403, "forbidden", "Chỉ Owner đang hoạt động được quản lý xử lý bình luận.")


@router.get("/sources/{source_id}/posts/{evidence_id}/comments", response_model=CommentCandidatesPage)
async def comment_candidates(company_id: str, source_id: str, evidence_id: str, response: Response,
                             user: CurrentUser, owner: Owner, db: DB, limit: int = 25,
                             cursor: str | None = None):
    from .market_research import _decode_web_cursor, _encode_web_cursor
    company, source = await _source(db, company_id, source_id, lock=True)
    await _locked_owner(db, company_id, user.id)
    if not 1 <= limit <= 100:
        raise ApiProblem(422, "invalid_limit", "Giới hạn cần nằm trong khoảng 1 đến 100.")
    evidence = await db.scalar(select(MarketEvidence).where(
        MarketEvidence.company_id == company_id, MarketEvidence.source_id == source_id,
        MarketEvidence.id == evidence_id,
    ))
    if evidence is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy bài viết của nguồn này.")
    observation = await db.scalar(select(MarketObservation).where(
        MarketObservation.company_id == company_id, MarketObservation.evidence_id == evidence.id,
    ).order_by(MarketObservation.observed_at.desc(), MarketObservation.id.desc()).limit(1))
    metrics = observation.metrics_json if observation else {}
    coverage = safe_comment_coverage(metrics.get("comment_coverage"))
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    decision = await active_public_comment_decision(db, source, lock=True)
    if decision is None or observation is None:
        return CommentCandidatesPage(source_id=source_id, evidence_id=evidence_id,
            observation_id=observation.id if observation else None, status="processing_required", coverage=coverage)
    now = utcnow()
    query = select(ResearchCommentVersion).where(
        ResearchCommentVersion.company_id == company_id, ResearchCommentVersion.source_id == source_id,
        ResearchCommentVersion.observation_id == observation.id, ResearchCommentVersion.decision_id == decision.id,
        ResearchCommentVersion.status == "privacy_hold", ResearchCommentVersion.expires_at > now,
        ResearchCommentVersion.candidate_ciphertext.is_not(None),
    )
    if cursor:
        seen_at, version_id = _decode_web_cursor(cursor)
        anchor = await db.scalar(select(ResearchCommentVersion.id).where(
            ResearchCommentVersion.id == version_id, ResearchCommentVersion.company_id == company_id,
            ResearchCommentVersion.observation_id == observation.id,
        ))
        if anchor is None:
            raise ApiProblem(409, "comment_observation_changed", "Lượt quan sát đã thay đổi; tải lại danh sách bình luận.")
        query = query.where((ResearchCommentVersion.captured_at > seen_at) |
                           ((ResearchCommentVersion.captured_at == seen_at) & (ResearchCommentVersion.id > version_id)))
    rows = (await db.scalars(query.order_by(ResearchCommentVersion.captured_at, ResearchCommentVersion.id)
                            .limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    result = []
    for row in rows:
        binding = {"company_id": company_id, "source_id": source_id,
                   "observation_id": observation.id, "comment_id": row.external_comment_id}
        try:
            candidate = decrypt_candidate(row.candidate_ciphertext, binding=binding)
        except CommentQuarantineUnavailable:
            raise ApiProblem(503, "comment_quarantine_unavailable", "Không mở được vùng kiểm tra bình luận.") from None
        metadata = row.redaction_json or {}
        reactions = metadata.get("reactions")
        precision = metadata.get("reactions_precision")
        alias = metadata.get("author_alias")
        result.append(CommentCandidateOut(id=row.id, author_alias=alias, text=candidate,
            author_identity_known=metadata.get("author_identity_known") is True,
            likes=row.likes, reactions=reactions if type(reactions) is int and reactions >= 0 else None,
            reactions_raw=metadata.get("reactions_raw"),
            reactions_precision=precision if precision in {"exact", "approximate", "lower_bound"} else "unknown",
            reaction_breakdown=safe_reaction_breakdown(metadata.get("reaction_breakdown")),
            reply_count=row.reply_count, published_at=row.published_at, observed_at=row.captured_at,
            expires_at=row.expires_at, content_truncated=row.content_truncated))
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="research.comments.review_read",
        entity_type="market_observation", entity_id=observation.id,
        metadata_json={"records_returned": len(result), "provider_transmission_allowed": False}))
    await db.commit()
    return CommentCandidatesPage(source_id=source_id, evidence_id=evidence_id, observation_id=observation.id,
        status="privacy_hold" if result else "no_candidates", comments=result, coverage=coverage,
        next_cursor=_encode_web_cursor(rows[-1].captured_at, rows[-1].id) if has_more and rows else None)
