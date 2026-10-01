"""Durable Gemini analysis of explicitly screened excerpts, with budget/fencing.

No collector bodies, author identities or credentials are copied to the job or
usage ledger. A provider timeout remains uncertain; replay never calls again.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from database.job_fencing import JobLeaseLost, claim_job_fence, isolated_job_fence
from database.models import Job, ResearchCommentAnalysisBatch, new_id, utcnow
from services.api.config import settings
from services.api.db import SessionLocal
from services.agents.providers.comment_contracts import CommentAnalysis
from services.agents.providers.errors import ProviderContextLimitError, ProviderOutputError, safe_provider_error_code
from services.research.comment_analysis import CommentAnalysisHeld, approved_input, lock_source, validate_screened_text
from services.research.comment_quarantine import CommentQuarantineUnavailable
from .ai_budget import (
    PricingUnavailable, mark_automatic_request_unknown, release_unsubmitted_request,
    reserve_automatic_request, settle_automatic_request,
)
from .async_runtime import run_worker_coroutine
from .celery_app import celery_app
from .interactive_ai import provider_reservation_parameters
from .model_provider import AIConfigurationError, configured_structured_model


async def _claim(job_id):
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id, Job.kind == "research_comment_analysis").with_for_update())
        if job is None or job.status != "queued":
            return None
        from .page_gate import block_job_without_active_page
        if await block_job_without_active_page(db, job):
            await db.commit()
            return None
        result = job.result or {}
        retry_at = result.get("retry_not_before")
        if retry_at and datetime.fromisoformat(retry_at) > utcnow():
            return None
        if not all(isinstance(result.get(key), str) for key in ("source_id", "batch_id")):
            job.status = "failed"
            job.error = {"code": "comment_analysis_context_missing", "message": "Thiếu lô bình luận đã kiểm tra."}
            job.finished_at = utcnow()
            await db.commit()
            return None
        token = new_id()
        job.claim_token = token
        job.status = "running"
        job.started_at = job.started_at or utcnow()
        job.attempts += 1
        job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
        await db.commit()
        claim_job_fence(job_id, token)
        return job.company_id, result["source_id"], result["batch_id"]


async def _input(company_id, source_id, batch_id):
    async with SessionLocal() as db:
        batch, data = await approved_input(db, company_id=company_id, source_id=source_id, batch_id=batch_id)
        if batch.status != "completed":
            batch.status = "running"
        completed = batch.status == "completed" and batch.result_json is not None
        await db.commit()
        return data, completed


async def _finish(job_id, *, code=None, deferred=False):
    async with SessionLocal() as db:
        await db.flush()
        job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None:
            return
        source_id, batch_id = job.result["source_id"], job.result["batch_id"]
        # Same lock order as erasure. A removed source can still finish its job.
        try:
            await lock_source(db, job.company_id, source_id)
        except CommentAnalysisHeld:
            code = "comment_source_erased"
        batch = await db.scalar(select(ResearchCommentAnalysisBatch).where(
            ResearchCommentAnalysisBatch.company_id == job.company_id,
            ResearchCommentAnalysisBatch.id == batch_id).with_for_update())
        if batch is None or batch.status in {"suppressed", "expired"}:
            code, deferred = "comment_analysis_unavailable", False
        if batch and batch.status not in {"suppressed", "expired", "completed"}:
            batch.status = "deferred_budget" if deferred else "failed" if code else "completed"
            batch.error_code = code
        job.status = "queued" if deferred else "failed" if code else "succeeded"
        job.error = {"code": code, "message": "Phân tích bình luận chưa hoàn tất; dữ liệu thu thập được giữ riêng.",
                     "retryable": deferred} if code else None
        job.finished_at = None if deferred else utcnow()
        if deferred:
            tomorrow = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date() + timedelta(days=1)
            job.lease_until = datetime.combine(tomorrow, datetime.min.time(), ZoneInfo("Asia/Ho_Chi_Minh")).astimezone(timezone.utc)
            job.result = {**job.result, "retry_not_before": job.lease_until.isoformat()}
            job.attempts = 0  # Budget wait is not a failed provider attempt.
        else:
            job.lease_until = None
            job.result = {key: value for key, value in job.result.items() if key != "retry_not_before"}
        job.claim_token = new_id()
        await db.commit()


async def _call_with_heartbeat(model, data):
    # HTTPX enforces the adapter's <=60-second request timeout. Cancelling a
    # to_thread await cannot undo a request already received by the provider.
    pending = asyncio.create_task(asyncio.to_thread(model.summarize_screened_comments, batch=data))
    try:
        while True:
            try:
                return await asyncio.wait_for(asyncio.shield(pending), timeout=10)
            except TimeoutError:
                async with SessionLocal() as db:
                    await db.commit()  # Fenced heartbeat; lost lease raises.
    finally:
        if not pending.done():
            pending.cancel()


async def _store_result(company_id, source_id, batch_id, data, parsed):
    parsed = CommentAnalysis.model_validate(parsed.model_dump())
    allowed = {item.evidence_ref for item in data.comments}
    if any(ref not in allowed for topic in parsed.topics for ref in topic.evidence_refs):
        raise ProviderOutputError("Comment citation is outside the approved selection")
    for topic in parsed.topics:
        validate_screened_text(topic.topic)
        validate_screened_text(topic.summary)
    for limitation in parsed.limitations:
        validate_screened_text(limitation)
    async with SessionLocal() as db:
        batch, current = await approved_input(db, company_id=company_id, source_id=source_id, batch_id=batch_id)
        if current.model_dump() != data.model_dump():
            raise CommentAnalysisHeld("comment_analysis_selection_changed")
        batch.result_json = parsed.model_dump(mode="json")
        batch.status = "completed"
        batch.error_code = None
        batch.completed_at = utcnow()
        await db.commit()


@isolated_job_fence
async def comment_analysis_task_async(job_id):
    context = await _claim(job_id)
    if context is None:
        return
    company_id, source_id, batch_id = context
    reservation = None
    submitted = False
    try:
        data, completed = await _input(*context)
        if completed:
            await _finish(job_id)
            return
        model = configured_structured_model()
        if getattr(model, "provider_name", None) != "gemini" or model.model_name != "gemini-3.8-flash":
            raise AIConfigurationError("Screened comment role requires the selected Gemini model")
        reservation = await reserve_automatic_request(company_id=company_id, request_key=f"comment-analysis:{batch_id}",
            provider="gemini", model=model.model_name, operation="research_comment_analysis",
            **provider_reservation_parameters(model))
        if reservation.status == "deferred_budget":
            await _finish(job_id, code="deferred_budget", deferred=True)
            return
        if reservation.status != "reserved":
            await _finish(job_id, code="provider_outcome_unknown")
            return
        # Revalidate after reserving, just before the external request. No DB
        # locks are kept while waiting for the provider response.
        data, _ = await _input(*context)
        submitted = True
        parsed, metadata = await _call_with_heartbeat(model, data)
        await _store_result(*context, data, parsed)
        # Only a pointer is cached in the billing ledger, never comment-derived
        # text; suppression clears the canonical result without stale copies.
        await settle_automatic_request(company_id=company_id, reservation=reservation,
            provider="gemini", model=getattr(metadata, "model", None) or model.model_name,
            input_tokens=getattr(metadata, "input_tokens", None), output_tokens=getattr(metadata, "output_tokens", None),
            result_json={"comment_analysis_batch_id": batch_id})
        await _finish(job_id)
    except JobLeaseLost:
        # A reservation is retained for reconciliation; a stale delivery cannot
        # settle or write result bodies through a new worker's lease.
        return
    except (AIConfigurationError, PricingUnavailable) as error:
        await _finish(job_id, code="pricing_unavailable" if isinstance(error, PricingUnavailable) else "provider_not_configured")
    except ProviderContextLimitError:
        if reservation:
            await release_unsubmitted_request(company_id=company_id, reservation=reservation)
        await _finish(job_id, code="input_limit_exceeded")
    except (CommentAnalysisHeld, CommentQuarantineUnavailable) as error:
        if reservation:
            if submitted:
                await mark_automatic_request_unknown(company_id=company_id, reservation=reservation,
                    error_code="comment_context_invalidated")
            else:
                await release_unsubmitted_request(company_id=company_id, reservation=reservation)
        await _finish(job_id, code=error.code if isinstance(error, CommentAnalysisHeld) else "comment_encryption_unavailable")
    except Exception as error:
        if reservation:
            await mark_automatic_request_unknown(company_id=company_id, reservation=reservation,
                error_code=safe_provider_error_code(error))
        await _finish(job_id, code=safe_provider_error_code(error))


@celery_app.task(name="services.worker.comment_analysis_tasks.comment_analysis_task", acks_late=True,
                 reject_on_worker_lost=True)
def comment_analysis_task(job_id):
    run_worker_coroutine(comment_analysis_task_async(job_id))
