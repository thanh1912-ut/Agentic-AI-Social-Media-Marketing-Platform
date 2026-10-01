"""Owner review/analysis of pinned comment excerpts, separate from collection."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditEvent, Job, Membership, ResearchCommentAnalysisBatch, ResearchCommentVersion, ResearchScreenedComment, User, utcnow
from services.research.comment_analysis import CommentAnalysisHeld, aware, create_screened_batch, excerpt_binding
from services.research.comment_quarantine import CommentQuarantineUnavailable, decrypt_candidate
from . import job_service
from .comment_processing import _source
from .db import get_db
from .dependencies import current_user, require_csrf, require_permission
from .errors import ApiProblem
from .market_research import _decode_web_cursor, _encode_web_cursor
from .market_research_schemas import CommentAnalysisIn, CommentAnalysisOut, CommentAnalysesPage, ScreenedCommentCitationOut
from .rate_limits import rate_limit
from .schemas import AcceptedResponse

router = APIRouter(prefix="/workspaces/{company_id}/market-research", tags=["market-research"])
DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
Owner = Annotated[Membership, Depends(require_permission("connection:manage"))]


async def _out(db, row):
    available = row.status not in {"expired", "suppressed"} and aware(row.expires_at) > utcnow()
    pairs = (await db.execute(select(ResearchScreenedComment, ResearchCommentVersion).join(
        ResearchCommentVersion, (ResearchCommentVersion.company_id == ResearchScreenedComment.company_id)
        & (ResearchCommentVersion.source_id == ResearchScreenedComment.source_id)
        & (ResearchCommentVersion.id == ResearchScreenedComment.version_id)).where(
        ResearchScreenedComment.company_id == row.company_id, ResearchScreenedComment.batch_id == row.id
    ).order_by(ResearchScreenedComment.id))).all() if available else []
    citations = []
    for item, version in pairs:
        if item.excerpt_ciphertext is None or version.status == "suppressed":
            available = False
            citations = []
            break
        try:
            text = decrypt_candidate(item.excerpt_ciphertext, binding=excerpt_binding(item))
        except CommentQuarantineUnavailable:
            raise ApiProblem(503, "comment_encryption_unavailable", "Không mở được bản kiểm tra đã lưu.") from None
        citations.append(ScreenedCommentCitationOut(evidence_ref="comment_" + item.id, version_id=version.id,
            evidence_id=version.evidence_id, observation_id=version.observation_id,
            evidence_version_id=version.evidence_version_id, text=text, content_edited=item.content_edited,
            source_content_truncated=version.content_truncated))
    job_id = await db.scalar(select(Job.id).where(Job.company_id == row.company_id,
        Job.idempotency_key == f"comment-analysis:{row.id}"))
    report_job = await db.scalar(select(Job).where(Job.company_id == row.company_id,
        Job.idempotency_key == "comment-report:" + row.id))
    return CommentAnalysisOut(id=row.id, source_id=row.source_id, job_id=job_id,
        report_job_id=report_job.id if report_job else None,
        report_id=(report_job.result or {}).get("report_id") if report_job and available else None,
        status=row.status if available or row.status == "suppressed" else "expired",
        provider=row.provider, model=row.model, created_at=row.created_at, expires_at=row.expires_at,
        result=row.result_json if available else None, coverage=row.coverage_json,
        error_code=row.error_code, selected_version_ids=[item.version_id for item in citations], citations=citations)


@router.post("/sources/{source_id}/comment-analyses", response_model=AcceptedResponse, status_code=202,
    dependencies=[Depends(require_csrf), Depends(rate_limit("comment_analysis", max_requests=6, window_seconds=3600))])
async def create_comment_analysis(company_id: str, source_id: str, request: CommentAnalysisIn,
                                  user: CurrentUser, owner: Owner, db: DB):
    try:
        batch, job, created = await create_screened_batch(db, company_id=company_id, source_id=source_id,
            actor_id=user.id, request=request)
    except CommentAnalysisHeld as error:
        await db.rollback()
        raise ApiProblem(403 if error.code == "comment_owner_required" else 404 if error.code == "comment_source_missing" else 409,
            error.code, "Lô bình luận chưa đủ điều kiện phân tích. Tải lại nguồn, rà soát phiên bình luận và tham chiếu đánh giá xử lý/gửi dữ liệu trước khi thử lại.") from None
    except CommentQuarantineUnavailable:
        await db.rollback()
        raise ApiProblem(503, "comment_encryption_unavailable", "Không mở được bản kiểm tra bình luận; chưa gửi dữ liệu tới Gemini.") from None
    if created:
        db.add(AuditEvent(company_id=company_id, actor_user_id=user.id, action="research.comment_analysis.request",
            entity_type="research_comment_analysis_batch", entity_id=batch.id,
            metadata_json={"selected_comments": len(request.comments), "provider": "gemini", "model": "gemini-3.8-flash",
                           "assessment_scope": "selected_screened_excerpts", "legal_basis_verified_by_platform": False}))
        await db.commit()  # Durable selection and job before broker delivery.
        sent = await job_service.dispatch_comment_analysis_job(job.id)
        await job_service._record_dispatch(db, job.id, sent)
    return await job_service.accepted_response(db, job)


@router.get("/sources/{source_id}/comment-analyses", response_model=CommentAnalysesPage)
async def list_comment_analyses(company_id: str, source_id: str, response: Response, owner: Owner, db: DB,
                                cursor: str | None = None, limit: int = 25, evidence_id: str | None = None):
    await _source(db, company_id, source_id)
    if not 1 <= limit <= 100:
        raise ApiProblem(422, "invalid_limit", "Mỗi trang từ 1 đến 100 lô phân tích.")
    query = select(ResearchCommentAnalysisBatch).where(ResearchCommentAnalysisBatch.company_id == company_id,
        ResearchCommentAnalysisBatch.source_id == source_id)
    if evidence_id:
        query = query.where(ResearchCommentAnalysisBatch.id.in_(select(ResearchScreenedComment.batch_id).join(
            ResearchCommentVersion, (ResearchCommentVersion.company_id == ResearchScreenedComment.company_id)
            & (ResearchCommentVersion.source_id == ResearchScreenedComment.source_id)
            & (ResearchCommentVersion.id == ResearchScreenedComment.version_id)).where(
            ResearchScreenedComment.company_id == company_id, ResearchScreenedComment.source_id == source_id,
            ResearchCommentVersion.evidence_id == evidence_id)))
    if cursor:
        created_at, batch_id = _decode_web_cursor(cursor)
        query = query.where((ResearchCommentAnalysisBatch.created_at < created_at) |
            ((ResearchCommentAnalysisBatch.created_at == created_at) & (ResearchCommentAnalysisBatch.id < batch_id)))
    rows = (await db.scalars(query.order_by(ResearchCommentAnalysisBatch.created_at.desc(),
        ResearchCommentAnalysisBatch.id.desc()).limit(limit + 1))).all()
    has_more, rows = len(rows) > limit, rows[:limit]
    response.headers["Cache-Control"] = "no-store, private"
    return CommentAnalysesPage(items=[await _out(db, row) for row in rows],
        next_cursor=_encode_web_cursor(rows[-1].created_at, rows[-1].id) if rows and has_more else None)


@router.get("/sources/{source_id}/comment-analyses/{batch_id}", response_model=CommentAnalysisOut)
async def get_comment_analysis(company_id: str, source_id: str, batch_id: str, response: Response, owner: Owner, db: DB):
    row = await db.scalar(select(ResearchCommentAnalysisBatch).where(
        ResearchCommentAnalysisBatch.company_id == company_id, ResearchCommentAnalysisBatch.source_id == source_id,
        ResearchCommentAnalysisBatch.id == batch_id))
    if row is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy lô phân tích của nguồn.")
    response.headers["Cache-Control"] = "no-store, private"
    return await _out(db, row)
