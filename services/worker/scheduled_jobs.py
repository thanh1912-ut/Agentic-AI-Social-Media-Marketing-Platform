"""Recovery scheduler. Durable due work is scanned from PostgreSQL."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from database.models import Job
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
                job.status = "queued"
                job.lease_until = None
            count = await dispatch_queued_jobs(db)
            await db.commit()
            return count

    return asyncio.run(run())
