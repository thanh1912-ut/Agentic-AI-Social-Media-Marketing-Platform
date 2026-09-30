"""Durable purge of research data collected from one disabled source.

The job removes app-managed source evidence and invalidates reports that used
it. It is not a legal-erasure certification and cannot remove copies already
published/exported, provider-side data, or backups outside this application.
"""

from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy import delete, select

from database.job_fencing import claim_job_fence, isolated_job_fence
from database.models import (
    AIUsageLedger,
    AuditEvent,
    Campaign,
    CampaignBriefRevisionDraft,
    Job,
    JobEvent,
    JobStep,
    MarketEvidence,
    MarketEvidenceVersion,
    MarketObservation,
    MarketReport,
    MarketReportEvidence,
    MarketReportWebSnapshot,
    ResearchCycle,
    ResearchPrivacyPolicyRevision,
    ResearchSource,
    ResearchSourceErasure,
    ResearchSourceErasureObject,
    ResearchSourceMetricSnapshot,
    WebCrawlPage,
    WebCrawlRun,
    WebEntity,
    WebEntitySnapshot,
    WebOfferSnapshot,
    new_id,
    utcnow,
)
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.storage import storage
from services.worker.async_runtime import run_worker_coroutine
from services.worker.celery_app import celery_app


OBJECT_BATCH_SIZE = 50


def _owns_lease(job: Job, claim_token: str) -> bool:
    lease_until = job.lease_until
    if lease_until is not None and lease_until.tzinfo is None:
        lease_until = lease_until.replace(tzinfo=timezone.utc)
    return (
        job.status == "running"
        and job.claim_token == claim_token
        and lease_until is not None
        and lease_until > utcnow()
    )


async def _event(db, job: Job, message: str, progress: int) -> None:
    last = await db.scalar(
        select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.sequence.desc())
    )
    db.add(JobEvent(
        job_id=job.id,
        sequence=last.sequence + 1 if last else 1,
        event_type="progress",
        message=message,
        progress=progress,
        at=utcnow(),
    ))
    job.progress = progress


async def _claim(job_id: str) -> str | None:
    claim_token = new_id()
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(
            Job.id == job_id, Job.kind == "research_source_erasure",
        ).with_for_update())
        if job is None or job.status != "queued":
            return None
        request = await db.scalar(select(ResearchSourceErasure).where(
            ResearchSourceErasure.company_id == job.company_id,
            ResearchSourceErasure.job_id == job.id,
        ).with_for_update())
        if request is None:
            job.status = "failed"
            job.error = {"code": "erasure_request_missing", "message": "Không tìm thấy yêu cầu xóa dữ liệu."}
            job.finished_at = utcnow()
            await db.commit()
            return None
        job.status = "running"
        job.started_at = job.started_at or utcnow()
        job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
        job.claim_token = claim_token
        job.attempts += 1
        request.status = "preparing"
        step = await db.scalar(select(JobStep).where(
            JobStep.job_id == job.id, JobStep.step_key == "purge_source_data",
        ))
        if step is not None:
            step.status = "running"
            step.started_at = step.started_at or utcnow()
            step.message = "Đang chuẩn bị xóa dữ liệu đã thu thập từ nguồn."
        await db.commit()
    claim_job_fence(job_id, claim_token)
    return claim_token


async def _prepare_storage_keys(job_id: str, claim_token: str) -> bool:
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None or not _owns_lease(job, claim_token):
            return
        request = await db.scalar(select(ResearchSourceErasure).where(
            ResearchSourceErasure.company_id == job.company_id,
            ResearchSourceErasure.job_id == job.id,
        ).with_for_update())
        if request is None:
            raise RuntimeError("research source erasure request disappeared")
        source = await db.scalar(select(ResearchSource).where(
            ResearchSource.company_id == job.company_id,
            ResearchSource.id == request.source_id,
        ).with_for_update())
        if source is None:
            raise RuntimeError("research source tombstone disappeared")
        if source.active:
            raise RuntimeError("research source was reactivated during data purge")

        evidence_ids = select(MarketEvidence.id).where(
            MarketEvidence.company_id == job.company_id,
            MarketEvidence.source_id == source.id,
        )
        raw_rows = (await db.execute(select(
            MarketObservation.raw_object_key,
            MarketObservation.raw_upload_lease_until,
        ).where(
            MarketObservation.company_id == job.company_id,
            MarketObservation.evidence_id.in_(evidence_ids),
            MarketObservation.raw_object_key.is_not(None),
        ))).all()
        now = utcnow()
        active_upload_deadlines = []
        for _key, deadline in raw_rows:
            if deadline is None:
                continue
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if deadline > now:
                active_upload_deadlines.append(deadline)
        if active_upload_deadlines:
            # A worker has committed the storage key but may still be inside
            # object-store put(). Let its short lease expire (or let the
            # worker clear it on completion) before deleting, then recover the
            # durable purge job from PostgreSQL.
            ready_at = min(active_upload_deadlines)
            request.status = "waiting_for_raw_uploads"
            job.status = "queued"
            job.result = {"source_id": source.id, "phase": "waiting_for_raw_uploads"}
            job.finished_at = None
            job.lease_until = ready_at
            job.claim_token = None
            job.error = None
            step = await db.scalar(select(JobStep).where(
                JobStep.job_id == job.id, JobStep.step_key == "purge_source_data",
            ))
            if step is not None:
                step.status = "pending"
                step.progress = 5
                step.message = "Đang chờ worker hoàn tất ghi tệp raw trước khi xóa dữ liệu."
            await db.commit()
            return False
        existing_keys = set((await db.scalars(select(ResearchSourceErasureObject.object_key).where(
            ResearchSourceErasureObject.company_id == job.company_id,
            ResearchSourceErasureObject.erasure_id == request.id,
        ))).all())
        raw_keys = {key for key, _deadline in raw_rows if key}
        for key in raw_keys:
            if key and key not in existing_keys:
                db.add(ResearchSourceErasureObject(
                    id=new_id(), company_id=job.company_id, erasure_id=request.id,
                    object_key=key, status="pending",
                ))
        request.object_count = len(existing_keys | {key for key in raw_keys if key})
        request.status = "deleting_raw_objects"
        job.result = {"source_id": source.id, "phase": "deleting_raw_objects"}
        job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
        step = await db.scalar(select(JobStep).where(
            JobStep.job_id == job.id, JobStep.step_key == "purge_source_data",
        ))
        if step is not None:
            step.progress = 10
            step.message = "Đang xóa tệp raw đã lưu trước khi xóa bản ghi nghiên cứu."
        await db.commit()
        return True


async def _delete_storage_objects(job_id: str, claim_token: str) -> None:
    while True:
        async with SessionLocal() as db:
            job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job is None or not _owns_lease(job, claim_token):
                return
            request = await db.scalar(select(ResearchSourceErasure).where(
                ResearchSourceErasure.company_id == job.company_id,
                ResearchSourceErasure.job_id == job.id,
            ))
            if request is None:
                raise RuntimeError("research source erasure request disappeared")
            rows = (await db.scalars(select(ResearchSourceErasureObject).where(
                ResearchSourceErasureObject.company_id == job.company_id,
                ResearchSourceErasureObject.erasure_id == request.id,
                ResearchSourceErasureObject.status == "pending",
            ).order_by(ResearchSourceErasureObject.id).limit(OBJECT_BATCH_SIZE))).all()
            batch = [(row.id, row.object_key) for row in rows]
            await db.commit()
        if not batch:
            return

        deleted_ids: list[str] = []
        for object_id, key in batch:
            # Storage deletion is idempotent in both supported backends. If
            # the worker dies after this call, the pending row safely retries.
            await storage.delete(key)
            deleted_ids.append(object_id)

        async with SessionLocal() as db:
            job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job is None or not _owns_lease(job, claim_token):
                return
            rows = (await db.scalars(select(ResearchSourceErasureObject).where(
                ResearchSourceErasureObject.company_id == job.company_id,
                ResearchSourceErasureObject.id.in_(deleted_ids),
                ResearchSourceErasureObject.status == "pending",
            ).with_for_update())).all()
            for row in rows:
                row.status = "deleted"
            job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
            step = await db.scalar(select(JobStep).where(
                JobStep.job_id == job.id, JobStep.step_key == "purge_source_data",
            ))
            if step is not None:
                step.progress = 30
                step.message = "Đã xóa một lô tệp raw; dữ liệu trong database sẽ tiếp tục được xóa."
            await db.commit()


async def _finish_purge(job_id: str, claim_token: str) -> None:
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None or not _owns_lease(job, claim_token):
            return
        request = await db.scalar(select(ResearchSourceErasure).where(
            ResearchSourceErasure.company_id == job.company_id,
            ResearchSourceErasure.job_id == job.id,
        ).with_for_update())
        if request is None:
            raise RuntimeError("research source erasure request disappeared")
        if await db.scalar(select(ResearchSourceErasureObject.id).where(
            ResearchSourceErasureObject.company_id == job.company_id,
            ResearchSourceErasureObject.erasure_id == request.id,
            ResearchSourceErasureObject.status != "deleted",
        ).limit(1)):
            raise RuntimeError("research raw storage object deletion is incomplete")

        source = await db.scalar(select(ResearchSource).where(
            ResearchSource.company_id == job.company_id,
            ResearchSource.id == request.source_id,
        ).with_for_update())
        if source is None or source.active:
            raise RuntimeError("research source became active during data purge")

        evidence_ids = select(MarketEvidence.id).where(
            MarketEvidence.company_id == job.company_id,
            MarketEvidence.source_id == source.id,
        )
        entity_ids = select(WebEntity.id).where(
            WebEntity.company_id == job.company_id,
            WebEntity.source_id == source.id,
        )
        run_ids = select(WebCrawlRun.id).where(
            WebCrawlRun.company_id == job.company_id,
            WebCrawlRun.source_id == source.id,
        )

        evidence_report_ids = (await db.scalars(
            select(MarketReportEvidence.report_id)
            .join(MarketEvidence, (MarketEvidence.company_id == MarketReportEvidence.company_id)
                  & (MarketEvidence.id == MarketReportEvidence.evidence_id))
            .where(MarketEvidence.company_id == job.company_id, MarketEvidence.source_id == source.id)
            .distinct()
        )).all()
        web_report_ids = (await db.scalars(
            select(MarketReportWebSnapshot.report_id)
            .join(WebEntitySnapshot, (WebEntitySnapshot.company_id == MarketReportWebSnapshot.company_id)
                  & (WebEntitySnapshot.id == MarketReportWebSnapshot.snapshot_id))
            .join(WebEntity, (WebEntity.company_id == WebEntitySnapshot.company_id)
                  & (WebEntity.id == WebEntitySnapshot.entity_id))
            .where(WebEntity.company_id == job.company_id, WebEntity.source_id == source.id)
            .distinct()
        )).all()
        report_ids = set(evidence_report_ids) | set(web_report_ids)
        reports = []
        if report_ids:
            reports = (await db.scalars(select(MarketReport).where(
                MarketReport.company_id == job.company_id,
                MarketReport.id.in_(report_ids),
            ).with_for_update())).all()
            now = utcnow()
            for report in reports:
                # A mixed-source report is invalidated as a whole: preserving a
                # summary that combined the erased source with other sources
                # would leave its contribution impossible to separate safely.
                report.report_json = {
                    "status": "source_data_erased",
                    "message": "Dữ liệu nghiên cứu nguồn đã được xóa; báo cáo cũ không còn dùng để tạo nội dung.",
                }
                report.evidence_ids_json = []
                report.coverage_json = {"status": "source_data_erased", "source_data_removed": True}
                report.updated_at = now
            await db.execute(delete(MarketReportEvidence).where(
                MarketReportEvidence.company_id == job.company_id,
                MarketReportEvidence.report_id.in_(report_ids),
            ))
            await db.execute(delete(MarketReportWebSnapshot).where(
                MarketReportWebSnapshot.company_id == job.company_id,
                MarketReportWebSnapshot.report_id.in_(report_ids),
            ))

        # Remove references that would let a later worker replay the source or
        # regenerate analysis from a cached provider result.
        cycles = (await db.scalars(select(ResearchCycle).where(
            ResearchCycle.company_id == job.company_id,
            ResearchCycle.group_id == source.group_id,
        ).with_for_update())).all()
        cycle_ids: set[str] = set()
        for cycle in cycles:
            values = cycle.source_results_json if isinstance(cycle.source_results_json, list) else []
            kept_values = [
                item for item in values
                if not isinstance(item, dict) or item.get("source_id") != source.id
            ]
            if len(kept_values) != len(values):
                cycle_ids.add(cycle.id)
                cycle.source_results_json = kept_values
        if cycle_ids:
            ledgers = (await db.scalars(select(AIUsageLedger).where(
                AIUsageLedger.company_id == job.company_id,
            ).with_for_update())).all()
            for ledger in ledgers:
                if any(ledger.request_key == f"research-report:{cycle_id}" for cycle_id in cycle_ids):
                    ledger.result_json = None

        jobs = (await db.scalars(select(Job).where(
            Job.company_id == job.company_id,
            Job.kind == "market_research",
        ).with_for_update())).all()
        for old_job in jobs:
            result = old_job.result if isinstance(old_job.result, dict) else None
            if result is None:
                continue
            source_results = result.get("source_results")
            if isinstance(source_results, list):
                result = dict(result)
                result["source_results"] = [
                    item for item in source_results
                    if not isinstance(item, dict) or item.get("source_id") != source.id
                ]
                old_job.result = result

        # Remove user-saved references to an invalidated report so future
        # generation cannot pin it again. Generated/published copies are kept
        # for business audit; this endpoint is explicitly research-data scoped.
        campaigns = (await db.scalars(select(Campaign).where(
            Campaign.company_id == job.company_id,
        ).with_for_update())).all()
        invalidated_campaigns = 0
        campaigns_by_id = {campaign.id: campaign for campaign in campaigns}
        for campaign in campaigns:
            brief = campaign.brief_json if isinstance(campaign.brief_json, dict) else {}
            market_context = brief.get("market_research_context")
            if isinstance(market_context, dict) and market_context.get("report_id") in report_ids:
                brief = dict(brief)
                brief.pop("market_research_context", None)
                brief["market_research_context_invalidated"] = {"reason": "source_data_erased"}
                campaign.brief_json = brief
                campaign.version += 1
                campaign.updated_at = utcnow()
                invalidated_campaigns += 1

        # A pending analytics brief can otherwise be accepted after the
        # report it was based on has been tombstoned. Keep the draft record as
        # an audit marker, but remove its derived changes and make it
        # non-applicable through the existing pending_review state guard.
        invalidated_brief_drafts = 0
        drafts = (await db.scalars(select(CampaignBriefRevisionDraft).where(
            CampaignBriefRevisionDraft.company_id == job.company_id,
            CampaignBriefRevisionDraft.status == "pending_review",
        ).with_for_update())).all()
        for draft in drafts:
            result = draft.resulting_brief_json if isinstance(draft.resulting_brief_json, dict) else {}
            market_context = result.get("market_research_context")
            if not isinstance(market_context, dict) or market_context.get("report_id") not in report_ids:
                continue
            campaign = campaigns_by_id.get(draft.campaign_id)
            safe_brief = dict(campaign.brief_json) if campaign and isinstance(campaign.brief_json, dict) else {}
            safe_brief.pop("market_research_context", None)
            safe_brief["market_research_context_invalidated"] = {"reason": "source_data_erased"}
            draft.resulting_brief_json = safe_brief
            draft.changes_json = []
            draft.note = None
            draft.status = "invalidated"
            invalidated_brief_drafts += 1

        # Explicit deletes make dependency ordering the same on PostgreSQL and
        # SQLite integration tests, rather than relying on backend cascades.
        await db.execute(delete(WebCrawlPage).where(
            WebCrawlPage.company_id == job.company_id, WebCrawlPage.run_id.in_(run_ids),
        ))
        await db.execute(delete(WebOfferSnapshot).where(
            WebOfferSnapshot.company_id == job.company_id,
            WebOfferSnapshot.entity_snapshot_id.in_(select(WebEntitySnapshot.id).where(
                WebEntitySnapshot.company_id == job.company_id,
                WebEntitySnapshot.entity_id.in_(entity_ids),
            )),
        ))
        await db.execute(delete(WebEntitySnapshot).where(
            WebEntitySnapshot.company_id == job.company_id,
            WebEntitySnapshot.entity_id.in_(entity_ids),
        ))
        await db.execute(delete(WebEntity).where(
            WebEntity.company_id == job.company_id, WebEntity.id.in_(entity_ids),
        ))
        await db.execute(delete(WebCrawlRun).where(
            WebCrawlRun.company_id == job.company_id, WebCrawlRun.id.in_(run_ids),
        ))
        await db.execute(delete(ResearchSourceMetricSnapshot).where(
            ResearchSourceMetricSnapshot.company_id == job.company_id,
            ResearchSourceMetricSnapshot.source_id == source.id,
        ))
        await db.execute(delete(MarketObservation).where(
            MarketObservation.company_id == job.company_id,
            MarketObservation.evidence_id.in_(evidence_ids),
        ))
        await db.execute(delete(MarketEvidenceVersion).where(
            MarketEvidenceVersion.company_id == job.company_id,
            MarketEvidenceVersion.evidence_id.in_(evidence_ids),
        ))
        await db.execute(delete(MarketEvidence).where(
            MarketEvidence.company_id == job.company_id,
            MarketEvidence.id.in_(evidence_ids),
        ))
        await db.execute(delete(ResearchPrivacyPolicyRevision).where(
            ResearchPrivacyPolicyRevision.company_id == job.company_id,
            ResearchPrivacyPolicyRevision.source_id == source.id,
        ))
        await db.execute(delete(ResearchSourceErasureObject).where(
            ResearchSourceErasureObject.company_id == job.company_id,
            ResearchSourceErasureObject.erasure_id == request.id,
        ))

        source.name = "Nguồn đã xóa"
        source.url = f"https://deleted.invalid/{source.id}"
        source.normalized_url = source.url
        source.competitor_name = None
        source.connection_id = None
        source.collection_status = "erased"
        source.collection_last_method = None
        source.last_collection_attempt_at = None
        source.last_collection_success_at = None
        source.last_crawled_at = None
        source.next_due_at = None
        source.schedule_enabled = False
        source.error_json = None
        source.owned_page_backfill_cursor = None
        source.owned_page_backfill_page_id = None
        source.owned_page_backfill_window_start = None
        source.owned_page_backfill_complete = False
        source.owned_page_backfill_window_complete = False
        source.owned_page_backfill_pages_processed = 0
        source.latest_job_id = None
        source.active = False
        source.status = "erased"

        request.status = "completed"
        request.finished_at = utcnow()
        request.error_code = None
        job.status = "succeeded"
        job.progress = 100
        job.result = {
            "phase": "completed",
            "scope": "collected_source_data_and_invalidated_reports",
            "invalidated_reports": len(reports),
            "invalidated_campaign_briefs": invalidated_campaigns,
            "invalidated_brief_drafts": invalidated_brief_drafts,
            "external_copies_removed": False,
        }
        job.error = None
        job.finished_at = utcnow()
        job.lease_until = None
        step = await db.scalar(select(JobStep).where(
            JobStep.job_id == job.id, JobStep.step_key == "purge_source_data",
        ))
        if step is not None:
            step.status = "succeeded"
            step.progress = 100
            step.message = "Đã xóa dữ liệu đã thu thập và vô hiệu báo cáo liên quan. Bản đã xuất/đăng, provider và backup nằm ngoài phạm vi."
            step.finished_at = utcnow()
        db.add(AuditEvent(
            company_id=job.company_id, actor_user_id=request.requested_by,
            action="market.source.purge_completed", entity_type="research_source_erasure",
            entity_id=request.id,
            metadata_json={"invalidated_reports": len(reports), "invalidated_campaign_briefs": invalidated_campaigns},
        ))
        await db.commit()


@isolated_job_fence
async def research_source_erasure_task_async(job_id: str) -> None:
    claim_token = await _claim(job_id)
    if claim_token is None:
        return
    try:
        ready = await _prepare_storage_keys(job_id, claim_token)
        if not ready:
            return
        await _delete_storage_objects(job_id, claim_token)
        await _finish_purge(job_id, claim_token)
    except Exception:
        # Leave the durable job running with its pending object-key rows intact.
        # The normal lease-recovery loop will requeue it for an idempotent retry.
        raise


@celery_app.task(
    name="services.worker.research_erasure_tasks.research_source_erasure_task",
    acks_late=True,
    time_limit=1800,
    soft_time_limit=1700,
)
def research_source_erasure_task(job_id: str) -> None:
    run_worker_coroutine(research_source_erasure_task_async(job_id))
