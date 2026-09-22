"""Storage abstraction: local MinIO-compatible development fallback."""

from __future__ import annotations

import asyncio
from pathlib import Path

from .config import settings


class LocalObjectStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, content: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    def path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root.resolve() not in candidate.parents:
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
        try:
            self.client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            self.client.create_bucket(Bucket=settings.s3_bucket)

    async def put(self, key: str, content: bytes) -> None:
        await asyncio.to_thread(self.client.put_object, Bucket=settings.s3_bucket, Key=key, Body=content)

    async def read(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=settings.s3_bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)


storage = S3ObjectStorage() if settings.storage_backend == "s3" else LocalObjectStorage(settings.storage_root)
