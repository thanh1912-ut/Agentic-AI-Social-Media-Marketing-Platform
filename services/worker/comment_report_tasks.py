"""Durable writing-direction reports from pinned, screened comment summaries."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from database.job_fencing import JobLeaseLost, claim_job_fence, isolated_job_fence
from database.models import (
    AIUsageLedger, Brand, Job, MarketReport, MarketReportCommentAnalysis, MetaPageGroup,
    ResearchCycle, new_id, utcnow,
)
from services.api.config import settings
from services.api.db import SessionLocal
from services.research.comment_analysis import CommentAnalysisHeld
from services.research.comment_quarantine import CommentQuarantineUnavailable
from services.research.comment_reports import load_analysis
from services.agents.providers.errors import safe_provider_error_code
from . import research_tasks
from .async_runtime import run_worker_coroutine
from .celery_app import celery_app


async def _claim(job_id):
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id, Job.kind == "research_comment_report").with_for_update())
        if job is None or job.status != "queued":
            return None
        from .page_gate import block_job_without_active_page
        if await block_job_without_active_page(db, job):
            await db.commit()
            return None
        retry_at = (job.result or {}).get("retry_not_before")
        if retry_at and datetime.fromisoformat(retry_at) > utcnow():
            return None
        if not all(isinstance((job.result or {}).get(key), str) for key in ("source_id", "batch_id", "group_id")):
            job.status = "failed"
            job.error = {"code": "comment_report_context_missing", "message": "Thiếu nguồn báo cáo đã ghim."}
            job.finished_at = utcnow()
            await db.commit()
            return None
        cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job.id).with_for_update())
        if cycle is None:
            job.status = "failed"
            job.error = {"code": "comment_report_cycle_missing", "message": "Thiếu chu kỳ báo cáo đã ghim."}
            job.finished_at = utcnow()
            await db.commit()
            return None
        token = new_id()
        job.status = "running"
        job.claim_token = token
        job.started_at = job.started_at or utcnow()
        job.attempts += 1
        job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
        cycle.status = "running"
        await db.commit()
        claim_job_fence(job_id, token)
        return job.company_id, job.result["group_id"], job.result["source_id"], job.result["batch_id"], cycle.id


async def _context(company_id, group_id, source_id, batch_id, cycle_id):
    async with SessionLocal() as db:
        row = await load_analysis(db, company_id=company_id, group_id=group_id, source_id=source_id, batch_id=batch_id)
        group = await db.scalar(select(MetaPageGroup).where(MetaPageGroup.company_id == company_id, MetaPageGroup.id == group_id))
        if group is None:
            raise CommentAnalysisHeld("comment_report_group_missing")
        detached = MetaPageGroup(id=group.id, company_id=company_id, name=group.name, industry=group.industry,
            region=group.region, locale=group.locale, keywords_json=group.keywords_json)
        existing = await db.scalar(select(MarketReport.id).where(MarketReport.company_id == company_id,
            MarketReport.cycle_id == cycle_id))
        await db.commit()
        return row, detached, existing


async def _generate(context, group, row):
    pending = asyncio.create_task(research_tasks._make_report(context[0], context[-1], group, [], [], [], [row]))
    try:
        while True:
            try:
                return await asyncio.wait_for(asyncio.shield(pending), timeout=10)
            except TimeoutError:
                async with SessionLocal() as db:
                    await db.commit()  # Fenced heartbeat; stale worker cannot proceed.
    finally:
        if not pending.done():
            pending.cancel()


async def _finish(job_id, *, code=None, report_id=None, deferred=False):
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None:
            return
        cycle = await db.scalar(select(ResearchCycle).where(ResearchCycle.job_id == job_id).with_for_update())
        now = utcnow()
        job.status = "queued" if deferred else "failed" if code else "succeeded"
        job.finished_at = None if deferred else now
        job.error = {"code": code, "message": "Báo cáo hướng viết chưa hoàn tất; phân tích bình luận đã lưu vẫn còn.",
                     "retryable": deferred} if code else None
        job.result = {key: value for key, value in (job.result or {}).items() if key != "retry_not_before"}
        if report_id:
            job.result = {**job.result, "report_id": report_id}
        if deferred:
            tomorrow = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date() + timedelta(days=1)
            job.lease_until = datetime.combine(tomorrow, datetime.min.time(), ZoneInfo("Asia/Ho_Chi_Minh")).astimezone(timezone.utc)
            job.result = {**job.result, "retry_not_before": job.lease_until.isoformat()}
            job.attempts = 0
        else:
            job.lease_until = None
        if cycle:
            cycle.status = "queued" if deferred else "failed" if code else "succeeded"
            cycle.completed_at = None if deferred else now
        job.claim_token = new_id()
        await db.commit()


async def _store(context, input_row, report_json, model_name):
    company_id, group_id, source_id, batch_id, cycle_id = context
    original_profile = report_json.get("business_profile_context", {})
    async with SessionLocal() as db:
        row = await load_analysis(db, company_id=company_id, group_id=group_id, source_id=source_id, batch_id=batch_id)
        await db.scalar(select(Brand).where(Brand.company_id == company_id).with_for_update())
        _profile, current_profile = await research_tasks._owner_brand_context_from_db(db, company_id)
        if current_profile != original_profile:
            raise CommentAnalysisHeld("comment_report_brand_changed")
        if row != input_row:
            raise CommentAnalysisHeld("comment_report_analysis_changed")
        pin = {key: row[key] for key in ("batch_id", "source_id", "input_hash", "result_hash", "completed_at", "coverage")}
        report_json = {**report_json, "comment_analysis_refs": [pin], "evidence_refs": [], "source_audience": []}
        report = MarketReport(id=new_id(), company_id=company_id, group_id=group_id, cycle_id=cycle_id,
            window_start=datetime.fromisoformat(row["completed_at"]), window_end=utcnow(), report_json=report_json,
            evidence_ids_json=[], coverage_json={"ai_status": "completed", "comment_analysis_ids": [batch_id],
                "privacy_coverage": report_json.get("privacy_coverage", {}), "analysis_scope": "selected_screened_comments",
                "business_profile_context": report_json.get("business_profile_context", {})}, model_name=model_name)
        db.add(report)
        await db.flush()
        db.add(MarketReportCommentAnalysis(company_id=company_id, group_id=group_id, report_id=report.id,
            source_id=source_id, batch_id=batch_id, input_hash=row["input_hash"], result_hash=row["result_hash"]))
        ledger = await db.scalar(select(AIUsageLedger).where(AIUsageLedger.company_id == company_id,
            AIUsageLedger.request_key == "research-report:" + cycle_id).with_for_update())
        if ledger is not None:
            ledger.result_json = None
        await db.commit()
        return report.id


@isolated_job_fence
async def comment_report_task_async(job_id):
    context = await _claim(job_id)
    if context is None:
        return
    try:
        row, group, existing = await _context(*context)
        if existing:
            await _finish(job_id, report_id=existing)
            return
        report, model_name, status = await _generate(context, group, row)
        if status != "completed":
            await _finish(job_id, code=status, deferred=status == "deferred_budget")
            return
        report_id = await _store(context, row, report, model_name)
        await _finish(job_id, report_id=report_id)
    except JobLeaseLost:
        return
    except (CommentAnalysisHeld, CommentQuarantineUnavailable) as error:
        await _finish(job_id, code=error.code if isinstance(error, CommentAnalysisHeld) else "comment_encryption_unavailable")
    except Exception as error:
        await _finish(job_id, code=safe_provider_error_code(error))


@celery_app.task(name="services.worker.comment_report_tasks.comment_report_task", acks_late=True, reject_on_worker_lost=True)
def comment_report_task(job_id):
    run_worker_coroutine(comment_report_task_async(job_id))
