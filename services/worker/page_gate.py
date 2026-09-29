"""Durable-job guard for workspaces that require a verified company Page."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    CampaignPost, Company, Job, JobEvent, JobStep, MetaPublication,
    MetaSyncState, ResearchCycle, ScheduledMetaPublication, utcnow,
)


async def block_job_without_active_page(db: AsyncSession, job: Job) -> bool:
    """Fail queued work before it can call an agent, collector, or publisher.

    Returns True when the job was blocked. The Company row is locked for the
    duration of the claim transaction so reconnect/disconnect changes serialize
    with the worker's activation check.
    """
    company = await db.scalar(
        select(Company).where(Company.id == job.company_id).with_for_update()
    )
    if company is not None and company.page_id and company.page_connection_state == "active":
        return False

    code = "page_connection_required" if company is None or not company.page_id else "page_needs_reconnect"
    message = (
        "Owner cần kết nối Fanpage doanh nghiệp trước khi tiếp tục tác vụ."
        if code == "page_connection_required"
        else "Fanpage cần được kết nối lại trước khi tiếp tục tác vụ. Dữ liệu cũ vẫn được giữ."
    )
    error = {"code": code, "message": message, "retryable": False}
    now = utcnow()
    job.status = "failed"
    job.progress = 100
    job.error = error
    job.finished_at = now
    job.lease_until = None
    job.claim_token = None

    steps = (await db.scalars(select(JobStep).where(JobStep.job_id == job.id))).all()
    for step in steps:
        if step.status in {"pending", "running"}:
            step.status = "failed"
            step.progress = 100
            step.message = message
            step.error = error
            step.finished_at = now

    cycle = await db.scalar(
        select(ResearchCycle).where(ResearchCycle.job_id == job.id).with_for_update()
    )
    if cycle is not None:
        cycle.status = "failed"

    if job.kind == "meta_publish":
        publication = await db.scalar(
            select(MetaPublication).where(MetaPublication.job_id == job.id).with_for_update()
        )
        if publication is not None and publication.status == "queued":
            publication.status = "failed"
            publication.active_key = None
            publication.error_json = error
            publication.updated_at = now
            post = await db.scalar(select(CampaignPost).where(
                CampaignPost.company_id == job.company_id,
                CampaignPost.id == publication.post_id,
            ).with_for_update())
            if post is not None and post.status == "scheduled":
                post.status = "approved"
                post.publish_mode = None
                post.scheduled_at = None
                post.updated_at = now
        schedule = await db.scalar(
            select(ScheduledMetaPublication).where(ScheduledMetaPublication.job_id == job.id).with_for_update()
        )
        if schedule is not None and schedule.status == "queued":
            schedule.status = "failed"
            schedule.active_key = None
            schedule.updated_at = now

    if job.kind == "meta_metrics_sync":
        page_id = str((job.result or {}).get("page_id") or "")
        if page_id:
            sync_state = await db.scalar(select(MetaSyncState).where(
                MetaSyncState.company_id == job.company_id,
                MetaSyncState.page_id == page_id,
            ).with_for_update())
            if sync_state is not None and sync_state.running_job_id == job.id:
                sync_state.running_job_id = None
                sync_state.updated_at = now

    last = await db.scalar(
        select(JobEvent)
        .where(JobEvent.job_id == job.id)
        .order_by(JobEvent.sequence.desc())
    )
    db.add(JobEvent(
        job_id=job.id,
        sequence=last.sequence + 1 if last else 1,
        event_type="error",
        message=message,
        progress=100,
        at=now,
    ))
    return True
