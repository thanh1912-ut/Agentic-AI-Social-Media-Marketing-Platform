"""Storage abstraction: local MinIO-compatible development fallback."""

from __future__ import annotations

import asyncio
from pathlib import Path
from pathlib import PureWindowsPath

from .config import settings


def _storage_key_parts(key: str) -> tuple[str, ...]:
    if not isinstance(key, str) or not key or "\x00" in key or "\\" in key:
        raise ValueError("invalid storage key")
    windows_path = PureWindowsPath(key)
    if windows_path.is_absolute() or windows_path.drive:
        raise ValueError("invalid storage key")
    parts = tuple(key.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("invalid storage key")
    return parts


class LocalObjectStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, content: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self.path(key).read_bytes)

    def path(self, key: str) -> Path:
        parts = _storage_key_parts(key)
        root = self.root.resolve()
        candidate = root.joinpath(*parts).resolve()
        if root not in candidate.parents:
            raise ValueError("invalid storage key")
        return candidate


class S3ObjectStorage:
    def __init__(self):
        import boto3

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=settings.s3_bucket)
        except Exception as exc:
            response = getattr(exc, "response", {})
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = response.get("Error", {}).get("Code")
            if status not in {404, 301} and code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self.client.create_bucket(Bucket=settings.s3_bucket)

    def is_ready(self) -> bool:
        try:
            self.client.head_bucket(Bucket=settings.s3_bucket)
            return True
        except Exception:
            return False

    async def put(self, key: str, content: bytes) -> None:
        _storage_key_parts(key)
        await asyncio.to_thread(self.client.put_object, Bucket=settings.s3_bucket, Key=key, Body=content)

    async def read(self, key: str) -> bytes:
        _storage_key_parts(key)
        response = await asyncio.to_thread(self.client.get_object, Bucket=settings.s3_bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)


storage = S3ObjectStorage() if settings.storage_backend == "s3" else LocalObjectStorage(settings.storage_root)


async def storage_ready() -> bool:
    if isinstance(storage, S3ObjectStorage):
        return await asyncio.to_thread(storage.is_ready)
    return True
