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
    cookie_samesite: str = os.getenv("COOKIE_SAMESITE", "lax").lower()
    cors_allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    )
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
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_default_model: str = os.getenv("LLM_DEFAULT_MODEL", "gpt-4o-mini")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "")
    ai_request_timeout_seconds: int = int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "120"))
    max_job_attempts: int = int(os.getenv("MAX_JOB_ATTEMPTS", "3"))
    job_lease_minutes: int = int(os.getenv("JOB_LEASE_MINUTES", "30"))


settings = Settings()
if settings.cookie_samesite not in {"strict", "lax", "none"}:
    raise ValueError("COOKIE_SAMESITE must be strict, lax, or none")
if settings.cookie_samesite == "none" and not settings.cookie_secure:
    raise ValueError("COOKIE_SECURE=1 is required when COOKIE_SAMESITE=none")
