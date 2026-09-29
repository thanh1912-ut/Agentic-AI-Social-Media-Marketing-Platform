#!/usr/bin/env python3
"""Start and inspect the persistent, isolated local auth preview.

Secrets are read as data from owner-only files. This module never evaluates an
environment file as shell and never prints credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.engine import make_url


RUNTIME_ROOT = Path(
    os.environ.get(
        "AGENTIC_MARKETING_RUNTIME_ROOT",
        Path.home() / ".local" / "share" / "agentic-marketing",
    )
).expanduser()
SECRETS_ROOT = RUNTIME_ROOT / "secrets"
APP_ENV_FILE = SECRETS_ROOT / "app.env"
PREVIEW_ENV_FILE = SECRETS_ROOT / "auth-preview.env"
DEEPSEEK_ENV_FILE = SECRETS_ROOT / "deepseek-docling.env"
TEST_DATABASE = "agentic_marketing_auth_test_20260929"
QUEUE_DB = 4

APP_KEYS = {
    "DATABASE_URL",
    "APP_ENV",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "PASSWORD_RESET_EXPIRE_MINUTES",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_STARTTLS",
    "SMTP_SSL",
    "SMTP_TIMEOUT_SECONDS",
    "EMAIL_FROM",
    "MAX_UPLOAD_BYTES",
    "MAX_REQUEST_BODY_BYTES",
    "MAX_IMAGE_BYTES",
    "MAX_IMAGE_PIXELS",
    "MAX_FILES_PER_REQUEST",
    "MAX_NORMALIZED_DOCUMENT_CHARS",
    "MAX_DOCUMENT_TABLE_ROWS",
    "MAX_DOCUMENT_TABLE_COLUMNS",
    "MAX_DOCUMENT_TABLE_CELLS",
    "MAX_DOCUMENT_PDF_PAGES",
    "MAX_DOCUMENT_PROCESS_SECONDS",
    "PARSER_VERSION",
    "LLM_MAX_INPUT_CHARS",
    "DEEPSEEK_MAX_TOKENS",
    "AI_REQUEST_TIMEOUT_SECONDS",
    "MAX_JOB_ATTEMPTS",
    "JOB_LEASE_MINUTES",
    "EMBEDDING_PROVIDER",
    "RETRIEVAL_MODE",
    "CHUNKER_VERSION",
    "MINIMUM_RELEVANCE_SCORE",
    "MINIMUM_SEMANTIC_SCORE",
    "MINIMUM_SEMANTIC_MARGIN",
    "MINIMUM_HYBRID_LEXICAL_SCORE",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL_REVISION",
    "EMBEDDING_CACHE_DIR",
    "EMBEDDING_THREADS",
    "EMBEDDING_LOCAL_FILES_ONLY",
}
PREVIEW_KEYS = {
    "JWT_SECRET",
    "COOKIE_SECURE",
    "COOKIE_SAMESITE",
}
AI_KEYS = {
    "LLM_PROVIDER",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "LLM_DEFAULT_MODEL",
}


class PreviewConfigurationError(RuntimeError):
    """The isolated preview cannot safely construct its process environment."""


def parse_env_text(text: str) -> dict[str, str]:
    """Parse simple KEY=VALUE lines without shell expansion or execution."""

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name or not name.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def read_env_file(path: Path, *, required: bool = False) -> dict[str, str]:
    if not path.is_file():
        if required:
            raise PreviewConfigurationError(
                f"Required local settings file is missing: {path.name}"
            )
        return {}
    try:
        return parse_env_text(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PreviewConfigurationError(
            f"Cannot read local settings file: {path.name}"
        ) from error


def build_environment(
    mode: str,
    *,
    app_values: dict[str, str],
    preview_values: dict[str, str],
    ai_values: dict[str, str],
    runtime_root: Path,
) -> dict[str, str]:
    """Build the allowlisted environment for one auth-preview process."""

    if mode not in {
        "api",
        "worker",
        "worker-ingestion",
        "beat",
        "probe-model",
        "status",
        "dispatch-document",
    }:
        raise PreviewConfigurationError("Unsupported local preview process mode")

    database_url = app_values.get("DATABASE_URL", "")
    if not database_url:
        raise PreviewConfigurationError(
            "DATABASE_URL is missing from the local app settings"
        )
    try:
        parsed_database_url = make_url(database_url)
    except Exception as error:
        raise PreviewConfigurationError(
            "DATABASE_URL in the local app settings is invalid"
        ) from error

    jwt_secret = preview_values.get("JWT_SECRET", "")
    if len(jwt_secret.encode("utf-8")) < 32:
        raise PreviewConfigurationError(
            "The local auth-preview JWT secret is missing or too short"
        )

    env = {key: value for key, value in app_values.items() if key in APP_KEYS}
    env.update(
        {key: value for key, value in preview_values.items() if key in PREVIEW_KEYS}
    )
    env.update(
        {
            "APP_NAME": "agentic-marketing-auth-preview",
            "APP_ENV": "development",
            "DATABASE_URL": parsed_database_url.set(
                database=TEST_DATABASE
            ).render_as_string(hide_password=False),
            "REDIS_URL": f"redis://127.0.0.1:16379/{QUEUE_DB}",
            "REDIS_CACHE_URL": f"redis://127.0.0.1:16380/{QUEUE_DB}",
            "RATE_LIMITS_ENABLED": "0",
            "JWT_SECRET": jwt_secret,
            "COOKIE_SECURE": preview_values.get("COOKIE_SECURE", "0"),
            "COOKIE_SAMESITE": preview_values.get("COOKIE_SAMESITE", "lax"),
            "CORS_ALLOWED_ORIGINS": "http://127.0.0.1:13104",
            "ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
            "WEB_BASE_URL": "http://127.0.0.1:13104",
            "STORAGE_BACKEND": "local",
            "STORAGE_ROOT": str(runtime_root / "auth-preview" / "storage"),
            "AUTO_CREATE_SCHEMA": "0",
            "INLINE_JOBS": "0",
        }
    )

    for key in AI_KEYS:
        env.pop(key, None)
    env["LLM_PROVIDER"] = ai_values.get("LLM_PROVIDER", "deepseek")
    env["LLM_DEFAULT_MODEL"] = ai_values.get("LLM_DEFAULT_MODEL", "")
    env["DEEPSEEK_BASE_URL"] = ai_values.get(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    if mode in {"api", "worker", "probe-model", "status"}:
        env["DEEPSEEK_API_KEY"] = ai_values.get("DEEPSEEK_API_KEY", "")
    else:
        env.pop("DEEPSEEK_API_KEY", None)
    if mode == "worker-ingestion":
        env["DOCLING_ARTIFACTS_PATH"] = str(
            runtime_root / "auth-preview" / "docling-models"
        )
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["EMBEDDING_PROVIDER"] = "none"

    return env


def load_environment(mode: str, runtime_root: Path = RUNTIME_ROOT) -> dict[str, str]:
    app_values = read_env_file(APP_ENV_FILE, required=True)
    preview_values = read_env_file(PREVIEW_ENV_FILE, required=True)
    ai_values = read_env_file(DEEPSEEK_ENV_FILE)
    return build_environment(
        mode,
        app_values=app_values,
        preview_values=preview_values,
        ai_values=ai_values,
        runtime_root=runtime_root,
    )


def _provider_probe(env: dict[str, str]) -> int:
    key = env.get("DEEPSEEK_API_KEY", "")
    model = env.get("LLM_DEFAULT_MODEL", "")
    if not key:
        print("DeepSeek key: missing")
        return 2
    base_url = env["DEEPSEEK_BASE_URL"].rstrip("/")
    request = Request(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8"))
    except HTTPError as error:
        print(f"DeepSeek models endpoint: HTTP {error.code}")
        return 1
    except (
        URLError,
        TimeoutError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        print(f"DeepSeek models endpoint: unavailable ({type(error).__name__})")
        return 1

    available = {
        str(item.get("id"))
        for item in (payload.get("data") or [])
        if isinstance(item, dict) and item.get("id")
    }
    is_available = model in available
    print("DeepSeek key: present; value hidden")
    print(f"Configured model: {model or 'missing'}")
    print(f"Configured model available: {'yes' if is_available else 'no'}")
    return 0 if is_available else 1


def _status(env: dict[str, str]) -> int:
    parsed = make_url(env["DATABASE_URL"])
    print(f"preview database: {parsed.database}")
    print("queue Redis: 127.0.0.1:16379/4")
    print("cache Redis: 127.0.0.1:16380/4")
    print(
        f"DeepSeek key: {'present' if env.get('DEEPSEEK_API_KEY') else 'missing'} (value hidden)"
    )
    print(f"DeepSeek model: {env.get('LLM_DEFAULT_MODEL') or 'not configured'}")
    return 0


async def _dispatch_document(job_id: str, env: dict[str, str]) -> bool:
    os.environ.update(env)
    from sqlalchemy import select

    from database.models import Job, utcnow
    from services.api.db import SessionLocal
    from services.api.job_service import _record_dispatch, dispatch_document_job
    from services.api.config import settings

    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None or job.status != "queued" or job.kind != "document_ingest":
            raise PreviewConfigurationError(
                "The requested row is not a queued document-ingestion job"
            )
        result = job.result or {}
        document_id = str(result.get("document_id") or "")
        document_ids = [
            str(item)
            for item in result.get("document_ids")
            or ([document_id] if document_id else [])
        ]
        if not document_id or not document_ids:
            raise PreviewConfigurationError(
                "The queued document job has no safe dispatch identifiers"
            )
        job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
        await db.commit()
        sent = await dispatch_document_job(job.id, document_id, document_ids)
        await _record_dispatch(db, job.id, sent)
        return sent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "api",
            "worker",
            "worker-ingestion",
            "beat",
            "probe-model",
            "status",
            "dispatch-document",
        ),
    )
    parser.add_argument("job_id", nargs="?")
    args = parser.parse_args()
    try:
        env = load_environment(args.mode)
        if args.mode == "status":
            return _status(env)
        if args.mode == "probe-model":
            return _provider_probe(env)
        if args.mode == "dispatch-document":
            if not args.job_id:
                parser.error("dispatch-document requires a job id")
            sent = asyncio.run(_dispatch_document(args.job_id, env))
            print(f"document job dispatch: {'accepted' if sent else 'not accepted'}")
            return 0 if sent else 1

        process_env = {
            "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()),
            "LANG": "C",
            "LC_ALL": "C",
            **env,
        }
        if args.mode == "api":
            command = [
                sys.executable,
                "-m",
                "uvicorn",
                "services.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
            ]
        elif args.mode == "beat":
            schedule_path = (
                RUNTIME_ROOT / "auth-preview" / "beat" / "celerybeat-schedule"
            )
            schedule_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "services.worker.celery_app:celery_app",
                "beat",
                "--loglevel=INFO",
                f"--schedule={schedule_path}",
            ]
        else:
            queues = "ingestion" if args.mode == "worker-ingestion" else "default,agent"
            command = [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "services.worker.celery_app:celery_app",
                "worker",
                "--loglevel=INFO",
                f"--queues={queues}",
                "--concurrency=1",
                "--pool=solo",
            ]
        os.execve(sys.executable, command, process_env)
    except PreviewConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
