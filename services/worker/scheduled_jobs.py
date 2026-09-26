"""Recovery scheduler. Durable due work is scanned from PostgreSQL."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from database.models import (
    Job, JobStep, MarketObservation, Membership, MetaPageGroup, MetaPublication,
    ResearchCycle, ResearchSource, new_id,
)
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.job_service import dispatch_queued_jobs
from services.api.storage import storage
from .async_runtime import run_worker_coroutine
from .celery_app import celery_app


async def _enqueue_due_research(db, now: datetime) -> int:
    groups = (await db.scalars(
        select(MetaPageGroup)
        .where(MetaPageGroup.active.is_(True), MetaPageGroup.next_due_at.is_not(None),
               MetaPageGroup.next_due_at <= now)
        .order_by(MetaPageGroup.next_due_at)
        .limit(50)
        .with_for_update(skip_locked=True)
    )).all()
    enqueued = 0
    for group in groups:
        source_id = await db.scalar(select(ResearchSource.id).where(
            ResearchSource.company_id == group.company_id,
            ResearchSource.group_id == group.id,
            ResearchSource.active.is_(True),
            ResearchSource.schedule_enabled.is_(True),
            or_(
                ResearchSource.status.in_(["active", "error"]),
                and_(ResearchSource.source_type == "owned_facebook_page", ResearchSource.status == "needs_access"),
            ),
        ).limit(1))
        if not source_id:
            group.next_due_at = None
            continue
        creator_id = await db.scalar(
            select(Membership.user_id)
            .where(Membership.company_id == group.company_id, Membership.is_active.is_(True))
            .order_by(Membership.role.asc())
            .limit(1)
        )
        if not creator_id:
            group.next_due_at = now + timedelta(hours=12)
            continue
        cycle_key = f"scheduled:{group.next_due_at.strftime('%Y%m%dT%H%M%S')}"
        exists = await db.scalar(select(ResearchCycle.id).where(
            ResearchCycle.company_id == group.company_id,
            ResearchCycle.group_id == group.id,
            ResearchCycle.cycle_key == cycle_key,
        ))
        if exists:
            group.next_due_at = now + timedelta(hours=12)
            continue
        job_id = new_id()
        job = Job(
            id=job_id, company_id=group.company_id, created_by=creator_id,
            kind="market_research", title=f"Thu thập dữ liệu thị trường: {group.name}",
            status="queued", progress=0, result={"group_id": group.id},
            idempotency_key=f"market:{group.id}:{cycle_key}",
        )
        db.add(job)
        await db.flush()
        db.add(JobStep(job_id=job_id, step_key="collect_sources",
                       label="Đọc nguồn công khai và Fanpage đã kết nối", status="pending"))
        db.add(ResearchCycle(
            id=new_id(), company_id=group.company_id, group_id=group.id,
            job_id=job_id, cycle_key=cycle_key, status="queued", source_results_json=[],
        ))
        # A queued/running cycle owns the schedule until the worker finishes.
        group.next_due_at = None
        enqueued += 1
    if enqueued:
        await db.flush()
    return enqueued


async def _purge_expired_raw(db, now: datetime) -> int:
    rows = (await db.scalars(
        select(MarketObservation)
        .where(MarketObservation.raw_object_key.is_not(None), MarketObservation.raw_expires_at <= now)
        .order_by(MarketObservation.raw_expires_at)
        .limit(100)
        .with_for_update(skip_locked=True)
    )).all()
    for row in rows:
        key = row.raw_object_key
        if key:
            try:
                await storage.delete(key)
            except Exception:
                # Keep the DB key so the next recovery tick can retry deletion.
                continue
            row.raw_object_key = None
            row.raw_expires_at = None
    if rows:
        await db.flush()
    return len(rows)


@celery_app.task
def recover_due_jobs() -> int:
    async def run() -> int:
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            await _enqueue_due_research(db, now)
            stale = (await db.scalars(select(Job).where(Job.status == "running", Job.lease_until.is_not(None), Job.lease_until < now))).all()
            for job in stale:
                job.lease_until = None
                if job.kind == "meta_publish":
                    publication = await db.scalar(select(MetaPublication).where(
                        MetaPublication.job_id == job.id
                    ).with_for_update())
                    if publication is not None and publication.status == "queued":
                        # The worker never crossed the external-send boundary.
                        job.status = "queued"
                        continue
                    if publication is not None and publication.status == "sending":
                        publication.status = "outcome_unknown"
                        publication.error_json = {
                            "code": "meta_outcome_unknown",
                            "message": "Worker dừng khi gửi bài; hãy kiểm tra Fanpage trước khi đối soát.",
                        }
                        publication.updated_at = now
                    job.status = "failed"
                    job.progress = 100
                    job.finished_at = now
                    job.error = {
                        "code": "meta_outcome_unknown",
                        "message": "Chưa rõ bài đã đăng hay chưa; hệ thống không tự gửi lại.",
                        "retryable": False,
                    }
                    step = await db.scalar(select(JobStep).where(JobStep.job_id == job.id))
                    if step:
                        step.status = "failed"
                        step.progress = 100
                        step.finished_at = now
                        step.error = job.error
                    continue
                if job.kind == "meta_metrics_sync":
                    # A read-only import can be resumed from its stored cursor.
                    job.status = "queued"
                    continue
                if job.attempts >= settings.max_job_attempts:
                    job.status = "failed"
                    job.progress = 100
                    job.finished_at = now
                    job.error = {
                        "code": "retry_limit_exceeded",
                        "message": "Worker dừng giữa chừng và job đã hết số lần thử tự động.",
                        "hint": "Hãy kiểm tra tài liệu rồi gửi yêu cầu xử lý lại.",
                        "retryable": False,
                    }
                else:
                    job.status = "queued"
                    job.error = {
                        "code": "worker_lease_expired",
                        "message": "Worker trước đó đã dừng; job được đưa lại vào hàng đợi.",
                        "hint": "Hệ thống đang thử lại tự động.",
                        "retryable": True,
                    }
            await _purge_expired_raw(db, now)
            count = await dispatch_queued_jobs(db)
            await db.commit()
            return count

    return run_worker_coroutine(run())
