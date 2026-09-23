from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import BaseModel

from services.agents.brand_agent import BrandAgent, run_brand_profile_handler
from services.agents.providers import (
    DeepSeekStructuredModel,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderModelNotFoundError,
    ProviderOutputError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    configured_deepseek_structured_model,
)
from services.agents.providers import deepseek as deepseek_provider


class Answer(BaseModel):
    answer: str
    citations: list[str]


def _completion(
    content: str | None,
    *,
    finish_reason: str | None = "stop",
    model: str = "deepseek-flash",
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, refusal=None),
            finish_reason=finish_reason,
        )],
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        next_value = self.responses.pop(0)
        if isinstance(next_value, Exception):
            raise next_value
        return next_value


class FakeAPIError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"fake status {status_code}")
        self.status_code = status_code


class FakeClient:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


def _model(client: FakeClient) -> DeepSeekStructuredModel:
    return DeepSeekStructuredModel(
        api_key="test-key",
        model="deepseek-flash",
        client=client,
    )


def test_deepseek_request_uses_json_mode_schema_and_validates_pydantic():
    client = FakeClient([_completion('{"answer":"Bếp Mộc","citations":["menu@page=2"]}')])
    model = _model(client)

    result, metadata = model.generate(
        system_prompt="Extract supported brand facts.",
        input_payload={"sources": [{"source_id": "menu", "text": "Bếp Mộc"}]},
        response_model=Answer,
    )

    request = client.completions.calls[0]
    assert request["model"] == "deepseek-flash"
    assert request["response_format"] == {"type": "json_object"}
    assert request["max_tokens"] == 8192
    assert not hasattr(client.chat.completions, "parse")
    assert "JSON" in request["messages"][0]["content"]
    assert '"answer"' in request["messages"][0]["content"]
    assert isinstance(result, Answer)
    assert result.answer == "Bếp Mộc"
    assert metadata.provider == "deepseek"
    assert metadata.model == "deepseek-flash"
    assert metadata.input_tokens == 11 and metadata.output_tokens == 7
    assert model.cost_estimate_available is False


@pytest.mark.parametrize(
    "first",
    [
        _completion(None),
        _completion('{"answer":"partial"', finish_reason="length"),
        _completion("not json"),
        _completion('{"wrong":"field"}'),
    ],
    ids=["empty", "truncated", "invalid-json", "invalid-schema"],
)
def test_deepseek_performs_one_repair_for_incomplete_or_invalid_json(first):
    client = FakeClient([
        first,
        _completion('{"answer":"repaired","citations":[]} ', prompt_tokens=3, completion_tokens=2),
    ])
    model = _model(client)

    result, metadata = model.generate(
        system_prompt="Extract.",
        input_payload={"sources": []},
        response_model=Answer,
    )

    assert result.answer == "repaired"
    assert len(client.completions.calls) == 2
    assert "Repair the previous response once" in client.completions.calls[1]["messages"][-1]["content"]
    assert model.last_repair_attempts == 1
    assert metadata.input_tokens == 14 and metadata.output_tokens == 9


def test_deepseek_does_not_repair_twice_and_reports_incomplete_output():
    client = FakeClient([
        _completion('{"answer":"bad"}'),
        _completion('{"answer":"still bad"}'),
    ])
    model = _model(client)

    with pytest.raises(ProviderOutputError) as caught:
        model.generate(
            system_prompt="Extract.", input_payload={}, response_model=Answer
        )

    assert len(client.completions.calls) == 2
    assert caught.value.repair_attempts == 1
    assert model.last_repair_attempts == 1


@pytest.mark.parametrize(
    ("error", "expected", "retryable"),
    [
        (FakeAPIError(401), ProviderAuthenticationError, False),
        (FakeAPIError(429), ProviderRateLimitError, True),
        (FakeAPIError(404), ProviderModelNotFoundError, False),
        (FakeAPIError(400), ProviderRequestError, False),
        (FakeAPIError(503), ProviderRequestError, True),
        (TimeoutError("private timeout details"), ProviderTimeoutError, True),
    ],
)
def test_deepseek_normalizes_auth_rate_limit_model_and_provider_errors(error, expected, retryable):
    client = FakeClient([error])
    model = _model(client)

    with pytest.raises(expected) as caught:
        model.generate(system_prompt="Extract.", input_payload={}, response_model=Answer)

    assert len(client.completions.calls) == 1
    assert caught.value.retryable is retryable


@pytest.mark.parametrize(
    ("status", "failure_code", "retryable"),
    [(404, "provider_model_not_found", False), (429, "provider_rate_limited", True)],
)
def test_brand_handler_maps_provider_errors_without_openai_specific_exception(
    status, failure_code, retryable
):
    client = FakeClient([FakeAPIError(status)])
    result = run_brand_profile_handler(
        agent=BrandAgent(_model(client)),
        company_id="tenant-a",
        brand_id="brand-a",
        document_ids=["doc-a"],
        job_id="job-a",
        run_id="run-a",
        input_snapshot_id="snapshot-a",
        business_hint="",
        context=[{
            "company_id": "tenant-a",
            "brand_id": "brand-a",
            "source_id": "source-a",
            "document_id": "doc-a",
            "source_version": "v1",
            "source_hash": "sha256:a",
            "locator": "page=1",
            "text": "Bếp Mộc",
        }],
    )

    assert result.status == "failed"
    assert result.error and result.error.code == failure_code
    assert result.error.retryable is retryable


def test_configured_factory_requires_deepseek_key_and_explicit_model():
    with pytest.raises(ProviderConfigurationError, match="DEEPSEEK_API_KEY"):
        configured_deepseek_structured_model({})
    with pytest.raises(ProviderConfigurationError, match="LLM_DEFAULT_MODEL"):
        configured_deepseek_structured_model({"DEEPSEEK_API_KEY": "present"})
    with pytest.raises(ProviderConfigurationError, match="must agree"):
        configured_deepseek_structured_model({
            "DEEPSEEK_API_KEY": "present",
            "DEEPSEEK_MODEL": "deepseek-flash",
            "LLM_DEFAULT_MODEL": "deepseek-v4-pro",
        })


def test_configured_factory_accepts_m2_llm_default_model(monkeypatch):
    fake_client = FakeClient([])
    monkeypatch.setattr(
        deepseek_provider,
        "_client",
        lambda _key, _timeout, _base_url, client=None: client or fake_client,
    )

    model = configured_deepseek_structured_model({
        "DEEPSEEK_API_KEY": "test-key",
        "LLM_DEFAULT_MODEL": "deepseek-flash",
    })

    assert model.model_name == "deepseek-flash"
    assert model.client is fake_client


def test_sdk_is_created_with_retries_disabled(monkeypatch):
    captured = {}
    openai_module = ModuleType("openai")

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return object()

    openai_module.OpenAI = fake_openai
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    deepseek_provider._client("test-key", 13, "https://api.deepseek.com")

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["timeout"] == 13
    assert captured["max_retries"] == 0
