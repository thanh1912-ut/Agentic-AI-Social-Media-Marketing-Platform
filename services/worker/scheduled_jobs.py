"""Recovery scheduler. Durable due work is scanned from PostgreSQL."""

from datetime import datetime, timezone

from sqlalchemy import select

from database.models import Job, JobStep, MetaPublication
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.job_service import dispatch_queued_jobs
from .async_runtime import run_worker_coroutine
from .celery_app import celery_app


@celery_app.task
def recover_due_jobs() -> int:
    async def run() -> int:
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
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
            count = await dispatch_queued_jobs(db)
            await db.commit()
            return count

    return run_worker_coroutine(run())
