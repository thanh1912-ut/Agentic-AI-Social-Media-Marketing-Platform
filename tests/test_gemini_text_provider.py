"""Native Gemini adapter fixtures; these tests never call Google."""

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from services.agents.providers.errors import ProviderContextLimitError, ProviderOutputError, ProviderRequestError, safe_provider_error_code
from services.agents.providers.gemini_text import GeminiStructuredModel
from services.agents.providers.comment_contracts import PrivacyApprovedCommentBatch


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: str


def adapter(handler, *, max_input_chars=24_000):
    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"x-goog-api-key": "synthetic-secret"})
    return GeminiStructuredModel(api_key="synthetic-secret", model="gemini-3.8-flash", client=client,
                                 max_input_chars=max_input_chars, max_tokens=1000)


def response(usage=None, *, text='{"caption":"Bài viết tiếng Việt"}', finish="STOP"):
    return httpx.Response(200, json={
        "modelVersion": "gemini-3.8-flash",
        "candidates": [{"finishReason": finish, "content": {"parts": [
            {"text": "private reasoning must not enter the output", "thought": True}, {"text": text},
        ]}}],
        "usageMetadata": usage or {},
    })


def test_native_text_generation_validates_json_and_counts_paid_thinking():
    requests = []
    def handler(request):
        requests.append(request)
        return response({"promptTokenCount": 20, "candidatesTokenCount": 10,
                         "thoughtsTokenCount": 15, "totalTokenCount": 45})
    model = adapter(handler)
    output, metadata = model.generate(system_prompt="Viết đúng hồ sơ Owner.",
                                      input_payload={"profile_text": "Chỉ bán cà phê"}, response_model=Draft)
    assert output.caption == "Bài viết tiếng Việt"
    assert metadata.provider == "gemini" and metadata.model == "gemini-3.8-flash"
    assert metadata.input_tokens == 20 and metadata.output_tokens == 25
    assert len(requests) == 1 and "synthetic-secret" not in str(requests[0].url)
    assert requests[0].url.host == "generativelanguage.googleapis.com"
    assert requests[0].url.path.endswith("/gemini-3.8-flash:generateContent")
    import json
    body = json.loads(requests[0].content)
    assert set(body) == {"systemInstruction", "contents", "generationConfig"}
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert "inlineData" not in str(body) and "tools" not in body
    assert model.last_repair_attempts == 0
    assert model.reservation_parameters() == {
        "max_input_tokens": 1_048_576, "max_output_tokens": 1000, "max_attempts": 1,
    }


@pytest.mark.parametrize("usage", [
    {}, {"promptTokenCount": 20, "candidatesTokenCount": 10},
    {"promptTokenCount": True, "candidatesTokenCount": 10, "totalTokenCount": 30},
    {"promptTokenCount": 20, "candidatesTokenCount": 10, "totalTokenCount": 29},
    {"promptTokenCount": 20, "candidatesTokenCount": 10, "thoughtsTokenCount": -1},
    {"promptTokenCount": 20, "candidatesTokenCount": 10, "thoughtsTokenCount": 5, "totalTokenCount": 31},
])
def test_missing_or_inconsistent_usage_preserves_output_for_ledger_reconciliation(usage):
    output, metadata = adapter(lambda _request: response(usage)).generate(
        system_prompt="Return draft.", input_payload={}, response_model=Draft,
    )
    assert output.caption and metadata is None  # Missing usage never becomes zero cost.


@pytest.mark.parametrize("text,finish", [('{"caption":12}', "STOP"), ('{}', "MAX_TOKENS"), ('', "STOP")])
def test_invalid_output_or_truncation_has_one_call_and_no_repair(text, finish):
    requests = []
    def handler(request):
        requests.append(request)
        return response(text=text, finish=finish)
    with pytest.raises(ProviderOutputError):
        adapter(handler).generate(system_prompt="Return draft.", input_payload={}, response_model=Draft)
    assert len(requests) == 1


def test_input_limit_rejects_before_network_request():
    requests = []
    def handler(request):
        requests.append(request)
        return response()
    with pytest.raises(ProviderContextLimitError):
        adapter(handler, max_input_chars=100).generate(system_prompt="x", input_payload={"text": "x" * 101}, response_model=Draft)
    assert requests == []


def comment_batch():
    return PrivacyApprovedCommentBatch.model_validate({
        "privacy_status": "approved_for_provider",
        "privacy_decision_id": "test-decision-01",
        "policy_version": "test-privacy-v1",
        "comments": [{"evidence_ref": "comment_run1_01", "text": "Có bảng giá không?"}],
    })


def test_comment_role_uses_gemini_and_sends_only_screened_text_and_refs():
    import json
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return response({"promptTokenCount": 20, "candidatesTokenCount": 10, "totalTokenCount": 30},
                        text=json.dumps({"topics": [{"category": "question", "topic": "giá",
                             "summary": "Hỏi bảng giá.", "evidence_refs": ["comment_run1_01"]}],
                             "limitations": ["Chỉ một đoạn đã được kiểm tra."]}))
    output, metadata = adapter(handler).summarize_screened_comments(batch=comment_batch())
    assert output.topics[0].evidence_refs == ["comment_run1_01"]
    assert metadata.provider == "gemini"
    sent = json.loads(requests[0]["contents"][0]["parts"][0]["text"])
    assert sent == {"comments": [{"evidence_ref": "comment_run1_01", "text": "Có bảng giá không?"}]}
    assert "test-decision-01" not in json.dumps(requests)


def test_comment_role_revalidates_privacy_hold_before_network():
    from pydantic import ValidationError
    batch = comment_batch()
    batch.privacy_status = "privacy_hold"
    requests = []
    with pytest.raises(ValidationError):
        adapter(lambda request: requests.append(request)).summarize_screened_comments(batch=batch)
    assert requests == []


def test_comment_role_rejects_citations_from_another_batch_without_repair():
    import json
    requests = []
    def handler(request):
        requests.append(request)
        return response(text=json.dumps({"topics": [{"category": "other", "topic": "x", "summary": "x",
                         "evidence_refs": ["comment_other_run"]}], "limitations": []}))
    with pytest.raises(ProviderOutputError, match="outside the supplied batch"):
        adapter(handler).summarize_screened_comments(batch=comment_batch())
    assert len(requests) == 1


def test_http_failure_keeps_safe_status_without_key_body_or_retry():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(503, json={"error": {"message": "raw-source-and-private-details"}})
    with pytest.raises(ProviderRequestError) as failure:
        adapter(handler).generate(system_prompt="Return draft.", input_payload={}, response_model=Draft)
    assert safe_provider_error_code(failure.value) == "provider_http_503"
    assert "raw-source" not in str(failure.value) and "synthetic-secret" not in str(failure.value)
    assert len(requests) == 1
