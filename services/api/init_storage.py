"""Initialize the configured object-storage bucket before API/worker startup."""

from __future__ import annotations

import asyncio

from .storage import S3ObjectStorage, storage


async def main() -> None:
    if not isinstance(storage, S3ObjectStorage):
        return
    last_error: Exception | None = None
    for attempt in range(30):
        try:
            await asyncio.to_thread(storage.ensure_bucket)
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(min(2 + attempt, 5))
    raise RuntimeError("Object storage bucket initialization failed") from last_error


if __name__ == "__main__":
    asyncio.run(main())
