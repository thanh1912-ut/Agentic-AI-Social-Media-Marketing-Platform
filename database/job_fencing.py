"""Context-local ownership token used to fence commits from stale workers."""

from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar


JobFence = tuple[str, str]
_current_job_fence: ContextVar[JobFence | None] = ContextVar("current_job_fence", default=None)
F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


class JobLeaseLost(RuntimeError):
    """Raised when the worker no longer owns the job it is trying to commit."""


def active_job_fence() -> JobFence | None:
    return _current_job_fence.get()


def claim_job_fence(job_id: str, claim_token: str) -> None:
    _current_job_fence.set((job_id, claim_token))


def isolated_job_fence(function: F) -> F:
    """Clear inherited task state before work and restore it when the task ends."""

    @wraps(function)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        context_token = _current_job_fence.set(None)
        try:
            return await function(*args, **kwargs)
        finally:
            _current_job_fence.reset(context_token)

    return wrapped  # type: ignore[return-value]
