"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "agentic-marketing")
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./.data/agentic-marketing.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    password_reset_expire_minutes: int = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "30"))
    cookie_secure: bool = _bool("COOKIE_SECURE", False)
    cookie_domain: str | None = os.getenv("COOKIE_DOMAIN") or None
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    storage_root: Path = Path(os.getenv("STORAGE_ROOT", ".data/uploads"))
    s3_endpoint: str = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    s3_access_key: str = os.getenv("S3_ACCESS_KEY", "minioadmin")
    s3_secret_key: str = os.getenv("S3_SECRET_KEY", "minioadmin")
    s3_bucket: str = os.getenv("S3_BUCKET", "agentic-marketing")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    max_files_per_request: int = int(os.getenv("MAX_FILES_PER_REQUEST", "10"))
    parser_version: str = os.getenv("PARSER_VERSION", "m2-parser-v1")
    auto_create_schema: bool = _bool("AUTO_CREATE_SCHEMA", False)
    inline_jobs: bool = _bool("INLINE_JOBS", False)


settings = Settings()
