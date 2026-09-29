from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from services.agents.providers.errors import ProviderConfigurationError, ProviderOutputError
from services.agents.providers.qwen import (
    PrivacyApprovedCommentBatch,
    QwenCommentAnalysis,
    QwenStructuredModel,
    configured_qwen_structured_model,
)


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
    client = FakeClient([_completion(
        '{"topics":[{"category":"question","topic":"giá sản phẩm","summary":"Cần biết giá.",'
        '"evidence_refs":["comment_run1_01"]}],"limitations":[]}'
    )])
    model = QwenStructuredModel(
        api_key="test-key",
        model="qwen-explicit-model",
        base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=client,
    )

    batch = PrivacyApprovedCommentBatch.model_validate({
        "privacy_status": "approved_for_provider",
        "privacy_decision_id": "privacy-decision-01",
        "policy_version": "comment-screening-v1",
        "comments": [{"evidence_ref": "comment_run1_01", "text": "Cần biết giá và chính sách bảo hành."}],
    })
    result, metadata = model.summarize_screened_comments(batch=batch)

    request = client.chat.completions.calls[0]
    assert request["model"] == "qwen-explicit-model"
    assert request["response_format"] == {"type": "json_object"}
    assert "JSON" in request["messages"][0]["content"]
    assert "Cần biết giá và chính sách bảo hành" in request["messages"][1]["content"]
    assert result.topics[0].topic == "giá sản phẩm"
    assert metadata.provider == "qwen"
    assert metadata.model == "qwen-test-model"
    assert metadata.input_tokens == 12 and metadata.output_tokens == 4


def test_qwen_does_not_make_unreserved_repair_request():
    client = FakeClient([_completion('{"wrong":[]}', finish_reason="stop")])
    model = QwenStructuredModel(
        api_key="test-key", model="qwen-explicit-model",
        base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=client,
    )

    batch = PrivacyApprovedCommentBatch.model_validate({
        "privacy_status": "approved_for_provider",
        "privacy_decision_id": "privacy-decision-01",
        "policy_version": "comment-screening-v1",
        "comments": [{"evidence_ref": "comment_run1_01", "text": "Cần hỏi về giá."}],
    })
    with pytest.raises(ProviderOutputError, match="schema"):
        model.summarize_screened_comments(batch=batch)
    assert len(client.chat.completions.calls) == 1
    assert model.last_repair_attempts == 0


def test_qwen_summarizes_only_privacy_approved_batch_and_checks_citations():
    client = FakeClient([_completion(
        '{"topics":[{"category":"question","topic":"giá bán","summary":"Người đọc hỏi giá sản phẩm.",'
        '"evidence_refs":["comment_run1_01","comment_run1_02"]}],"limitations":[]}'
    )])
    model = QwenStructuredModel(
        api_key="test-key", model="qwen-explicit-model",
        base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=client,
    )
    batch = PrivacyApprovedCommentBatch.model_validate({
        "privacy_status": "approved_for_provider",
        "privacy_decision_id": "privacy-decision-01",
        "policy_version": "comment-screening-v1",
        "comments": [
            {"evidence_ref": "comment_run1_01", "text": "Cho mình xin giá sản phẩm."},
            {"evidence_ref": "comment_run1_02", "text": "Giá hiện tại bao nhiêu vậy?"},
        ],
    })

    result, _ = model.summarize_screened_comments(batch=batch)

    sent = client.chat.completions.calls[0]["messages"][1]["content"]
    assert "privacy-decision-01" not in sent and "comment-screening-v1" not in sent
    assert "comment_run1_01" in sent and "profile_url" not in sent
    assert result.topics[0].evidence_refs == ["comment_run1_01", "comment_run1_02"]


def test_qwen_comment_batch_requires_unique_run_scoped_refs_and_approved_status():
    with pytest.raises(ValidationError):
        PrivacyApprovedCommentBatch.model_validate({
            "privacy_status": "privacy_hold",
            "privacy_decision_id": "privacy-decision-01",
            "policy_version": "comment-screening-v1",
            "comments": [{"evidence_ref": "comment_run1_01", "text": "Cần giá."}],
        })
    with pytest.raises(ValidationError, match="unique"):
        PrivacyApprovedCommentBatch.model_validate({
            "privacy_status": "approved_for_provider",
            "privacy_decision_id": "privacy-decision-01",
            "policy_version": "comment-screening-v1",
            "comments": [
                {"evidence_ref": "comment_run1_01", "text": "Cần giá."},
                {"evidence_ref": "comment_run1_01", "text": "Cần bảo hành."},
            ],
        })


def test_qwen_generic_generation_path_is_disabled():
    model = QwenStructuredModel(
        api_key="test-key", model="qwen-explicit-model",
        base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=FakeClient([]),
    )
    with pytest.raises(ProviderConfigurationError, match="privacy-approved batch"):
        model.generate(system_prompt="ignored", input_payload={}, response_model=QwenCommentAnalysis)


def test_qwen_rejects_model_citations_outside_the_supplied_comment_batch():
    client = FakeClient([_completion(
        '{"topics":[{"category":"need","topic":"giá","summary":"Cần thông tin giá.",'
        '"evidence_refs":["comment_from_another_run"]}],"limitations":[]}'
    )])
    model = QwenStructuredModel(
        api_key="test-key", model="qwen-explicit-model",
        base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=client,
    )
    batch = PrivacyApprovedCommentBatch.model_validate({
        "privacy_status": "approved_for_provider",
        "privacy_decision_id": "privacy-decision-01",
        "policy_version": "comment-screening-v1",
        "comments": [{"evidence_ref": "comment_run1_01", "text": "Cần biết giá."}],
    })

    with pytest.raises(ProviderOutputError, match="outside the supplied batch"):
        model.summarize_screened_comments(batch=batch)


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
