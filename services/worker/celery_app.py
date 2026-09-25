"""Celery entry point. PostgreSQL remains the authoritative job ledger."""

from celery import Celery

from services.api.config import settings


celery_app = Celery(
    "agentic_marketing",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["services.worker.tasks", "services.worker.content_tasks", "services.worker.meta_tasks", "services.worker.research_tasks", "services.worker.scheduled_jobs"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "services.worker.scheduled_jobs.recover_due_jobs": {"queue": "default"},
    },
    task_track_started=True,
    result_expires=3600,
    beat_schedule={
        "recover-due-jobs-every-minute": {
            "task": "services.worker.scheduled_jobs.recover_due_jobs",
            "schedule": 60.0,
            "options": {"queue": "default"},
        },
    },
)
