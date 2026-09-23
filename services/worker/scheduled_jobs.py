"""Recovery scheduler. Durable due work is scanned from PostgreSQL."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from database.models import Job
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.job_service import dispatch_queued_jobs
from .celery_app import celery_app


@celery_app.task
def recover_due_jobs() -> int:
    async def run() -> int:
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            stale = (await db.scalars(select(Job).where(Job.status == "running", Job.lease_until.is_not(None), Job.lease_until < now))).all()
            for job in stale:
                job.lease_until = None
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

    return asyncio.run(run())
