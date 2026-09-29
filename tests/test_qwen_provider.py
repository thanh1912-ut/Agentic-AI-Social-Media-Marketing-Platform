from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from services.agents.providers.errors import ProviderConfigurationError
from services.agents.providers.qwen import QwenStructuredModel, configured_qwen_structured_model


class Summary(BaseModel):
    topics: list[str]


def _completion(content: str, *, finish_reason: str = "stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, refusal=None),
            finish_reason=finish_reason,
        )],
        model="qwen-test-model",
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4),
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    def __init__(self, responses):
        completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=completions)


def test_qwen_uses_explicit_regional_endpoint_json_mode_and_validates_output():
    client = FakeClient([_completion('{"topics":["giá sản phẩm","bảo hành"]}')])
    model = QwenStructuredModel(
        api_key="test-key",
        model="qwen-explicit-model",
        base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=client,
    )

    result, metadata = model.generate(
        system_prompt="Summarize only the supplied screened comments. JSON output.",
        input_payload={"comments": ["Cần biết giá và chính sách bảo hành."]},
        response_model=Summary,
    )

    request = client.chat.completions.calls[0]
    assert request["model"] == "qwen-explicit-model"
    assert request["response_format"] == {"type": "json_object"}
    assert "JSON" in request["messages"][0]["content"]
    assert result.topics == ["giá sản phẩm", "bảo hành"]
    assert metadata.provider == "qwen"
    assert metadata.model == "qwen-test-model"
    assert metadata.input_tokens == 12 and metadata.output_tokens == 4


def test_qwen_repairs_invalid_structured_output_once():
    client = FakeClient([
        _completion('{"wrong":[]}', finish_reason="stop"),
        _completion('{"topics":["câu hỏi về giá"]}'),
    ])
    model = QwenStructuredModel(
        api_key="test-key", model="qwen-explicit-model",
        base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=client,
    )

    result, metadata = model.generate(
        system_prompt="Return JSON.", input_payload={"batch_id": "batch-1"}, response_model=Summary,
    )

    assert result.topics == ["câu hỏi về giá"]
    assert len(client.chat.completions.calls) == 2
    assert "Repair the previous response once" in client.chat.completions.calls[1]["messages"][-1]["content"]
    assert model.last_repair_attempts == 1
    assert metadata.input_tokens == 24 and metadata.output_tokens == 8


def test_qwen_requires_explicit_key_model_and_region_endpoint():
    with pytest.raises(ProviderConfigurationError, match="QWEN_API_KEY"):
        configured_qwen_structured_model({})
    with pytest.raises(ProviderConfigurationError, match="QWEN_MODEL"):
        configured_qwen_structured_model({"QWEN_API_KEY": "present"})
    with pytest.raises(ProviderConfigurationError, match="QWEN_BASE_URL"):
        configured_qwen_structured_model({"QWEN_API_KEY": "present", "QWEN_MODEL": "qwen-test"})
    with pytest.raises(ProviderConfigurationError, match="HTTPS"):
        QwenStructuredModel(
            api_key="test-key", model="qwen-test", base_url="http://127.0.0.1:1234/v1",
        )
    with pytest.raises(ProviderConfigurationError, match="official Alibaba"):
        QwenStructuredModel(
            api_key="test-key", model="qwen-test", base_url="https://example.com/v1",
        )


def test_qwen_factory_does_not_print_or_select_an_implicit_model(monkeypatch):
    monkeypatch.setattr("services.agents.providers.deepseek._client", lambda *args, **kwargs: object())
    model = configured_qwen_structured_model({
        "QWEN_API_KEY": "private-test-key",
        "QWEN_MODEL": "qwen-explicit-model",
        "QWEN_BASE_URL": "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
    })

    assert model.model_name == "qwen-explicit-model"
    assert model.provider_name == "qwen"
    assert "private-test-key" not in repr(model)
