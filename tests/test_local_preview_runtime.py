from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from scripts.local_preview_runtime import (
    PreviewConfigurationError,
    build_environment,
    parse_env_text,
)


def test_env_parser_keeps_equals_and_does_not_execute_shell_syntax(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "must-not-exist"
    values = parse_env_text(
        f"# comment\nexport VALUE='left=right'\nAPI_KEY=$(touch {marker})\n"
    )

    assert values == {"VALUE": "left=right", "API_KEY": f"$(touch {marker})"}
    assert not marker.exists()


def test_api_and_agent_worker_load_saved_key_and_isolated_endpoints(
    tmp_path: Path,
) -> None:
    shared = {
        "DATABASE_URL": "postgresql+asyncpg://runtime:opaque@127.0.0.1:15432/agentic_marketing_fresh",
        "DEEPSEEK_API_KEY": "",  # A stale empty value must not mask the secret file.
    }
    preview = {"JWT_SECRET": "p" * 40, "COOKIE_SECURE": "0", "COOKIE_SAMESITE": "lax"}
    ai = {
        "LLM_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "fake-test-key-never-sent",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "LLM_DEFAULT_MODEL": "deepseek-flash",
    }

    for mode in ("api", "worker"):
        env = build_environment(
            mode,
            app_values=shared,
            preview_values=preview,
            ai_values=ai,
            runtime_root=tmp_path,
        )
        assert env["DEEPSEEK_API_KEY"] == "fake-test-key-never-sent"
        assert env["LLM_DEFAULT_MODEL"] == "deepseek-flash"
        assert env["REDIS_URL"].endswith("/4")
        assert env["REDIS_CACHE_URL"].endswith("/4")
        assert (
            make_url(env["DATABASE_URL"]).database
            == "agentic_marketing_auth_test_20260929"
        )
        assert env["STORAGE_ROOT"] == str(tmp_path / "auth-preview" / "storage")


def test_ingestion_worker_uses_local_models_without_provider_key(
    tmp_path: Path,
) -> None:
    env = build_environment(
        "worker-ingestion",
        app_values={
            "DATABASE_URL": "postgresql+asyncpg://runtime:opaque@127.0.0.1:15432/fresh"
        },
        preview_values={"JWT_SECRET": "p" * 40},
        ai_values={
            "DEEPSEEK_API_KEY": "fake-test-key-never-sent",
            "LLM_DEFAULT_MODEL": "deepseek-flash",
        },
        runtime_root=tmp_path,
    )

    assert "DEEPSEEK_API_KEY" not in env
    assert env["DOCLING_ARTIFACTS_PATH"] == str(
        tmp_path / "auth-preview" / "docling-models"
    )
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == "1"
    assert env["EMBEDDING_PROVIDER"] == "none"


def test_one_time_job_dispatch_does_not_inherit_provider_key(tmp_path: Path) -> None:
    env = build_environment(
        "dispatch-document",
        app_values={
            "DATABASE_URL": "postgresql+asyncpg://runtime:opaque@127.0.0.1:15432/fresh"
        },
        preview_values={"JWT_SECRET": "p" * 40},
        ai_values={"DEEPSEEK_API_KEY": "fake-test-key-never-sent"},
        runtime_root=tmp_path,
    )

    assert "DEEPSEEK_API_KEY" not in env


def test_recovery_scheduler_does_not_receive_provider_key(tmp_path: Path) -> None:
    env = build_environment(
        "beat",
        app_values={
            "DATABASE_URL": "postgresql+asyncpg://runtime:opaque@127.0.0.1/fresh"
        },
        preview_values={"JWT_SECRET": "p" * 40},
        ai_values={"DEEPSEEK_API_KEY": "fake-test-key-never-sent"},
        runtime_root=tmp_path,
    )

    assert "DEEPSEEK_API_KEY" not in env


def test_runtime_requires_a_database_and_existing_session_secret(
    tmp_path: Path,
) -> None:
    with pytest.raises(PreviewConfigurationError, match="DATABASE_URL"):
        build_environment(
            "api",
            app_values={},
            preview_values={"JWT_SECRET": "p" * 40},
            ai_values={},
            runtime_root=tmp_path,
        )

    with pytest.raises(PreviewConfigurationError, match="JWT secret"):
        build_environment(
            "api",
            app_values={"DATABASE_URL": "postgresql://runtime:opaque@127.0.0.1/fresh"},
            preview_values={},
            ai_values={},
            runtime_root=tmp_path,
        )
