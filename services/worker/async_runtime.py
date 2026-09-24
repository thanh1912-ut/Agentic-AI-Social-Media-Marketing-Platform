"""Async runtime shared by synchronous Celery task entrypoints."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from typing import Any, TypeVar


ResultT = TypeVar("ResultT")
_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_pid: int | None = None


def run_worker_coroutine(coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Run a task on the process's persistent loop.

    SQLAlchemy's asyncpg pool binds connections to the loop that created them.
    Reusing one loop across Celery tasks prevents a later ``asyncio.run`` from
    reusing a connection attached to a closed loop. Celery's prefork and solo
    pools execute synchronous task bodies serially within each process.
    """

    global _worker_loop, _worker_pid
    current_pid = os.getpid()
    if _worker_loop is None or _worker_loop.is_closed() or _worker_pid != current_pid:
        _worker_loop = asyncio.new_event_loop()
        _worker_pid = current_pid
    if _worker_loop.is_running():
        coroutine.close()
        raise RuntimeError("Celery worker async tasks must run serially in a sync task process")
    return _worker_loop.run_until_complete(coroutine)
