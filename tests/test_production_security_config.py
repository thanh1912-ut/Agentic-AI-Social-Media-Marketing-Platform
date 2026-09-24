"""Subprocess checks for production-only secret and docs protections."""

from __future__ import annotations

import os
import subprocess
import sys


def _production_env() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({
        "APP_ENV": "production",
        "WEB_BASE_URL": "https://marketing.example.test",
        "COOKIE_SECURE": "1",
        "JWT_SECRET": "test-only-random-secret-with-at-least-32-bytes",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "STORAGE_BACKEND": "local",
        "RATE_LIMITS_ENABLED": "1",
    })
    return environment


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


def test_production_disables_interactive_api_docs() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from services.api.main import app; assert app.openapi_url is None and app.docs_url is None and app.redoc_url is None"],
        env=_production_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
