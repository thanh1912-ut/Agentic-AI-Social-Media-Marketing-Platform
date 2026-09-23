"""Tenant-scoped manual metrics, descriptive analytics and cautious tests."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditEvent, CampaignPost, PostMetricSnapshot, User, new_id, utcnow
from services.agents.analytics.metrics import PostMetricInput, build_analytics_report
from .analytics_schemas import (
    AnalyticsDashboardOut,
    MetricGroupOut,
    MetricImportRequest,
    MetricImportResponse,
    RecommendationOut,
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
