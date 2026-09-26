"""Async SQLAlchemy session factory."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select, update

from database.job_fencing import JobLeaseLost, active_job_fence
from database.models import Base, Job, utcnow
from .config import settings


if settings.database_url.startswith("sqlite"):
    Path(".data").mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)


class FencedAsyncSession(AsyncSession):
    """Reject a worker transaction after another delivery has claimed its job."""

    def __init__(self, *args, **kwargs) -> None:
        # ORM autoflush could write a terminal job state before commit() gets
        # a chance to validate the lease. Fenced worker sessions therefore
        # flush only at explicit, lease-checked boundaries.
        if active_job_fence() is not None:
            kwargs["autoflush"] = False
        super().__init__(*args, **kwargs)

    async def _assert_job_fence(self) -> tuple[str, str] | None:
        fence = active_job_fence()
        if fence is None:
            return None
        job_id, claim_token = fence
        now = utcnow()
        with self.no_autoflush:
            row = (
                await self.execute(
                    select(Job.status, Job.claim_token, Job.lease_until)
                    .where(Job.id == job_id)
                    .with_for_update()
                )
            ).one_or_none()
        if (
            row is None
            or row.claim_token != claim_token
            or row.status != "running"
            or row.lease_until is None
            or row.lease_until <= now
        ):
            await self.rollback()
            raise JobLeaseLost(f"Worker lease for job {job_id} is no longer current.")
        return job_id, claim_token

    async def flush(self, objects=None) -> None:
        await self._assert_job_fence()
        await super().flush(objects)

    async def commit(self) -> None:
        fence = await self._assert_job_fence()
        if fence is not None:
            job_id, claim_token = fence
            now = utcnow()
            await self.execute(
                update(Job)
                .where(Job.id == job_id, Job.claim_token == claim_token, Job.status == "running")
                .values(lease_until=now + timedelta(minutes=settings.job_lease_minutes))
            )
        await super().commit()


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=FencedAsyncSession)


async def get_db():
    async with SessionLocal() as session:
        yield session


async def create_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
