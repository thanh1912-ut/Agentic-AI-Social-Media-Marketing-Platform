"""Subprocess checks for production-only secret and docs protections."""

from __future__ import annotations

import os
import subprocess
import sys

from services.api.config import Settings


def _production_env() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({
        "APP_ENV": "production",
        "WEB_BASE_URL": "https://marketing.example.test",
        "CORS_ALLOWED_ORIGINS": "https://marketing.example.test",
        "COOKIE_SECURE": "1",
        "JWT_SECRET": "test-only-random-secret-with-at-least-32-bytes",
        "DATABASE_URL": "postgresql+asyncpg://agentic:test-only-long-password@db.example.test/agentic_marketing",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "STORAGE_BACKEND": "local",
        "RATE_LIMITS_ENABLED": "1",
        "ALLOWED_HOSTS": "marketing.example.test",
    })
    return environment


def test_settings_repr_does_not_expose_credentials() -> None:
    sentinels = {
        "database_url": "postgresql+asyncpg://user:db-secret@db.example.test/app",
        "redis_url": "redis://:redis-secret@cache.example.test/0",
        "jwt_secret": "jwt-secret-sentinel",
        "smtp_username": "smtp-user-sentinel",
        "s3_endpoint": "https://user:s3-secret@storage.example.test",
        "s3_access_key": "s3-access-sentinel",
        "s3_secret_key": "s3-secret-sentinel",
        "deepseek_api_key": "deepseek-secret-sentinel",
        "embedding_api_key": "embedding-secret-sentinel",
        "meta_page_access_token": "meta-page-token-sentinel",
        "meta_public_content_access_token": "meta-public-token-sentinel",
        "meta_token_encryption_key": "meta-key-sentinel",
    }
    rendered = repr(Settings(**sentinels))
    assert all(secret not in rendered for secret in sentinels.values())


def test_production_rejects_a_short_jwt_secret() -> None:
    environment = _production_env()
    environment["JWT_SECRET"] = "too-short"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Production requires a random JWT_SECRET" in result.stderr


def test_production_rejects_disabled_rate_limits() -> None:
    environment = _production_env()
    environment["RATE_LIMITS_ENABLED"] = "0"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Production requires RATE_LIMITS_ENABLED=1" in result.stderr


def test_production_requires_explicit_host_allowlist() -> None:
    environment = _production_env()
    environment.pop("ALLOWED_HOSTS")
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Production requires an explicit ALLOWED_HOSTS list" in result.stderr


def test_production_requires_postgresql() -> None:
    environment = _production_env()
    environment["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Production requires a PostgreSQL DATABASE_URL" in result.stderr


def test_production_requires_explicit_https_cors_origins() -> None:
    environment = _production_env()
    environment["CORS_ALLOWED_ORIGINS"] = "*"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Production CORS origins must be HTTPS origins" in result.stderr


def test_production_s3_storage_rejects_default_credentials() -> None:
    environment = _production_env()
    environment["STORAGE_BACKEND"] = "s3"
    environment["S3_ACCESS_KEY"] = "minioadmin"
    environment["S3_SECRET_KEY"] = "minioadmin"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Production S3 storage requires non-default" in result.stderr


def test_production_rejects_wildcard_host_allowlist() -> None:
    environment = _production_env()
    environment["ALLOWED_HOSTS"] = "*"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Production requires an explicit ALLOWED_HOSTS list" in result.stderr


def test_host_allowlist_rejects_multiple_wildcards() -> None:
    environment = _production_env()
    environment["ALLOWED_HOSTS"] = "*.*.example.test"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ALLOWED_HOSTS wildcards must use the '*.example.com' form" in result.stderr


def test_production_requires_https_for_deepseek() -> None:
    environment = _production_env()
    environment["DEEPSEEK_BASE_URL"] = "http://api.deepseek.com"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Production DEEPSEEK_BASE_URL must use HTTPS" in result.stderr


def test_forwarded_ips_reject_unknown_or_unbounded_proxies() -> None:
    environment = _production_env()
    environment["FORWARDED_ALLOW_IPS"] = "*"
    result = subprocess.run(
        [sys.executable, "-c", "import services.api.config"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "FORWARDED_ALLOW_IPS must list trusted proxy IPs or CIDRs" in result.stderr


def test_api_entrypoint_passes_only_configured_proxy_ips_to_uvicorn() -> None:
    environment = _production_env()
    environment["FORWARDED_ALLOW_IPS"] = "10.0.0.0/24,127.0.0.1"
    script = (
        "from unittest.mock import patch; import runpy; "
        "context=patch('uvicorn.run'); run=context.start(); "
        "runpy.run_module('services.api', run_name='__main__'); "
        "assert run.call_args.kwargs['proxy_headers'] is True; "
        "assert run.call_args.kwargs['forwarded_allow_ips'] == '10.0.0.0/24,127.0.0.1'; "
        "context.stop()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_production_disables_interactive_api_docs() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from services.api.main import app; assert app.openapi_url is None and app.docs_url is None and app.redoc_url is None"],
        env=_production_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_production_rejects_untrusted_host_header() -> None:
    script = (
        "from fastapi.testclient import TestClient; "
        "from services.api.main import app; "
        "response=TestClient(app).get('/healthz', headers={'host':'attacker.example'}); "
        "assert response.status_code == 400"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=_production_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_application_returns_error_envelope_for_oversized_request_body() -> None:
    environment = _production_env()
    environment["MAX_UPLOAD_BYTES"] = "8"
    environment["MAX_REQUEST_BODY_BYTES"] = str(8 + 1024 * 1024)
    script = (
        "from fastapi.testclient import TestClient; "
        "from services.api.main import app; "
        "body=b'x'*(8+1024*1024+1); "
        "response=TestClient(app).post('/healthz', content=body, headers={'host':'marketing.example.test'}); "
        "assert response.status_code == 413; "
        "assert response.json()['error']['code'] == 'request_too_large'; "
        "assert response.headers['x-request-id'] == response.json()['error']['request_id']"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
