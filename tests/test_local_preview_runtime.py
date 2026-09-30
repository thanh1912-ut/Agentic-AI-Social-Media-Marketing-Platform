from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from scripts.local_preview_runtime import (
    PreviewConfigurationError,
    build_environment,
    load_environment,
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


def test_gemini_settings_reload_without_overriding_auth_or_saved_deepseek_key(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "app.env").write_text("DATABASE_URL=postgresql://runtime:opaque@127.0.0.1/fresh\n")
    (secrets / "auth-preview.env").write_text(f"JWT_SECRET={'p' * 40}\n")
    (secrets / "deepseek-docling.env").write_text(
        "DEEPSEEK_API_KEY=fake-deepseek\nLLM_DEFAULT_MODEL=explicit-deepseek-model\n"
    )
    research_file = secrets / "research-ai.env"
    research_file.write_text(
        "LLM_PROVIDER=gemini\nLLM_DEFAULT_MODEL=gemini-3.8-flash\n"
        "GEMINI_API_KEY=fake-gemini\nGEMINI_MODEL=gemini-3.8-flash\n"
        "QWEN_API_KEY=fake-qwen\nQWEN_MODEL=explicit-qwen-model\nQWEN_REGION=singapore\n"
        "QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1\n"
        "DEEPSEEK_API_KEY=must-not-override\nJWT_SECRET=must-not-override\n"
        "DATABASE_URL=must-not-override\n"
    )
    research_file.chmod(0o600)
    for mode in ("api", "worker", "status", "probe-model"):
        env = load_environment(mode, runtime_root=tmp_path)
        assert env["GEMINI_API_KEY"] == "fake-gemini"
        assert "QWEN_API_KEY" not in env and "QWEN_REGION" not in env
        assert "DEEPSEEK_API_KEY" not in env
        assert env["LLM_PROVIDER"] == "gemini"
        assert env["LLM_DEFAULT_MODEL"] == "gemini-3.8-flash"
        assert env["JWT_SECRET"] == "p" * 40
        assert make_url(env["DATABASE_URL"]).database == "agentic_marketing_auth_test_20260929"
    for mode in ("worker-ingestion", "beat", "dispatch-document"):
        env = load_environment(mode, runtime_root=tmp_path)
        assert "GEMINI_API_KEY" not in env
        assert "QWEN_API_KEY" not in env
    research_file.write_text("LLM_PROVIDER=gemini\nLLM_DEFAULT_MODEL=gemini-3.8-flash\nGEMINI_MODEL=gemini-3.8-flash\n")
    reloaded = load_environment("worker", runtime_root=tmp_path)
    assert reloaded["GEMINI_MODEL"] == "gemini-3.8-flash"
    assert "GEMINI_API_KEY" not in reloaded  # No inherited stale key.
    research_file.write_text("")
    rollback = load_environment("worker", runtime_root=tmp_path)
    assert rollback["DEEPSEEK_API_KEY"] == "fake-deepseek"
    assert rollback["LLM_DEFAULT_MODEL"] == "explicit-deepseek-model"


def test_research_provider_secret_file_requires_owner_only_permissions(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "app.env").write_text("DATABASE_URL=postgresql://runtime:opaque@127.0.0.1/fresh\n")
    (secrets / "auth-preview.env").write_text(f"JWT_SECRET={'p' * 40}\n")
    path = secrets / "research-ai.env"
    path.write_text("QWEN_API_KEY=fake-qwen\n")
    path.chmod(0o644)
    with pytest.raises(PreviewConfigurationError, match="0600"):
        load_environment("worker", runtime_root=tmp_path)


def test_page_settings_reload_and_do_not_reach_ingestion_or_scheduler(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "app.env").write_text("DATABASE_URL=postgresql://runtime:opaque@127.0.0.1/fresh\n")
    (secrets / "auth-preview.env").write_text(f"JWT_SECRET={'p' * 40}\n")
    path = secrets / "page-connection.env"
    path.write_text("META_TOKEN_ENCRYPTION_KEY=synthetic-stable-encryption-key\n"
                    "META_GRAPH_VERSION=v26.0\nMETA_PAGE_ACCESS_TOKEN=must-not-inherit\n")
    path.chmod(0o600)
    for mode in ("api", "worker", "status"):
        env = load_environment(mode, runtime_root=tmp_path)
        assert env["META_TOKEN_ENCRYPTION_KEY"] == "synthetic-stable-encryption-key"
        assert env["META_GRAPH_VERSION"] == "v26.0"
        assert "META_PAGE_ACCESS_TOKEN" not in env
    for mode in ("worker-ingestion", "beat", "dispatch-document", "probe-model"):
        assert "META_TOKEN_ENCRYPTION_KEY" not in load_environment(mode, runtime_root=tmp_path)
    path.chmod(0o644)
    with pytest.raises(PreviewConfigurationError, match="0600"):
        load_environment("api", runtime_root=tmp_path)


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
