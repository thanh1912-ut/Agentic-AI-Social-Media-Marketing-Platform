"""Tenant-bound Meta Page connection, guarded publishing, and Page history."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AuditEvent, CampaignPost, Job, JobStep, MediaAsset, Membership, MetaPagePost,
    MetaPublication, MetaSyncState, PostApproval, PostVersion, User, utcnow,
)
from .config import settings
from .content_integrity import content_sha256
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .job_service import accepted_response, dispatch_meta_job
from .meta_client import MetaGraphClient, MetaGraphReadError, MetaGraphRejected, MetaGraphTokenExpired
from .meta_schemas import (
    MetaConnectionOut, MetaPagePostOut, MetaPagePostsOut, MetaPublicationOut,
    MetaPublishIn, MetaReconcileIn,
)
from .schemas import AcceptedResponse


router = APIRouter(prefix="/workspaces/{company_id}/meta", tags=["meta"])


def _configured_for(company_id: str) -> bool:
    return settings.meta_configured and settings.meta_workspace_id == company_id


def _client() -> MetaGraphClient:
    return MetaGraphClient(settings.meta_page_id, settings.meta_page_access_token, settings.meta_graph_version)


def _require_connection(company_id: str) -> None:
    if not _configured_for(company_id):
        raise ApiProblem(409, "meta_unconfigured", "Fanpage chưa được cấu hình cho workspace này.")


async def _state(db: AsyncSession, company_id: str, *, lock: bool = False) -> MetaSyncState | None:
    query = select(MetaSyncState).where(
        MetaSyncState.company_id == company_id, MetaSyncState.page_id == settings.meta_page_id
    )
    if lock:
        query = query.with_for_update()
    return await db.scalar(query)


def _publication_out(row: MetaPublication) -> MetaPublicationOut:
    return MetaPublicationOut(
        id=row.id, post_id=row.post_id, post_version=row.post_version, page_id=row.page_id,
        status=row.status, external_post_id=row.external_post_id, permalink=row.permalink,
        error=row.error_json, created_at=row.created_at, updated_at=row.updated_at,
    )


def _page_post_out(row: MetaPagePost) -> MetaPagePostOut:
    counts = (row.reactions, row.comments, row.shares)
    return MetaPagePostOut(
        id=row.id, external_post_id=row.external_post_id, page_id=row.page_id,
        message=row.message, permalink=row.permalink, published_at=row.published_at,
        reactions=row.reactions, comments=row.comments, shares=row.shares,
        engagements=sum(counts) if all(count is not None for count in counts) else None,
        last_synced_at=row.last_synced_at, linked_post_id=row.linked_post_id,
    )


@router.get("/connection", response_model=MetaConnectionOut)
async def get_meta_connection(
    company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    if not _configured_for(company_id):
        return MetaConnectionOut(status="unconfigured", page_id=None, page_name=None,
                                 can_publish=False, can_sync_metrics=False,
                                 message="Chưa cấu hình Fanpage trên backend.")
    state = await _state(db, company_id)
    verified = bool(state and state.verified_at)
    return MetaConnectionOut(
        status="verified" if verified else "configured", page_id=settings.meta_page_id,
        page_name=state.page_name if state else None,
        can_publish=verified, can_sync_metrics=verified,
        message=("Đã xác minh Page và quyền đọc bài. Meta vẫn kiểm tra quyền đăng khi gửi từng bài."
                 if verified else "Đã cấu hình token; hãy xác minh Fanpage."),
    )


@router.post("/connection/verify", response_model=MetaConnectionOut, dependencies=[Depends(require_csrf)])
async def verify_meta_connection(
    company_id: str,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("connection:manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_connection(company_id)
    try:
        async with _client() as client:
            page = await client.verify_page()
            # A one-item read is side-effect-free and confirms Page posts can
            # be read before the UI offers historical metric synchronization.
            await client.list_page_posts(limit=1)
    except MetaGraphTokenExpired:
        raise ApiProblem(409, "meta_token_invalid", "Token Fanpage không còn hợp lệ. Hãy cấu hình lại token trên backend.") from None
    except (MetaGraphRejected, MetaGraphReadError):
        raise ApiProblem(502, "meta_verification_failed", "Không thể xác minh Fanpage với Meta. Kiểm tra Page ID, token và quyền truy cập.") from None
    state = await _state(db, company_id, lock=True)
    if state is None:
        state = MetaSyncState(company_id=company_id, page_id=page.id, has_more=True)
        db.add(state)
    state.page_name = page.name
    state.verified_at = utcnow()
    state.updated_at = utcnow()
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id,
                      action="meta.connection.verify", entity_type="meta_page", entity_id=None,
                      metadata_json={"page_id": page.id}))
    await db.commit()
    return MetaConnectionOut(status="verified", page_id=page.id, page_name=page.name,
                             can_publish=True, can_sync_metrics=True,
                             message="Đã xác minh Page và quyền đọc bài. Meta vẫn kiểm tra quyền đăng khi gửi từng bài.")


@router.get("/publications", response_model=list[MetaPublicationOut])
async def list_meta_publications(
    company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    rows = (await db.scalars(select(MetaPublication).where(MetaPublication.company_id == company_id)
                             .order_by(MetaPublication.created_at.desc()).limit(200))).all()
    return [_publication_out(row) for row in rows]


@router.post("/publications", response_model=AcceptedResponse, status_code=202,
             dependencies=[Depends(require_csrf)])
async def publish_meta_post(
    company_id: str, request: MetaPublishIn,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("publish:create")),
    db: AsyncSession = Depends(get_db),
):
    _require_connection(company_id)
    state = await _state(db, company_id)
    if state is None or not state.verified_at:
        raise ApiProblem(409, "meta_not_verified", "Hãy xác minh Fanpage trước khi đăng bài.")
    active_key = f"{request.post_id}:{request.version}:{settings.meta_page_id}"
    existing = await db.scalar(select(MetaPublication).where(
        MetaPublication.company_id == company_id, MetaPublication.active_key == active_key
    ))
    if existing is not None:
        existing_job = await db.get(Job, existing.job_id)
        if existing_job is not None:
            return await accepted_response(db, existing_job)
    post = await db.scalar(select(CampaignPost).where(
        CampaignPost.company_id == company_id, CampaignPost.id == request.post_id
    ).with_for_update())
    if post is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy bài viết.")
    if post.channel != "facebook_page" or post.format not in {"text", "image"}:
        raise ApiProblem(422, "meta_format_unsupported", "Fanpage hiện hỗ trợ bài chữ hoặc một ảnh đã tải lên.")
    if post.status != "approved" or post.current_version != request.version or post.requires_reapproval:
        raise ApiProblem(409, "post_not_approved", "Chỉ phiên bản bài viết đã duyệt hiện tại mới được đăng.")
    version = await db.scalar(select(PostVersion).where(
        PostVersion.company_id == company_id, PostVersion.post_id == post.id,
        PostVersion.version == request.version,
    ))
    approval = await db.scalar(select(PostApproval).where(
        PostApproval.company_id == company_id, PostApproval.post_id == post.id,
        PostApproval.version == request.version,
    ).order_by(PostApproval.decided_at.desc(), PostApproval.id.desc()))
    if version is None or approval is None or approval.decision != "approved" or approval.content_sha256 != content_sha256(version.content_json):
        raise ApiProblem(409, "approval_changed", "Nội dung không còn khớp phiên bản đã duyệt.")
    media = version.content_json.get("media") or []
    if not isinstance(media, list) or (post.format == "text" and media) or (post.format == "image" and (
        len(media) != 1 or not isinstance(media[0], dict) or media[0].get("source") != "uploaded"
    )):
        raise ApiProblem(422, "meta_media_unsupported", "Bài ảnh cần đúng một ảnh đã tải lên; bài chữ không có ảnh.")
    if post.format == "image":
        media_asset = media[0]
        asset = await db.scalar(select(MediaAsset).where(
            MediaAsset.company_id == company_id, MediaAsset.id == media_asset.get("asset_id")
        ))
        if asset is None or asset.mime_type not in {"image/jpeg", "image/png"} or media_asset.get("sha256") != asset.content_sha256:
            raise ApiProblem(422, "meta_media_unsupported", "Ảnh phải là JPEG hoặc PNG còn nguyên vẹn và thuộc workspace này.")
    caption = version.content_json.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        raise ApiProblem(422, "meta_caption_missing", "Bài viết cần nội dung trước khi đăng.")
    job = Job(company_id=company_id, created_by=user.id, kind="meta_publish",
              title="Đăng bài lên Fanpage", status="queued", progress=0,
              result={"post_id": post.id, "version": request.version}, attempts=0)
    db.add(job)
    await db.flush()
    publication = MetaPublication(
        company_id=company_id, post_id=post.id, post_version=request.version,
        approved_content_sha256=approval.content_sha256, page_id=settings.meta_page_id,
        status="queued", active_key=active_key, job_id=job.id,
    )
    db.add(publication)
    await db.flush()
    job.result = {"publication_id": publication.id, "post_id": post.id, "version": request.version}
    db.add(JobStep(job_id=job.id, step_key="publish", label="Gửi bài lên Fanpage", status="pending"))
    post.status = "scheduled"  # Prevent edits while delivery is queued or uncertain.
    post.publish_mode = "now"
    post.updated_at = utcnow()
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="meta.publish.request",
                      entity_type="post", entity_id=post.id,
                      metadata_json={"version": request.version, "publication_id": publication.id,
                                     "page_id": settings.meta_page_id, "content_sha256": approval.content_sha256}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiProblem(409, "meta_duplicate_publish", "Bài này đang được đăng, đã đăng hoặc đang chờ đối soát.") from None
    await dispatch_meta_job(job.id, "meta_publish")
    await db.refresh(job)
    return await accepted_response(db, job)


@router.post("/publications/{publication_id}/reconcile", response_model=MetaPublicationOut,
             dependencies=[Depends(require_csrf)])
async def reconcile_meta_publication(
    company_id: str, publication_id: str, request: MetaReconcileIn,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("publish:create")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(MetaPublication).where(
        MetaPublication.company_id == company_id, MetaPublication.id == publication_id
    ).with_for_update())
    if row is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy lần đăng bài.")
    if row.status != "outcome_unknown":
        raise ApiProblem(409, "state_conflict", "Chỉ bài có kết quả chưa rõ mới được đối soát.")
    if request.outcome == "published":
        _require_connection(company_id)
        try:
            async with _client() as client:
                confirmed = await client.read_post_metrics(request.external_post_id or "")
        except (ValueError, MetaGraphRejected, MetaGraphReadError):
            raise ApiProblem(409, "meta_post_not_verified", "Không xác minh được ID bài đăng trên Fanpage.") from None
        row.external_post_id = confirmed.external_post_id
        row.permalink = confirmed.permalink_url
        row.published_at = confirmed.created_time or utcnow()
        row.status = "published"
    else:
        row.status = "not_published"
        row.active_key = None
    row.error_json = None
    row.updated_at = utcnow()
    post = await db.scalar(select(CampaignPost).where(
        CampaignPost.company_id == company_id, CampaignPost.id == row.post_id
    ).with_for_update())
    if post is not None and post.current_version == row.post_version and post.status == "scheduled":
        post.status = "published" if request.outcome == "published" else "approved"
        post.updated_at = utcnow()
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id,
                      action=f"meta.publish.reconcile.{request.outcome}", entity_type="meta_publication",
                      entity_id=row.id, metadata_json={"external_post_id": row.external_post_id,
                                                       "note": request.note or ""}))
    await db.commit()
    return _publication_out(row)


@router.get("/page-posts", response_model=MetaPagePostsOut)
async def list_meta_page_posts(
    company_id: str, limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    if not _configured_for(company_id):
        return MetaPagePostsOut(items=[], total=0, has_more=False, next_offset=None,
                                sync_has_more=False, last_sync_at=None)
    filters = (MetaPagePost.company_id == company_id, MetaPagePost.page_id == settings.meta_page_id)
    total = await db.scalar(select(func.count()).select_from(MetaPagePost).where(*filters)) or 0
    rows = (await db.scalars(select(MetaPagePost).where(*filters)
                             .order_by(MetaPagePost.published_at.desc(), MetaPagePost.id.desc())
                             .offset(offset).limit(limit))).all()
    state = await _state(db, company_id)
    has_more = offset + len(rows) < total
    return MetaPagePostsOut(items=[_page_post_out(row) for row in rows], total=total,
                            has_more=has_more, next_offset=offset + len(rows) if has_more else None,
                            sync_has_more=state.has_more if state else True,
                            last_sync_at=state.last_sync_at if state else None)


@router.post("/metrics/sync", response_model=AcceptedResponse, status_code=202,
             dependencies=[Depends(require_csrf)])
async def sync_meta_metrics(
    company_id: str,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("connection:manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_connection(company_id)
    state = await _state(db, company_id, lock=True)
    if state is None or not state.verified_at:
        raise ApiProblem(409, "meta_not_verified", "Hãy xác minh Fanpage trước khi đồng bộ.")
    if state.running_job_id:
        running = await db.get(Job, state.running_job_id)
        if running and running.status in {"queued", "running"}:
            raise ApiProblem(409, "meta_sync_in_progress", "Đang đồng bộ số liệu Fanpage.")
    job = Job(company_id=company_id, created_by=user.id, kind="meta_metrics_sync",
              title="Đồng bộ bài cũ và số liệu Fanpage", status="queued", progress=0,
              result={"page_id": settings.meta_page_id}, attempts=0)
    db.add(job)
    await db.flush()
    state.running_job_id = job.id
    state.updated_at = utcnow()
    db.add(JobStep(job_id=job.id, step_key="sync", label="Đọc bài đăng và số liệu Fanpage", status="pending"))
    db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="meta.metrics.sync.request",
                      entity_type="meta_page", entity_id=None,
                      metadata_json={"page_id": settings.meta_page_id, "job_id": job.id}))
    await db.commit()
    await dispatch_meta_job(job.id, "meta_metrics_sync")
    await db.refresh(job)
    return await accepted_response(db, job)
