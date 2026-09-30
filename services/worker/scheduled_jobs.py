"""Recovery scheduler. Durable due work is scanned from PostgreSQL."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from database.models import (
    CampaignPost, Company, Job, JobStep, MarketObservation, Membership, MetaPageConnection,
    MetaPageGroup, MetaPublication, MetaSyncState, ResearchCycle, ResearchSource,
    ScheduledMetaPublication, new_id,
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
        company = await db.scalar(select(Company).where(Company.id == group.company_id))
        if company is None or company.page_connection_state != "active" or not company.page_id:
            # Keep each source's schedule intent/checkpoint, but stop polling a
            # due group every minute while its Owner must reconnect the Page.
            group.next_due_at = None
            continue
        due_sources = (await db.scalars(select(ResearchSource).where(
            ResearchSource.company_id == group.company_id,
            ResearchSource.group_id == group.id,
            ResearchSource.active.is_(True),
            ResearchSource.schedule_enabled.is_(True),
            ResearchSource.next_due_at.is_not(None),
            ResearchSource.next_due_at <= now,
            or_(
                ResearchSource.status.in_(["active", "error"]),
                and_(ResearchSource.source_type == "owned_facebook_page", ResearchSource.status == "needs_access"),
            ),
        ).order_by(ResearchSource.next_due_at).with_for_update(skip_locked=True))).all()
        source_ids = [source.id for source in due_sources]
        if not source_ids:
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
            status="queued", progress=0, result={"group_id": group.id, "source_ids": source_ids},
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


async def _enqueue_due_meta_publications(db, now: datetime) -> int:
    rows = (await db.scalars(
        select(ScheduledMetaPublication)
        .where(ScheduledMetaPublication.status == "scheduled", ScheduledMetaPublication.scheduled_at <= now)
        .order_by(ScheduledMetaPublication.scheduled_at)
        .limit(100)
        .with_for_update(skip_locked=True)
    )).all()
    enqueued = 0
    for schedule in rows:
        job = await db.scalar(select(Job).where(Job.id == schedule.job_id, Job.company_id == schedule.company_id).with_for_update())
        post = await db.scalar(select(CampaignPost).where(
            CampaignPost.company_id == schedule.company_id, CampaignPost.id == schedule.post_id,
        ).with_for_update())
        if job is None or post is None or job.status != "queued" or post.current_version != schedule.post_version or post.status != "scheduled":
            schedule.status = "failed"
            schedule.active_key = None
            schedule.updated_at = now
            if job is not None and job.status == "queued":
                job.status = "failed"
                job.progress = 100
                job.finished_at = now
                job.error = {"code": "schedule_context_changed", "message": "Bản đã duyệt hoặc Fanpage đã thay đổi; lịch không được gửi.", "retryable": False}
            continue
        company = await db.scalar(select(Company).where(Company.id == schedule.company_id).with_for_update())
        if company is None or company.page_connection_state != "active" or company.page_id != schedule.page_id:
            schedule.status = "failed"
            schedule.active_key = None
            schedule.updated_at = now
            job.status = "failed"
            job.progress = 100
            job.finished_at = now
            job.error = {
                "code": "page_needs_reconnect",
                "message": "Fanpage cần được kết nối lại. Lịch này chưa được gửi; hãy kiểm tra và lên lịch mới sau khi kết nối.",
                "retryable": False,
            }
            if post.status == "scheduled" and post.current_version == schedule.post_version:
                post.status = "approved"
                post.publish_mode = None
                post.scheduled_at = None
                post.updated_at = now
            for step in (await db.scalars(select(JobStep).where(JobStep.job_id == job.id))).all():
                step.status, step.progress, step.finished_at = "failed", 100, now
                step.error = job.error
                step.message = job.error["message"]
            continue
        if now - schedule.scheduled_at > timedelta(minutes=15):
            schedule.status = "missed"
            schedule.active_key = None
            schedule.updated_at = now
            job.status = "failed"
            job.progress = 100
            job.finished_at = now
            job.error = {"code": "schedule_missed", "message": "Máy không chạy đúng giờ; hãy chọn giờ mới để đăng.", "retryable": False}
            post.status = "approved"
            post.publish_mode = None
            post.scheduled_at = None
            post.updated_at = now
            for step in (await db.scalars(select(JobStep).where(JobStep.job_id == job.id))).all():
                step.status, step.progress, step.finished_at = "failed", 100, now
                step.error = job.error
                step.message = job.error["message"]
            continue
        publication = await db.scalar(select(MetaPublication).where(
            MetaPublication.company_id == schedule.company_id,
            MetaPublication.active_key == schedule.active_key,
        ))
        if publication is None:
            publication = MetaPublication(
                company_id=schedule.company_id, post_id=schedule.post_id,
                post_version=schedule.post_version,
                approved_content_sha256=schedule.approved_content_sha256,
                page_id=schedule.page_id, connection_id=schedule.connection_id,
                status="queued", active_key=schedule.active_key, job_id=job.id,
            )
            db.add(publication)
            await db.flush()
        schedule.publication_id = publication.id
        schedule.status = "queued"
        schedule.updated_at = now
        job.kind = "meta_publish"
        job.result = {"schedule_id": schedule.id, "publication_id": publication.id,
                      "post_id": schedule.post_id, "version": schedule.post_version,
                      "scheduled_at": schedule.scheduled_at.isoformat()}
        for step in (await db.scalars(select(JobStep).where(JobStep.job_id == job.id))).all():
            step.step_key = "publish"
            step.label = "Gửi bài đã lên lịch lên Fanpage"
            step.status = "pending"
        enqueued += 1
    if rows:
        await db.flush()
    return enqueued


async def _enqueue_due_meta_metrics(db, now: datetime) -> int:
    connections = (await db.scalars(
        select(MetaPageConnection)
        .join(Company, Company.id == MetaPageConnection.company_id)
        .where(
            Company.page_id == MetaPageConnection.page_id,
            Company.page_connection_state == "active",
            MetaPageConnection.active.is_(True), MetaPageConnection.status == "verified",
            MetaPageConnection.verified_at.is_not(None),
            MetaPageConnection.metrics_schedule_enabled.is_(True),
            MetaPageConnection.next_metrics_sync_at.is_not(None),
            MetaPageConnection.next_metrics_sync_at <= now,
        )
        .order_by(MetaPageConnection.next_metrics_sync_at)
        .limit(50)
        .with_for_update(skip_locked=True)
    )).all()
    enqueued = 0
    for connection in connections:
        interval = max(1, min(connection.metrics_sync_interval_hours or 6, 24 * 30))
        owner_id = await db.scalar(select(Membership.user_id).where(
            Membership.company_id == connection.company_id,
            Membership.role == "owner", Membership.is_active.is_(True),
        ).limit(1))
        creator_id = owner_id or await db.scalar(select(Membership.user_id).where(
            Membership.company_id == connection.company_id, Membership.is_active.is_(True),
        ).limit(1))
        state = await db.scalar(select(MetaSyncState).where(
            MetaSyncState.company_id == connection.company_id,
            MetaSyncState.page_id == connection.page_id,
        ).with_for_update())
        if not creator_id or state is None or not state.verified_at:
            connection.next_metrics_sync_at = now + timedelta(hours=interval)
            continue
        if state.running_job_id:
            current = await db.get(Job, state.running_job_id)
            if current is not None and current.status in {"queued", "running"}:
                connection.next_metrics_sync_at = now + timedelta(hours=interval)
                continue
        job = Job(
            company_id=connection.company_id, created_by=creator_id,
            kind="meta_metrics_sync", title="Đồng bộ số liệu Fanpage theo lịch",
            status="queued", progress=0,
            result={"page_id": connection.page_id, "connection_id": connection.id, "scheduled": True},
        )
        db.add(job)
        await db.flush()
        state.running_job_id = job.id
        state.updated_at = now
        connection.next_metrics_sync_at = now + timedelta(hours=interval)
        db.add(JobStep(job_id=job.id, step_key="sync", label="Đọc bài đăng và số liệu Fanpage", status="pending"))
        enqueued += 1
    if connections:
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
    deleted = 0
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
            deleted += 1
    if deleted:
        await db.flush()
    return deleted


@celery_app.task
def recover_due_jobs() -> int:
    async def run() -> int:
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            await _enqueue_due_research(db, now)
            await _enqueue_due_meta_publications(db, now)
            await _enqueue_due_meta_metrics(db, now)
            from .research_comments import enqueue_comment_batches, purge_expired_comment_quarantine
            await purge_expired_comment_quarantine(db, now)
            await enqueue_comment_batches(db, now)
            stale = (await db.scalars(select(Job).where(Job.status == "running", Job.lease_until.is_not(None), Job.lease_until < now))).all()
            for job in stale:
                job.lease_until = None
                # Revoke the previous delivery before returning the durable row
                # to the queue, including when the replacement claim has not
                # happened yet.
                job.claim_token = new_id()
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
