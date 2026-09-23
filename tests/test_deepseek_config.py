"""M2 provider selection tests; credentials are synthetic and never logged."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Literal

import pytest
from pydantic import BaseModel

from services.api.config import Settings
from services.worker import model_provider


def test_settings_default_to_deepseek_and_explicit_lexical_mode(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "deepseek-flash")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "none")
    monkeypatch.setenv("EMBEDDING_DATA_FLOW_APPROVED", "0")
    monkeypatch.setenv("RETRIEVAL_MODE", "lexical")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = Settings()

    assert config.llm_provider == "deepseek"
    assert config.llm_default_model == "deepseek-flash"
    assert config.embedding_provider == "none"
    assert config.retrieval_mode == "lexical"
    assert config.embedding_data_flow_approved is False
    assert "DEEPSEEK_API_KEY" not in repr(config)
    assert "OPENAI_API_KEY" not in repr(config)


def test_only_deepseek_configuration_constructs_m3_adapter(monkeypatch):
    class FakeDeepSeekAdapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module = ModuleType("services.agents.providers.deepseek")
    module.DeepSeekStructuredModel = FakeDeepSeekAdapter
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(
        model_provider,
        "settings",
        SimpleNamespace(
            llm_provider="deepseek",
            deepseek_api_key="test-secret-not-for-output",
            deepseek_base_url="https://api.deepseek.com",
            llm_default_model="deepseek-flash",
            ai_request_timeout_seconds=17,
            llm_max_tokens=321,
            llm_max_input_chars=6543,
        ),
    )

    adapter = model_provider.configured_structured_model()

    assert adapter.kwargs == {
        "api_key": "test-secret-not-for-output",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "timeout_seconds": 17,
        "max_tokens": 321,
        "max_input_chars": 6543,
    }


def test_missing_deepseek_key_has_provider_specific_configuration_error(monkeypatch):
    monkeypatch.setattr(
        model_provider,
        "settings",
        SimpleNamespace(llm_provider="deepseek", deepseek_api_key="", llm_default_model="deepseek-flash"),
    )

    with pytest.raises(model_provider.AIConfigurationError, match="DEEPSEEK_API_KEY"):
        model_provider.configured_structured_model()


def test_external_embedding_provider_requires_separate_data_flow_approval(monkeypatch):
    monkeypatch.setattr(
        model_provider,
        "settings",
        SimpleNamespace(embedding_provider="openai", embedding_data_flow_approved=False),
    )
    with pytest.raises(model_provider.AIConfigurationError, match="data flow is not approved"):
        model_provider.configured_embedding_provider()


class _SmokeResponse(BaseModel):
    ok: bool
    provider: Literal["deepseek"]


class _HttpError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__("raw provider response contains synthetic-secret")


@pytest.mark.parametrize(
    ("failure", "expected_type", "retryable"),
    [
        (_HttpError(401), "ProviderAuthenticationError", False),
        (_HttpError(403), "ProviderAuthenticationError", False),
        (_HttpError(404), "ProviderModelNotFoundError", False),
        (_HttpError(429), "ProviderRateLimitError", True),
        (_HttpError(503), "ProviderRequestError", True),
        (TimeoutError("synthetic-secret"), "ProviderTimeoutError", True),
    ],
)
def test_deepseek_adapter_maps_provider_errors_without_raw_details(
    monkeypatch, failure, expected_type, retryable
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fail_request(**_kwargs):
        raise failure

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fail_request))
    )
    from services.agents.providers.deepseek import DeepSeekStructuredModel

    adapter = DeepSeekStructuredModel(
        api_key="deepseek-test-secret",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        client=client,
    )

    with pytest.raises(RuntimeError) as raised:
        adapter.generate(
            system_prompt="Return JSON.",
            input_payload={"ok": True, "provider": "deepseek"},
            response_model=_SmokeResponse,
        )

    assert type(raised.value).__name__ == expected_type
    assert raised.value.retryable is retryable
    assert "synthetic-secret" not in str(raised.value)


@pytest.mark.parametrize(
    ("provider_error", "expected_code", "retryable"),
    [
        ("ProviderAuthenticationError", "provider_authentication_failed", False),
        ("ProviderModelNotFoundError", "provider_model_not_found", False),
        ("ProviderRateLimitError", "provider_rate_limited", True),
        ("ProviderTimeoutError", "provider_timeout", True),
    ],
)
def test_m3_handler_returns_clear_retry_policy(provider_error, expected_code, retryable):
    from services.agents.brand_agent.handler import BrandAgent
    from services.agents.brand_agent.result import run_brand_profile_handler
    from services.agents.providers import errors

    class RaisingModel:
        def generate(self, **_kwargs):
            raise getattr(errors, provider_error)("safe synthetic provider error")

    context = [
        {
            "company_id": "company-1",
            "brand_id": "brand-1",
            "source_id": "source-1",
            "document_id": "document-1",
            "source_version": "1",
            "source_hash": "hash-1",
            "locator": "page=1",
            "text": "Source context",
        }
    ]
    result = run_brand_profile_handler(
        agent=BrandAgent(RaisingModel()),
        company_id="company-1",
        brand_id="brand-1",
        document_ids=["document-1"],
        job_id="job-1",
        run_id="run-1",
        input_snapshot_id="snapshot-1",
        business_hint="Fixture",
        context=context,
    )

    assert result.status == "failed"
    assert result.error.code == expected_code
    assert result.error.retryable is retryable
