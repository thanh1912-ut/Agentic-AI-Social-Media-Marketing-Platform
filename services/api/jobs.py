"""Tenant-scoped job ledger endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Campaign, Job, JobEvent, JobStep, User, utcnow
from .config import settings
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf
from .errors import ApiProblem
from .job_service import accepted_response, dispatch_content_generation_job, dispatch_document_job, serialize_job
from .schemas import AcceptedResponse, JobEventOut, JobOut


router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _tenant_job(job_id: str, user: User, db: AsyncSession) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy job.")
    await membership_for(job.company_id, user, db)
    return job


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await serialize_job(db, await _tenant_job(job_id, user, db))


@router.get("/{job_id}/events", response_model=list[JobEventOut])
async def get_job_events(job_id: str, after_seq: int = Query(default=0, ge=0), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    job = await _tenant_job(job_id, user, db)
    events = (await db.scalars(select(JobEvent).where(JobEvent.job_id == job.id, JobEvent.sequence > after_seq).order_by(JobEvent.sequence))).all()
    return [JobEventOut(id=e.id, job_id=e.job_id, at=e.at, type=e.event_type, message=e.message, progress=e.progress) for e in events]


@router.post("/{job_id}/cancel", response_model=JobOut, dependencies=[Depends(require_csrf)])
async def cancel_job(job_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    job = await _tenant_job(job_id, user, db)
    if job.status not in {"queued", "running"}:
        raise ApiProblem(409, "state_conflict", "Job này không còn có thể huỷ.")
    job.status = "cancelled"
    job.finished_at = utcnow()
    job.lease_until = None
    result = dict(job.result or {})
    request = result.get("request") or {}
    slot_id = request.get("slot_id") if job.kind == "content_generation" else None
    if slot_id:
        campaign = await db.scalar(select(Campaign).where(
            Campaign.id == result.get("campaign_id"),
            Campaign.company_id == job.company_id,
        ).with_for_update())
        if campaign is not None:
            plan = campaign.content_plan_json or {"strategy_summary": "", "slots": []}
            updated_plan = {**plan, "slots": [dict(slot) for slot in plan.get("slots", [])]}
            slot = next((item for item in updated_plan["slots"] if item.get("id") == slot_id), None)
            if slot is not None and slot.get("generation_job_id") == job.id:
                slot.pop("generation_job_id", None)
                campaign.content_plan_json = updated_plan
                expected_campaign_version = result.get("campaign_version")
                context_is_current = campaign.version == expected_campaign_version
                campaign.version += 1
                campaign.updated_at = utcnow()
                if context_is_current:
                    result["campaign_version"] = campaign.version
                    job.result = result
    await db.commit()
    return await serialize_job(db, job)


@router.post("/{job_id}/retry", response_model=AcceptedResponse, status_code=202, dependencies=[Depends(require_csrf)])
async def retry_job(job_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    job = await _tenant_job(job_id, user, db)
    if job.status not in {"failed", "cancelled"}:
        raise ApiProblem(409, "state_conflict", "Job này không thể thử lại ở trạng thái hiện tại.")
    if job.kind not in {"document_ingest", "content_generation", "content_revise"}:
        raise ApiProblem(409, "state_conflict", "Loại job này chưa hỗ trợ thử lại.")
    document_id = (job.result or {}).get("document_id")
    has_content_payload = job.kind in {"content_generation", "content_revise"} and bool((job.result or {}).get("campaign_id"))
    if job.kind == "document_ingest" and not document_id:
        raise ApiProblem(409, "state_conflict", "Job không có dữ liệu để thử lại.")
    if job.kind in {"content_generation", "content_revise"} and not has_content_payload:
        raise ApiProblem(409, "state_conflict", "Job không có dữ liệu để thử lại.")
    if job.attempts >= settings.max_job_attempts:
        raise ApiProblem(409, "retry_limit_exceeded", "Job đã hết số lần thử tự động.", details={"max_attempts": settings.max_job_attempts})
    result = dict(job.result or {})
    request = result.get("request") or {}
    slot_id = request.get("slot_id") if job.kind == "content_generation" else None
    if slot_id:
        campaign = await db.scalar(select(Campaign).where(
            Campaign.id == result.get("campaign_id"),
            Campaign.company_id == job.company_id,
        ).with_for_update())
        if campaign is None:
            raise ApiProblem(409, "content_context_changed", "Không còn tìm thấy campaign để thử lại job này.")
        if campaign.version != result.get("campaign_version"):
            raise ApiProblem(409, "content_context_changed", "Campaign đã thay đổi sau khi job lỗi; hãy tạo yêu cầu sinh mới từ phiên bản hiện tại.")
        plan = campaign.content_plan_json or {"strategy_summary": "", "slots": []}
        updated_plan = {**plan, "slots": [dict(slot) for slot in plan.get("slots", [])]}
        slot = next((item for item in updated_plan["slots"] if item.get("id") == slot_id), None)
        if slot is None or slot.get("generated_post_id") or slot.get("generation_job_id"):
            raise ApiProblem(409, "content_slot_locked", "Slot không còn sẵn sàng để thử lại.")
        slot["generation_job_id"] = job.id
        campaign.content_plan_json = updated_plan
        campaign.version += 1
        campaign.updated_at = utcnow()
        result["campaign_version"] = campaign.version
        job.result = result
    job.status = "queued"
    job.progress = 0
    job.error = None
    job.finished_at = None
    job.lease_until = None
    for step in (await db.scalars(select(JobStep).where(JobStep.job_id == job.id))).all():
        step.status = "pending"
        step.progress = None
        step.message = None
        step.error = None
        step.started_at = None
        step.finished_at = None
    await db.commit()
    if job.kind == "document_ingest":
        await dispatch_document_job(job.id, str(document_id))
    else:
        await dispatch_content_generation_job(job.id)
    return await accepted_response(db, job)
