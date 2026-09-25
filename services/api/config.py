"""Environment-backed application settings."""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "agentic-marketing")
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./.data/agentic-marketing.db"),
        repr=False,
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"), repr=False)
    redis_cache_url: str = field(
        default_factory=lambda: os.getenv("REDIS_CACHE_URL", "redis://localhost:6380/0"), repr=False
    )
    rate_limits_enabled: bool = _bool(
        "RATE_LIMITS_ENABLED",
        os.getenv("APP_ENV", "development").strip().casefold() in {"prod", "production"},
    )
    jwt_secret: str = field(
        default_factory=lambda: os.getenv("JWT_SECRET", "change-me-in-development-only-secret"), repr=False
    )
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
    allowed_hosts: tuple[str, ...] = tuple(
        host.strip().lower()
        for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
        if host.strip()
    )
    forwarded_allow_ips: str = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1").strip()
    web_base_url: str = os.getenv("WEB_BASE_URL", "http://localhost:3000").rstrip("/")
    smtp_host: str = os.getenv("SMTP_HOST", "").strip()
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = field(default_factory=lambda: os.getenv("SMTP_USERNAME", "").strip(), repr=False)
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""), repr=False)
    smtp_starttls: bool = _bool("SMTP_STARTTLS", True)
    smtp_ssl: bool = _bool("SMTP_SSL", False)
    smtp_timeout_seconds: int = int(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
    email_from: str = os.getenv("EMAIL_FROM", "").strip()
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    storage_root: Path = Path(os.getenv("STORAGE_ROOT", ".data/uploads"))
    s3_endpoint: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT", "http://localhost:9000"), repr=False)
    s3_access_key: str = field(default_factory=lambda: os.getenv("S3_ACCESS_KEY", "minioadmin"), repr=False)
    s3_secret_key: str = field(default_factory=lambda: os.getenv("S3_SECRET_KEY", "minioadmin"), repr=False)
    s3_bucket: str = os.getenv("S3_BUCKET", "agentic-marketing")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    max_request_body_bytes: int = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(256 * 1024 * 1024)))
    max_image_bytes: int = int(os.getenv("MAX_IMAGE_BYTES", str(12 * 1024 * 1024)))
    max_image_pixels: int = int(os.getenv("MAX_IMAGE_PIXELS", "40000000"))
    max_files_per_request: int = int(os.getenv("MAX_FILES_PER_REQUEST", "10"))
    parser_version: str = os.getenv("PARSER_VERSION", "m2-parser-v2")
    auto_create_schema: bool = _bool("AUTO_CREATE_SCHEMA", False)
    inline_jobs: bool = _bool("INLINE_JOBS", False)
    llm_provider: str = os.getenv("LLM_PROVIDER", "deepseek").strip().casefold()
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""), repr=False)
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    llm_default_model: str = os.getenv("LLM_DEFAULT_MODEL", "deepseek-flash").strip()
    llm_max_tokens: int = int(os.getenv("DEEPSEEK_MAX_TOKENS", "8192"))
    llm_max_input_chars: int = int(os.getenv("LLM_MAX_INPUT_CHARS", "24000"))
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "none").strip().casefold()
    embedding_data_flow_approved: bool = _bool("EMBEDDING_DATA_FLOW_APPROVED", False)
    embedding_api_key: str = field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY", ""), repr=False)
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "").strip()
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    embedding_model_revision: str = os.getenv(
        "EMBEDDING_MODEL_REVISION", "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    ).strip()
    embedding_cache_dir: Path = Path(os.getenv("EMBEDDING_CACHE_DIR", ".data/embedding-models"))
    embedding_threads: int = int(os.getenv("EMBEDDING_THREADS", "2"))
    embedding_local_files_only: bool = _bool("EMBEDDING_LOCAL_FILES_ONLY", False)
    retrieval_mode: str = os.getenv("RETRIEVAL_MODE", "lexical").strip().casefold()
    chunker_version: str = os.getenv("CHUNKER_VERSION", "vi-token-window-v3-300").strip()
    minimum_relevance_score: float = float(os.getenv("MINIMUM_RELEVANCE_SCORE", "0.12"))
    minimum_semantic_score: float = float(os.getenv("MINIMUM_SEMANTIC_SCORE", "0.82"))
    minimum_semantic_margin: float = float(os.getenv("MINIMUM_SEMANTIC_MARGIN", "0.04"))
    minimum_hybrid_lexical_score: float = float(os.getenv("MINIMUM_HYBRID_LEXICAL_SCORE", "0.45"))
    ai_request_timeout_seconds: int = int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "120"))
    max_job_attempts: int = int(os.getenv("MAX_JOB_ATTEMPTS", "3"))
    job_lease_minutes: int = int(os.getenv("JOB_LEASE_MINUTES", "30"))
    meta_workspace_id: str = os.getenv("META_WORKSPACE_ID", "").strip()
    meta_page_id: str = os.getenv("META_PAGE_ID", "").strip()
    meta_page_access_token: str = field(default_factory=lambda: os.getenv("META_PAGE_ACCESS_TOKEN", "").strip(), repr=False)
    # App/user token for approved Page Public Content Access, used only for public competitor Pages.
    meta_public_content_access_token: str = field(
        default_factory=lambda: os.getenv("META_PUBLIC_CONTENT_ACCESS_TOKEN", "").strip(), repr=False
    )
    meta_graph_version: str = os.getenv("META_GRAPH_VERSION", "v26.0").strip()
    meta_token_encryption_key: str = field(default_factory=lambda: os.getenv("META_TOKEN_ENCRYPTION_KEY", "").strip(), repr=False)
    meta_token_encryption_key_previous: str = field(default_factory=lambda: os.getenv("META_TOKEN_ENCRYPTION_KEY_PREVIOUS", "").strip(), repr=False)

    @property
    def meta_configured(self) -> bool:
        return bool(self.meta_workspace_id and self.meta_page_id and self.meta_page_access_token)

    @property
    def email_delivery_configured(self) -> bool:
        return bool(self.smtp_host and self.email_from)


settings = Settings()
if any((settings.meta_workspace_id, settings.meta_page_id, settings.meta_page_access_token)) and not settings.meta_configured:
    raise ValueError("META_WORKSPACE_ID, META_PAGE_ID and META_PAGE_ACCESS_TOKEN must be configured together")
if not re.fullmatch(r"v[1-9][0-9]{0,2}\.0", settings.meta_graph_version):
    raise ValueError("META_GRAPH_VERSION must look like v26.0")
if settings.meta_page_id and not re.fullmatch(r"[0-9]{1,32}", settings.meta_page_id):
    raise ValueError("META_PAGE_ID must be a numeric Facebook Page ID")
if settings.cookie_samesite not in {"strict", "lax", "none"}:
    raise ValueError("COOKIE_SAMESITE must be strict, lax, or none")
if settings.cookie_samesite == "none" and not settings.cookie_secure:
    raise ValueError("COOKIE_SECURE=1 is required when COOKIE_SAMESITE=none")
web_url = urlsplit(settings.web_base_url)
if (
    web_url.scheme not in {"http", "https"}
    or not web_url.netloc
    or web_url.path not in {"", "/"}
    or web_url.username
    or web_url.password
    or web_url.query
    or web_url.fragment
):
    raise ValueError("WEB_BASE_URL must be an HTTP(S) origin without credentials, query, or fragment")
if settings.app_env.casefold() in {"prod", "production"} and web_url.scheme != "https":
    raise ValueError("Production WEB_BASE_URL must use HTTPS")
if not 1 <= settings.smtp_port <= 65535 or settings.smtp_timeout_seconds < 1:
    raise ValueError("SMTP port and timeout must be valid positive values")
if bool(settings.smtp_username) != bool(settings.smtp_password):
    raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
if settings.smtp_starttls and settings.smtp_ssl:
    raise ValueError("Configure only one of SMTP_STARTTLS or SMTP_SSL")
if settings.smtp_host and not settings.email_from:
    raise ValueError("EMAIL_FROM is required when SMTP_HOST is configured")
if settings.app_env.casefold() in {"prod", "production"}:
    # Fail before serving traffic when production could fall back to local/dev defaults.
    if settings.jwt_secret == "change-me-in-development-only-secret" or len(settings.jwt_secret.encode("utf-8")) < 32:
        raise ValueError("Production requires a random JWT_SECRET with at least 32 bytes")
    if not settings.cookie_secure:
        raise ValueError("Production cookie authentication requires COOKIE_SECURE=1")
    if not settings.rate_limits_enabled:
        raise ValueError("Production requires RATE_LIMITS_ENABLED=1")
    if not os.getenv("ALLOWED_HOSTS", "").strip() or not settings.allowed_hosts or "*" in settings.allowed_hosts:
        raise ValueError("Production requires an explicit ALLOWED_HOSTS list without '*'")
    if not settings.database_url.casefold().startswith("postgresql"):
        raise ValueError("Production requires a PostgreSQL DATABASE_URL")
    if not os.getenv("CORS_ALLOWED_ORIGINS", "").strip() or not settings.cors_allowed_origins:
        raise ValueError("Production requires an explicit CORS_ALLOWED_ORIGINS list")
    for origin in settings.cors_allowed_origins:
        try:
            parsed_origin = urlsplit(origin)
            _port = parsed_origin.port
        except ValueError as exc:
            raise ValueError("Production CORS origins must be valid HTTPS origins") from exc
        if (
            origin == "*"
            or parsed_origin.scheme != "https"
            or not parsed_origin.netloc
            or parsed_origin.username
            or parsed_origin.password
            or parsed_origin.path
            or parsed_origin.query
            or parsed_origin.fragment
            or "*" in parsed_origin.netloc
        ):
            raise ValueError(
                "Production CORS origins must be HTTPS origins without paths, credentials, query, fragments, or wildcards"
            )
    if settings.storage_backend.casefold() == "s3" and (
        settings.s3_access_key == "minioadmin" or settings.s3_secret_key == "minioadmin"
    ):
        raise ValueError("Production S3 storage requires non-default S3_ACCESS_KEY and S3_SECRET_KEY")
if any(
    "*" in host and host != "*" and (not host.startswith("*.") or host.count("*") != 1)
    for host in settings.allowed_hosts
):
    raise ValueError("ALLOWED_HOSTS wildcards must use the '*.example.com' form")
if "*" in settings.forwarded_allow_ips.split(","):
    raise ValueError("FORWARDED_ALLOW_IPS must list trusted proxy IPs or CIDRs; '*' is not allowed")
if not settings.forwarded_allow_ips:
    raise ValueError("FORWARDED_ALLOW_IPS must list trusted proxy IPs or CIDRs")
for proxy_ip in settings.forwarded_allow_ips.split(","):
    try:
        ipaddress.ip_network(proxy_ip.strip(), strict=False)
    except ValueError as exc:
        raise ValueError("FORWARDED_ALLOW_IPS entries must be IP addresses or CIDRs") from exc
if settings.llm_provider != "deepseek":
    raise ValueError("LLM_PROVIDER must be deepseek; no implicit provider fallback is supported")
if settings.embedding_provider not in {"none", "openai", "fastembed"}:
    raise ValueError("EMBEDDING_PROVIDER must be none, openai, or fastembed")
if settings.retrieval_mode not in {"lexical", "semantic_vector"}:
    raise ValueError("RETRIEVAL_MODE must be lexical or semantic_vector")
if settings.embedding_provider == "none" and settings.retrieval_mode != "lexical":
    raise ValueError("RETRIEVAL_MODE=semantic_vector requires an embedding provider")
if settings.embedding_provider != "none" and settings.retrieval_mode != "semantic_vector":
    raise ValueError("A configured embedding provider requires RETRIEVAL_MODE=semantic_vector")
if settings.embedding_provider == "openai" and not settings.embedding_data_flow_approved:
    raise ValueError(
        "External embeddings send workspace document text to another provider; set EMBEDDING_DATA_FLOW_APPROVED=1 only after separate approval"
    )
if not 1 <= settings.embedding_dimensions <= 2000:
    raise ValueError("EMBEDDING_DIMENSIONS must be between 1 and 2000")
if settings.max_image_bytes < 1 or settings.max_image_pixels < 1:
    raise ValueError("Image upload byte and pixel limits must be positive")
if settings.max_request_body_bytes < settings.max_upload_bytes + 1024 * 1024:
    raise ValueError("MAX_REQUEST_BODY_BYTES must exceed MAX_UPLOAD_BYTES by at least 1 MiB for multipart overhead")
if (
    not 0 <= settings.minimum_relevance_score <= 1
    or not 0 <= settings.minimum_semantic_score <= 1
    or not 0 <= settings.minimum_semantic_margin <= 1
    or not 0 <= settings.minimum_hybrid_lexical_score <= 1
):
    raise ValueError("Relevance thresholds must be between 0 and 1")
if settings.llm_max_tokens < 1 or settings.llm_max_input_chars < 1 or settings.ai_request_timeout_seconds < 1:
    raise ValueError("LLM token, input, and request-timeout limits must be positive")
if not settings.llm_default_model:
    raise ValueError("LLM_DEFAULT_MODEL must name a DeepSeek model")
deepseek_url = urlsplit(settings.deepseek_base_url)
if (
    deepseek_url.scheme not in {"http", "https"}
    or not deepseek_url.hostname
    or deepseek_url.username
    or deepseek_url.password
    or deepseek_url.query
    or deepseek_url.fragment
):
    raise ValueError("DEEPSEEK_BASE_URL must be an HTTP(S) URL")
if settings.app_env.casefold() in {"prod", "production"} and deepseek_url.scheme != "https":
    raise ValueError("Production DEEPSEEK_BASE_URL must use HTTPS")
if settings.embedding_provider == "openai":
    if not settings.embedding_api_key:
        raise ValueError("EMBEDDING_API_KEY is required when EMBEDDING_PROVIDER=openai")
    if not settings.embedding_model:
        raise ValueError("EMBEDDING_MODEL is required when EMBEDDING_PROVIDER=openai")
if settings.embedding_provider == "fastembed":
    if settings.embedding_model != "intfloat/multilingual-e5-small":
        raise ValueError("EMBEDDING_MODEL must be intfloat/multilingual-e5-small for fastembed")
    if settings.embedding_model_revision != "614241f622f53c4eeff9890bdc4f31cfecc418b3":
        raise ValueError("EMBEDDING_MODEL_REVISION must match the reviewed multilingual E5 weights")
    if settings.embedding_dimensions != 384:
        raise ValueError("EMBEDDING_DIMENSIONS must be 384 for intfloat/multilingual-e5-small")
    if settings.embedding_threads < 1:
        raise ValueError("EMBEDDING_THREADS must be positive")
