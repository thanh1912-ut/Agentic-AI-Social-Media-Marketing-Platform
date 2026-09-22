"""Convenience entry point for local worker checks."""

from .celery_app import celery_app

__all__ = ["celery_app"]

