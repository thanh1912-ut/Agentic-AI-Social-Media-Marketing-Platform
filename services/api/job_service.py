"""Job ledger serialization and post-commit dispatch."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Job, JobEvent, JobStep
from .config import settings
from .schemas import AcceptedResponse, JobErrorOut, JobOut, JobStepOut


STEP_LABELS = {
    "receive_file": "Nhận tệp tải lên",
    "detect_type": "Nhận dạng định dạng tệp",
    "extract_text": "Đọc nội dung văn bản",
    "normalize": "Chuẩn hoá nội dung và nguồn",
    "chunk_and_index": "Chia đoạn và lập chỉ mục tra cứu",
    "create_brand_profile": "Tạo và lưu hồ sơ thương hiệu",
    "prepare_context": "Xác minh hồ sơ và tìm nguồn phù hợp",
    "generate_posts": "Sinh bản nháp bằng AI",
    "save_posts": "Lưu phiên bản và thông tin kiểm duyệt",
}


def _job_error(raw: dict[str, Any] | None) -> JobErrorOut | None:
    if not raw:
        return None
    return JobErrorOut(
        code=str(raw.get("code", "job_failed")),
        message=str(raw.get("message", "Job không hoàn thành.")),
        hint=raw.get("hint"),
        retryable=bool(raw.get("retryable", False)),
    )


async def serialize_job(db: AsyncSession, job: Job) -> JobOut:
    steps = (await db.scalars(select(JobStep).where(JobStep.job_id == job.id).order_by(JobStep.created_at))).all()
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        title=job.title,
        progress=job.progress,
        steps=[
            JobStepOut(
                key=step.step_key,
                label=step.label,
                status=step.status,
                progress=step.progress,
                message=step.message,
                started_at=step.started_at,
                finished_at=step.finished_at,
                error=JobErrorOut(**step.error) if step.error else None,
            )
            for step in steps
        ],
        result=job.result,
        error=_job_error(job.error),
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        cancellable=job.status in {"queued", "running"} and job.kind not in {"meta_publish", "meta_publish_scheduled", "meta_metrics_sync"},
    )


async def accepted_response(db: AsyncSession, job: Job) -> AcceptedResponse:
    return AcceptedResponse(job_id=job.id, job=await serialize_job(db, job))


async def append_job_event(db: AsyncSession, job: Job, event_type: str, message: str, progress: int | None = None) -> None:
    last = await db.scalar(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.sequence.desc()))
    sequence = (last.sequence + 1) if last else 1
    db.add(JobEvent(job_id=job.id, sequence=sequence, event_type=event_type, message=message, progress=progress))


async def dispatch_document_job(job_id: str, document_id: str, document_ids: list[str] | None = None) -> bool:
    if settings.inline_jobs:
        from services.worker.tasks import ingest_document_task_batch_async

        await ingest_document_task_batch_async(job_id, document_ids or [document_id])
        return True
    try:
        from services.worker.celery_app import celery_app

        celery_app.send_task("services.worker.tasks.ingest_document_task", args=[job_id, document_id, document_ids or [document_id]], queue="ingestion")
        return True
    except Exception:
        # The database job remains queued and the scheduler can recover it;
        # API availability must not depend on Redis being reachable.
        return False


async def dispatch_content_generation_job(job_id: str) -> bool:
    if settings.inline_jobs:
        from services.worker.content_tasks import content_generation_task_async

        await content_generation_task_async(job_id)
        return True
    try:
        from services.worker.celery_app import celery_app

        celery_app.send_task("services.worker.content_tasks.content_generation_task", args=[job_id], queue="agent")
        return True
    except Exception:
        # The durable job remains queued and is recovered by the scheduler.
        return False


async def dispatch_campaign_plan_job(job_id: str) -> bool:
    if settings.inline_jobs:
        from services.worker.pilot_tasks import campaign_plan_task_async

        await campaign_plan_task_async(job_id)
        return True
    try:
        from services.worker.celery_app import celery_app

        celery_app.send_task("services.worker.pilot_tasks.campaign_plan_task", args=[job_id], queue="agent")
        return True
    except Exception:
        return False


async def dispatch_meta_job(job_id: str, kind: str) -> bool:
    """Dispatch only committed Meta jobs; delivery failure leaves a recoverable queue row."""
    if kind not in {"meta_publish", "meta_metrics_sync"}:
        raise ValueError("unsupported Meta job kind")
    if settings.inline_jobs:
        from services.worker.meta_tasks import meta_job_async

        await meta_job_async(job_id, kind)
        return True
    try:
        from services.worker.celery_app import celery_app

        celery_app.send_task("services.worker.meta_tasks.meta_job", args=[job_id, kind], queue="default")
        return True
    except Exception:
        return False


async def dispatch_research_job(job_id: str) -> bool:
    """Dispatch a durable market-research cycle after its database commit."""
    if settings.inline_jobs:
        from services.worker.research_tasks import market_research_task_async

        await market_research_task_async(job_id)
        return True
    try:
        from services.worker.celery_app import celery_app

        celery_app.send_task("services.worker.research_tasks.market_research_task", args=[job_id], queue="agent")
        return True
    except Exception:
        return False


async def _record_dispatch(db: AsyncSession, job_id: str, sent: bool) -> None:
    job = await db.get(Job, job_id)
    if job is None:
        return
    job.dispatch_attempts += 1
    job.last_dispatch_at = datetime.now(timezone.utc)
    job.last_dispatch_error = None if sent else "queue_unavailable"
    await db.commit()


async def dispatch_queued_jobs(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    jobs = (
        await db.scalars(
            select(Job)
            .where(Job.status == "queued", or_(Job.lease_until.is_(None), Job.lease_until <= now))
            .order_by(Job.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
    ).all()
    count = 0
    dispatch: list[tuple[str, str, list[str]]] = []
    content_dispatch: list[str] = []
    plan_dispatch: list[str] = []
    meta_dispatch: list[tuple[str, str]] = []
    research_dispatch: list[str] = []
    for job in jobs:
        if job.kind in {"content_generation", "content_revise"} and job.result and job.result.get("campaign_id"):
            if job.attempts >= settings.max_job_attempts:
                job.status = "failed"
                job.progress = 100
                job.finished_at = now
                job.lease_until = None
                job.error = {
                    "code": "retry_limit_exceeded",
                    "message": "Job đã hết số lần thử tự động.",
                    "hint": "Kiểm tra cấu hình AI và thử tạo yêu cầu mới.",
                    "retryable": False,
                }
                await append_job_event(db, job, "error", job.error["message"], 100)
                continue
            job.lease_until = now + timedelta(minutes=settings.job_lease_minutes)
            content_dispatch.append(job.id)
        elif job.kind == "campaign_plan" and job.result and job.result.get("prompt"):
            if job.attempts >= settings.max_job_attempts:
                job.status = "failed"
                job.progress = 100
                job.finished_at = now
                job.lease_until = None
                job.error = {"code": "retry_limit_exceeded", "message": "Yêu cầu lập kế hoạch đã hết số lần thử.", "retryable": False}
                continue
            job.lease_until = now + timedelta(minutes=settings.job_lease_minutes)
            plan_dispatch.append(job.id)
        elif job.kind == "document_ingest" and job.result and job.result.get("document_id"):
            if job.attempts >= settings.max_job_attempts:
                job.status = "failed"
                job.progress = 100
                job.finished_at = now
                job.lease_until = None
                job.error = {
                    "code": "retry_limit_exceeded",
                    "message": "Job đã hết số lần thử tự động.",
                    "hint": "Hãy kiểm tra tài liệu rồi gửi yêu cầu xử lý lại.",
                    "retryable": False,
                }
                await append_job_event(db, job, "error", job.error["message"], 100)
                continue
            document_id = str(job.result["document_id"])
            document_ids = [str(item) for item in job.result.get("document_ids", [document_id])]
            job.lease_until = now + timedelta(minutes=settings.job_lease_minutes)
            dispatch.append((job.id, document_id, document_ids))
        elif job.kind in {"meta_publish", "meta_metrics_sync"}:
            # Queued Meta publish jobs have not crossed the send boundary.
            # A running send is never returned to this queue by recovery.
            job.lease_until = now + timedelta(minutes=settings.job_lease_minutes)
            meta_dispatch.append((job.id, job.kind))
        elif job.kind == "market_research":
            if job.attempts >= settings.max_job_attempts:
                job.status = "failed"
                job.progress = 100
                job.finished_at = now
                job.lease_until = None
                job.error = {
                    "code": "retry_limit_exceeded",
                    "message": "Lượt nghiên cứu đã hết số lần thử tự động.",
                    "retryable": False,
                }
                continue
            job.lease_until = now + timedelta(minutes=settings.job_lease_minutes)
            research_dispatch.append(job.id)

    # Persist the lease before queue delivery. If Redis is unavailable, the
    # scheduler can safely retry after expiry without losing the DB job.
    if jobs:
        await db.commit()
    for job_id, document_id, document_ids in dispatch:
        sent = await dispatch_document_job(job_id, document_id, document_ids)
        await _record_dispatch(db, job_id, sent)
        count += int(sent)
    for job_id in content_dispatch:
        sent = await dispatch_content_generation_job(job_id)
        await _record_dispatch(db, job_id, sent)
        count += int(sent)
    for job_id in plan_dispatch:
        sent = await dispatch_campaign_plan_job(job_id)
        await _record_dispatch(db, job_id, sent)
        count += int(sent)
    for job_id, kind in meta_dispatch:
        sent = await dispatch_meta_job(job_id, kind)
        await _record_dispatch(db, job_id, sent)
        count += int(sent)
    for job_id in research_dispatch:
        sent = await dispatch_research_job(job_id)
        await _record_dispatch(db, job_id, sent)
        count += int(sent)
    return count
