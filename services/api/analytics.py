"""Tenant-scoped manual metrics, descriptive analytics and cautious tests."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AnalyticsRecommendationRecord,
    AuditEvent,
    Campaign,
    CampaignBriefRevisionDraft,
    CampaignPost,
    PostMetricSnapshot,
    User,
    new_id,
    utcnow,
)
from services.agents.analytics.metrics import PostMetricInput, build_analytics_report
from .analytics_schemas import (
    AnalyticsDashboardOut,
    AnalyticsRecommendationRecordOut,
    ApplyRecommendationRequest,
    ApplyRecommendationResponse,
    CampaignBriefChangeOut,
    CampaignBriefRevisionDraftOut,
    MetricGroupOut,
    MetricImportRequest,
    MetricImportResponse,
    RecommendationDraftDecisionRequest,
    RecommendationFeedbackOut,
    RecommendationFeedbackRequest,
    RecommendationOut,
    SaveRecommendationRequest,
)
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem


router = APIRouter(tags=["analytics"])


async def _latest_points(
    db: AsyncSession,
    company_id: str,
    source_id: str,
    *,
    min_post_age_hours: int,
    max_post_age_hours: int,
    measured_from: datetime | None,
    measured_to: datetime | None,
) -> list[tuple[PostMetricSnapshot, CampaignPost]]:
    statement = (
        select(PostMetricSnapshot, CampaignPost)
        .join(CampaignPost, CampaignPost.id == PostMetricSnapshot.post_id)
        .where(
            PostMetricSnapshot.company_id == company_id,
            CampaignPost.company_id == company_id,
            PostMetricSnapshot.source_id == source_id,
            PostMetricSnapshot.post_age_hours >= min_post_age_hours,
            PostMetricSnapshot.post_age_hours <= max_post_age_hours,
        )
    )
    if measured_from is not None:
        statement = statement.where(PostMetricSnapshot.measured_at >= measured_from)
    if measured_to is not None:
        statement = statement.where(PostMetricSnapshot.measured_at <= measured_to)
    statement = statement.order_by(PostMetricSnapshot.measured_at.desc(), PostMetricSnapshot.id.desc())
    rows = (await db.execute(statement)).all()
    latest: dict[str, tuple[PostMetricSnapshot, CampaignPost]] = {}
    for snapshot, post in rows:
        latest.setdefault(post.id, (snapshot, post))
    return list(latest.values())


def _to_metric_input(snapshot: PostMetricSnapshot, post: CampaignPost, source_id: str) -> PostMetricInput:
    return PostMetricInput(
        post_id=post.id,
        page_id=source_id,
        group=post.pillar,
        measured_at=snapshot.measured_at,
        post_age_hours=snapshot.post_age_hours,
        reach=snapshot.reach,
        views=snapshot.views,
        followers=None,
        engagements=snapshot.engagements,
        clicks=snapshot.clicks,
        spend=float(snapshot.spend) if snapshot.spend is not None else None,
        attributed_revenue=float(snapshot.attributed_revenue) if snapshot.attributed_revenue is not None else None,
        attribution_valid=snapshot.attribution_valid,
    )


def _dashboard(source_id: str, rows: list[tuple[PostMetricSnapshot, CampaignPost]]) -> AnalyticsDashboardOut:
    inputs = [_to_metric_input(snapshot, post, source_id) for snapshot, post in rows]
    material = "|".join(f"{item.post_id}:{item.measured_at.isoformat()}" for item in sorted(inputs, key=lambda item: item.post_id))
    report_hash = hashlib.sha256(f"{source_id}|{material}".encode()).hexdigest()[:16]
    report = build_analytics_report(
        inputs,
        report_id=f"report:{report_hash}",
        page_id=source_id,
    )
    grouped: dict[str, list[PostMetricInput]] = defaultdict(list)
    by_format: dict[str, list[PostMetricInput]] = defaultdict(list)
    post_by_id = {post.id: post for _snapshot, post in rows}
    for item in inputs:
        grouped[item.group].append(item)
        by_format[post_by_id[item.post_id].format].append(item)

    group_outputs: list[MetricGroupOut] = []
    for dimension, collection in (("pillar", grouped), ("format", by_format)):
        for name, items in sorted(collection.items()):
            group_report = build_analytics_report(items, report_id=f"{report.report_id}:{dimension}:{name}", page_id=source_id)
            metrics = {item.metric: item.value for item in group_report.observations}
            group_outputs.append(MetricGroupOut(
                dimension=dimension,
                name=name,
                post_count=len(items),
                average_reach=metrics.get("reach"),
                average_views=metrics.get("views"),
                engagement_rate_by_reach=metrics.get("engagement_rate_by_reach"),
                click_rate_by_reach=metrics.get("click_rate_by_reach"),
            ))
    return AnalyticsDashboardOut(
        report=report,
        groups=group_outputs,
        source_id=source_id,
        source_label="Nhập thủ công",
        freshness_at=max((snapshot.measured_at for snapshot, _post in rows), default=None),
    )


@router.post(
    "/workspaces/{company_id}/metrics/import",
    response_model=MetricImportResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def import_metrics(
    company_id: str,
    request: MetricImportRequest,
    user: User = Depends(current_user),
    membership=Depends(require_permission("metric:import")),
    db: AsyncSession = Depends(get_db),
):
    post_ids = [point.post_id for point in request.points]
    posts = (await db.scalars(select(CampaignPost).where(
        CampaignPost.company_id == company_id,
        CampaignPost.id.in_(post_ids),
    ))).all()
    if len(posts) != len(post_ids):
        raise ApiProblem(404, "not_found", "Không tìm thấy một hoặc nhiều bài viết trong workspace.")

    imported = [
        PostMetricSnapshot(
            id=new_id(),
            company_id=company_id,
            post_id=point.post_id,
            source_id=request.source_id,
            measured_at=request.measured_at,
            post_age_hours=point.post_age_hours,
            reach=point.reach,
            views=point.views,
            engagements=point.engagements,
            clicks=point.clicks,
            spend=point.spend,
            attributed_revenue=point.attributed_revenue,
            attribution_valid=point.attribution_valid,
            imported_by=user.id,
        )
        for point in request.points
    ]
    db.add_all(imported)
    db.add(AuditEvent(
        company_id=company_id,
        actor_user_id=user.id,
        action="metrics.import",
        entity_type="metrics_snapshot",
        entity_id=None,
        metadata_json={"source_id": request.source_id, "count": len(imported), "measured_at": request.measured_at.isoformat()},
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiProblem(409, "duplicate_metric_snapshot", "Snapshot này đã được nhập. Mỗi bài chỉ có một dòng cho cùng nguồn và thời điểm đo.")

    duplicate_key = hashlib.sha256(
        f"{company_id}|{request.source_id}|{request.measured_at.isoformat()}|{'|'.join(sorted(post_ids))}".encode()
    ).hexdigest()
    return MetricImportResponse(
        source_id=request.source_id,
        imported_count=len(imported),
        measured_at=request.measured_at,
        snapshot_fingerprint=duplicate_key,
    )


@router.get("/workspaces/{company_id}/analytics/dashboard", response_model=AnalyticsDashboardOut)
async def get_analytics_dashboard(
    company_id: str,
    source_id: str = Query(min_length=1, max_length=160),
    min_post_age_hours: int = Query(default=0, ge=0, le=24 * 365),
    max_post_age_hours: int = Query(default=24 * 30, ge=0, le=24 * 365),
    measured_from: datetime | None = None,
    measured_to: datetime | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    if max_post_age_hours < min_post_age_hours:
        raise ApiProblem(422, "validation_error", "Khoảng tuổi bài viết không hợp lệ.")
    if measured_from and measured_to and measured_to < measured_from:
        raise ApiProblem(422, "validation_error", "Khoảng thời gian đo không hợp lệ.")
    rows = await _latest_points(
        db,
        company_id,
        source_id,
        min_post_age_hours=min_post_age_hours,
        max_post_age_hours=max_post_age_hours,
        measured_from=measured_from,
        measured_to=measured_to,
    )
    return _dashboard(source_id, rows)


@router.get("/workspaces/{company_id}/analytics/recommendation", response_model=RecommendationOut)
async def get_recommendation(
    company_id: str,
    source_id: str = Query(min_length=1, max_length=160),
    min_post_age_hours: int = Query(default=0, ge=0, le=24 * 365),
    max_post_age_hours: int = Query(default=24 * 30, ge=0, le=24 * 365),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    if max_post_age_hours < min_post_age_hours:
        raise ApiProblem(422, "validation_error", "Khoảng tuổi bài viết không hợp lệ.")
    rows = await _latest_points(
        db,
        company_id,
        source_id,
        min_post_age_hours=min_post_age_hours,
        max_post_age_hours=max_post_age_hours,
        measured_from=None,
        measured_to=None,
    )
    return _build_recommendation(source_id, rows)


def _build_recommendation(
    source_id: str,
    rows: list[tuple[PostMetricSnapshot, CampaignPost]],
) -> RecommendationOut:
    dashboard = _dashboard(source_id, rows)
    candidates = [
        row for row in dashboard.groups
        if row.dimension == "pillar" and row.post_count >= 5 and row.engagement_rate_by_reach is not None
    ]
    evidence = next((item.evidence_id for item in dashboard.report.evidence if "engagement_rate_by_reach" in item.metric_names), None)
    now = datetime.now(timezone.utc)
    if len(candidates) < 2 or evidence is None:
        return RecommendationOut(
            status="abstain",
            observation="Chưa đủ dữ liệu theo từng trụ nội dung để đề xuất thử nghiệm.",
            metric="engagement_rate_by_reach",
            confidence=0,
            sample_size=len(rows),
            evidence_ids=[],
            limitations=["Cần ít nhất 5 bài cho mỗi trụ được so sánh.", "Số liệu mô tả không chứng minh quan hệ nhân quả."],
            created_at=now,
        )
    ranked = sorted(candidates, key=lambda row: row.engagement_rate_by_reach or 0, reverse=True)
    best, runner_up = ranked[0], ranked[1]
    if (best.engagement_rate_by_reach or 0) <= (runner_up.engagement_rate_by_reach or 0):
        return RecommendationOut(
            status="abstain",
            observation="Dữ liệu hiện tại chưa cho thấy một trụ nổi trội để ưu tiên thử nghiệm.",
            metric="engagement_rate_by_reach",
            confidence=0,
            sample_size=sum(row.post_count for row in candidates),
            evidence_ids=[],
            limitations=["Các nhóm được mô tả theo snapshot gần nhất; không thể suy ra tác động nhân quả."],
            created_at=now,
        )
    return RecommendationOut(
        status="proposed",
        observation=f"{best.name} có engagement rate by reach cao nhất trong các nhóm hiện có ({best.post_count} bài).",
        hypothesis=f"Khi thử nội dung thuộc trụ {best.name}, engagement rate by reach có thể cao hơn trụ {runner_up.name}.",
        action=f"Chạy thử hai tuần với lịch đăng và định dạng tương đương, phân bổ bài giữa {best.name} và {runner_up.name}.",
        metric="engagement_rate_by_reach",
        threshold="Đạt mức tăng tương đối ít nhất 10% sau khi đo cùng cửa sổ tuổi bài; đây là ngưỡng thử nghiệm, không phải dự báo.",
        confidence=0.3,
        sample_size=sum(row.post_count for row in candidates),
        evidence_ids=[evidence],
        limitations=["Đây là so sánh mô tả, không chứng minh nhân quả.", "Không dùng để dự báo kết quả hoặc tự động thay đổi campaign."],
        created_at=now,
    )


def _recommendation_record_out(row: AnalyticsRecommendationRecord) -> AnalyticsRecommendationRecordOut:
    return AnalyticsRecommendationRecordOut(
        id=row.id,
        source_id=row.source_id,
        lifecycle_status=row.lifecycle_status,
        recommendation=RecommendationOut.model_validate(row.recommendation_json),
        feedback=(RecommendationFeedbackOut.model_validate(row.feedback_json) if row.feedback_json else None),
        created_at=row.created_at,
    )


def _brief_revision_out(row: CampaignBriefRevisionDraft) -> CampaignBriefRevisionDraftOut:
    return CampaignBriefRevisionDraftOut(
        id=row.id,
        campaign_id=row.campaign_id,
        base_version=row.base_version,
        changes=[CampaignBriefChangeOut.model_validate(item) for item in row.changes_json],
        source_recommendation_id=row.recommendation_id,
        status=row.status,
        created_at=row.created_at,
    )


@router.post(
    "/workspaces/{company_id}/analytics/recommendations",
    response_model=AnalyticsRecommendationRecordOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def save_recommendation(
    company_id: str,
    request: SaveRecommendationRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    rows = await _latest_points(
        db,
        company_id,
        request.source_id,
        min_post_age_hours=0,
        max_post_age_hours=24 * 30,
        measured_from=None,
        measured_to=None,
    )
    dashboard = _dashboard(request.source_id, rows)
    recommendation = _build_recommendation(request.source_id, rows)
    if recommendation.status != "proposed":
        raise ApiProblem(409, "insufficient_evidence", "Chưa đủ bằng chứng để lưu đề xuất áp dụng.")

    fingerprint_material = {
        "report_id": dashboard.report.report_id,
        "status": recommendation.status,
        "hypothesis": recommendation.hypothesis,
        "action": recommendation.action,
        "evidence_ids": recommendation.evidence_ids,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    existing = await db.scalar(select(AnalyticsRecommendationRecord).where(
        AnalyticsRecommendationRecord.company_id == company_id,
        AnalyticsRecommendationRecord.source_id == request.source_id,
        AnalyticsRecommendationRecord.evidence_fingerprint == fingerprint,
    ))
    if existing:
        return _recommendation_record_out(existing)

    row = AnalyticsRecommendationRecord(
        id=new_id(),
        company_id=company_id,
        source_id=request.source_id,
        evidence_fingerprint=fingerprint,
        recommendation_json=recommendation.model_dump(mode="json"),
        lifecycle_status="new",
    )
    db.add(row)
    db.add(AuditEvent(
        company_id=company_id,
        actor_user_id=user.id,
        action="recommendation.save",
        entity_type="analytics_recommendation",
        entity_id=row.id,
        metadata_json={"source_id": request.source_id, "evidence_ids": recommendation.evidence_ids},
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(AnalyticsRecommendationRecord).where(
            AnalyticsRecommendationRecord.company_id == company_id,
            AnalyticsRecommendationRecord.source_id == request.source_id,
            AnalyticsRecommendationRecord.evidence_fingerprint == fingerprint,
        ))
        if existing is None:
            raise ApiProblem(409, "state_conflict", "Không thể lưu đề xuất do xung đột đồng thời.")
        return _recommendation_record_out(existing)
    await db.refresh(row)
    return _recommendation_record_out(row)


@router.post(
    "/workspaces/{company_id}/analytics/recommendations/{recommendation_id}/feedback",
    response_model=AnalyticsRecommendationRecordOut,
    dependencies=[Depends(require_csrf)],
)
async def record_recommendation_feedback(
    company_id: str,
    recommendation_id: str,
    request: RecommendationFeedbackRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    row = await db.scalar(select(AnalyticsRecommendationRecord).where(
        AnalyticsRecommendationRecord.company_id == company_id,
        AnalyticsRecommendationRecord.id == recommendation_id,
    ).with_for_update())
    if row is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy đề xuất.")
    if row.lifecycle_status == "applied":
        raise ApiProblem(409, "state_conflict", "Đề xuất đã được áp dụng thành bản nháp; không thể đổi feedback.")
    feedback = RecommendationFeedbackOut(
        value=request.value,
        note=request.note,
        at=utcnow(),
        by=user.id,
    )
    row.feedback_json = feedback.model_dump(mode="json")
    row.lifecycle_status = "dismissed" if request.value == "not_useful" else "acknowledged"
    row.updated_at = utcnow()
    db.add(AuditEvent(
        company_id=company_id,
        actor_user_id=user.id,
        action="recommendation.feedback",
        entity_type="analytics_recommendation",
        entity_id=row.id,
        metadata_json={"value": request.value},
    ))
    await db.commit()
    await db.refresh(row)
    return _recommendation_record_out(row)


@router.post(
    "/workspaces/{company_id}/analytics/recommendations/{recommendation_id}/apply",
    response_model=ApplyRecommendationResponse,
    dependencies=[Depends(require_csrf)],
)
async def apply_recommendation(
    company_id: str,
    recommendation_id: str,
    request: ApplyRecommendationRequest,
    user: User = Depends(current_user),
    membership=Depends(require_permission("recommendation:apply")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(AnalyticsRecommendationRecord).where(
        AnalyticsRecommendationRecord.company_id == company_id,
        AnalyticsRecommendationRecord.id == recommendation_id,
    ).with_for_update())
    if row is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy đề xuất.")
    existing_draft = await db.scalar(select(CampaignBriefRevisionDraft).where(
        CampaignBriefRevisionDraft.company_id == company_id,
        CampaignBriefRevisionDraft.recommendation_id == row.id,
    ))
    if existing_draft:
        return ApplyRecommendationResponse(
            recommendation=_recommendation_record_out(row),
            created_draft=_brief_revision_out(existing_draft),
            notice="Đề xuất chỉ tạo bản nháp; campaign chỉ thay đổi sau khi chủ workspace chấp nhận.",
        )
    if row.lifecycle_status == "dismissed":
        raise ApiProblem(409, "state_conflict", "Đề xuất đã bị từ chối, không thể áp dụng.")
    recommendation = RecommendationOut.model_validate(row.recommendation_json)
    if recommendation.status != "proposed":
        raise ApiProblem(409, "insufficient_evidence", "Đề xuất chưa đủ bằng chứng để áp dụng.")
    available_evidence = set(recommendation.evidence_ids)
    selected_evidence = set(request.evidence_ids or recommendation.evidence_ids)
    if not selected_evidence or not selected_evidence.issubset(available_evidence):
        raise ApiProblem(422, "validation_error", "Danh sách bằng chứng không thuộc đề xuất này.")

    campaign = await db.scalar(select(Campaign).where(
        Campaign.company_id == company_id,
        Campaign.id == request.campaign_id,
    ).with_for_update())
    if campaign is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy campaign trong workspace.")
    brief = dict(campaign.brief_json)
    previous = brief.get("must_include", [])
    if not isinstance(previous, list) or any(not isinstance(item, str) for item in previous):
        raise ApiProblem(409, "invalid_campaign_brief", "Không thể tạo revision vì brief hiện tại không hợp lệ.")
    action = recommendation.action or ""
    experiment_note = (
        f"Thử nghiệm recommendation: {recommendation.hypothesis} "
        f"{action} Theo dõi {recommendation.metric}; ngưỡng: {recommendation.threshold or 'so sánh cùng cửa sổ đo'}"
    )
    after = previous if experiment_note in previous else [*previous, experiment_note]
    resulting_brief = {**brief, "must_include": after}
    change = CampaignBriefChangeOut(
        field="must_include",
        label="Yêu cầu bắt buộc trong campaign",
        before=previous,
        after=after,
        rationale=f"{recommendation.observation} Bằng chứng: {', '.join(sorted(selected_evidence))}.",
    )
    draft = CampaignBriefRevisionDraft(
        id=new_id(),
        company_id=company_id,
        campaign_id=campaign.id,
        recommendation_id=row.id,
        base_version=campaign.version,
        changes_json=[change.model_dump(mode="json")],
        resulting_brief_json=resulting_brief,
        status="pending_review",
        note=request.note,
        created_by=user.id,
    )
    row.lifecycle_status = "applied"
    row.updated_at = utcnow()
    db.add(draft)
    db.add(AuditEvent(
        company_id=company_id,
        actor_user_id=user.id,
        action="recommendation.apply_to_draft",
        entity_type="campaign_brief_revision_draft",
        entity_id=draft.id,
        metadata_json={"campaign_id": campaign.id, "base_version": campaign.version, "evidence_ids": sorted(selected_evidence)},
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing_draft = await db.scalar(select(CampaignBriefRevisionDraft).where(
            CampaignBriefRevisionDraft.company_id == company_id,
            CampaignBriefRevisionDraft.recommendation_id == recommendation_id,
        ))
        if existing_draft is None:
            raise ApiProblem(409, "state_conflict", "Không thể áp dụng do xung đột đồng thời.")
        row = await db.scalar(select(AnalyticsRecommendationRecord).where(
            AnalyticsRecommendationRecord.company_id == company_id,
            AnalyticsRecommendationRecord.id == recommendation_id,
        ))
        return ApplyRecommendationResponse(
            recommendation=_recommendation_record_out(row),
            created_draft=_brief_revision_out(existing_draft),
            notice="Đề xuất chỉ tạo bản nháp; campaign chỉ thay đổi sau khi chủ workspace chấp nhận.",
        )
    await db.refresh(draft)
    return ApplyRecommendationResponse(
        recommendation=_recommendation_record_out(row),
        created_draft=_brief_revision_out(draft),
        notice="Đề xuất đã tạo bản nháp để xem lại. Campaign chưa thay đổi cho tới khi bạn chấp nhận.",
    )


@router.post(
    "/workspaces/{company_id}/analytics/recommendation-drafts/{draft_id}/decision",
    response_model=CampaignBriefRevisionDraftOut,
    dependencies=[Depends(require_csrf)],
)
async def decide_recommendation_draft(
    company_id: str,
    draft_id: str,
    request: RecommendationDraftDecisionRequest,
    user: User = Depends(current_user),
    membership=Depends(require_permission("recommendation:apply")),
    db: AsyncSession = Depends(get_db),
):
    draft = await db.scalar(select(CampaignBriefRevisionDraft).where(
        CampaignBriefRevisionDraft.company_id == company_id,
        CampaignBriefRevisionDraft.id == draft_id,
    ).with_for_update())
    if draft is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy bản nháp revision.")
    if draft.status == request.decision:
        return _brief_revision_out(draft)
    if draft.status != "pending_review":
        raise ApiProblem(409, "state_conflict", "Bản nháp đã được quyết định trước đó.")
    campaign = await db.scalar(select(Campaign).where(
        Campaign.company_id == company_id,
        Campaign.id == draft.campaign_id,
    ).with_for_update())
    if campaign is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy campaign của bản nháp.")
    if request.decision == "accepted":
        if campaign.version != draft.base_version:
            raise ApiProblem(409, "version_conflict", "Campaign đã thay đổi sau khi tạo bản nháp. Hãy tạo revision mới từ brief hiện tại.")
        campaign.brief_json = draft.resulting_brief_json
        campaign.version += 1
        campaign.updated_at = utcnow()
    draft.status = request.decision
    db.add(AuditEvent(
        company_id=company_id,
        actor_user_id=user.id,
        action=f"recommendation.brief_revision.{request.decision}",
        entity_type="campaign_brief_revision_draft",
        entity_id=draft.id,
        metadata_json={"campaign_id": campaign.id, "campaign_version": campaign.version},
    ))
    await db.commit()
    await db.refresh(draft)
    return _brief_revision_out(draft)
