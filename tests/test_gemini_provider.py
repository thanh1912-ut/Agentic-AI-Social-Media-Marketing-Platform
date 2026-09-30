from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import pytest
from pydantic import BaseModel

from services.agents.providers.errors import ProviderConfigurationError, ProviderContextLimitError, ProviderOutputError
from services.agents.providers.gemini import (
    ApprovedMediaInput,
    GeminiMediaAnalyzer,
    configured_gemini_media_analyzer,
)


class MediaSummary(BaseModel):
    description: str
    timestamps: list[str]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def _media(mime_type: str = "image/png", content: bytes = b"safe synthetic image"):
    return ApprovedMediaInput(
        asset_id="asset-fixture",
        source_id="source-fixture",
        evidence_id="evidence-fixture",
        sha256_hex=sha256(content).hexdigest(),
        mime_type=mime_type,
        content=content,
        privacy_status="approved",
    )


def _response(text: str):
    return FakeResponse({
        "modelVersion": "configured-gemini-fixture",
        "candidates": [{
            "finishReason": "STOP",
            "content": {"parts": [{"text": text}]},
        }],
        "usageMetadata": {"promptTokenCount": 31, "candidatesTokenCount": 8, "totalTokenCount": 39},
    })


def test_gemini_sends_only_screened_inline_media_and_validates_structured_output():
    client = FakeHttpClient(_response('{"description":"Sản phẩm trên bàn","timestamps":["00:00:02"]}'))
    analyzer = GeminiMediaAnalyzer(api_key="fixture-secret", model="gemini-fixture-v1", client=client)

    result, metadata = analyzer.analyze_media(
        media=_media(),
        system_prompt="Summarize visible content. Do not identify people.",
        input_payload={"asset_kind": "page_post_image", "required_citations": True},
        response_model=MediaSummary,
    )

    url, request = client.calls[0]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-fixture-v1:generateContent"
    assert request["headers"] == {"Content-Type": "application/json"}
    body = request["json"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "image/png"
    assert "fixture-secret" not in repr(request)
    assert result.description == "Sản phẩm trên bàn"
    assert result.timestamps == ["00:00:02"]
    assert metadata.provider == "gemini"
    assert metadata.model == "configured-gemini-fixture"
    assert metadata.input_tokens == 31 and metadata.output_tokens == 8
    assert analyzer.cost_estimate_available is False


def test_gemini_rejects_privacy_hold_and_hash_mismatch_before_network_call():
    client = FakeHttpClient(_response('{"description":"x","timestamps":[]}'))
    analyzer = GeminiMediaAnalyzer(api_key="fixture-secret", model="gemini-fixture-v1", client=client)

    with pytest.raises(ProviderConfigurationError, match="privacy hold"):
        analyzer.analyze_media(
            media=replace(_media(), privacy_status="privacy_hold"),
            system_prompt="Analyze.", input_payload={}, response_model=MediaSummary,
        )
    with pytest.raises(ProviderConfigurationError, match="hash"):
        analyzer.analyze_media(
            media=replace(_media(), sha256_hex="0" * 64),
            system_prompt="Analyze.", input_payload={}, response_model=MediaSummary,
        )
    assert client.calls == []


def test_gemini_rejects_mime_asset_and_total_inline_size_limits():
    client = FakeHttpClient(_response('{"description":"x","timestamps":[]}'))
    analyzer = GeminiMediaAnalyzer(
        api_key="fixture-secret", model="gemini-fixture-v1", max_asset_bytes=10,
        max_inline_request_bytes=400, client=client,
    )
    with pytest.raises(ProviderContextLimitError, match="MAX_ASSET_BYTES"):
        analyzer.analyze_media(
            media=_media(content=b"a" * 11), system_prompt="Analyze.", input_payload={}, response_model=MediaSummary,
        )
    with pytest.raises(ProviderConfigurationError, match="MIME type"):
        analyzer.analyze_media(
            media=replace(_media(content=b"tiny"), mime_type="image/svg+xml"),
            system_prompt="Analyze.", input_payload={}, response_model=MediaSummary,
        )
    with pytest.raises(ProviderContextLimitError, match="Files API is not enabled"):
        analyzer.analyze_media(
            media=_media(content=b"tiny"), system_prompt="A" * 1000,
            input_payload={}, response_model=MediaSummary,
        )
    assert client.calls == []


def test_gemini_does_not_auto_repair_invalid_media_output():
    client = FakeHttpClient(_response('{"description":12,"timestamps":[]}'))
    analyzer = GeminiMediaAnalyzer(api_key="fixture-secret", model="gemini-fixture-v1", client=client)

    with pytest.raises(ProviderOutputError, match="did not match"):
        analyzer.analyze_media(
            media=_media("video/mp4"),
            system_prompt="Describe this short clip with timestamps.",
            input_payload={"media_kind": "video"}, response_model=MediaSummary,
        )
    assert len(client.calls) == 1


def test_gemini_requires_explicit_server_configuration_and_model_path_is_safe():
    with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY"):
        configured_gemini_media_analyzer({})
    with pytest.raises(ProviderConfigurationError, match="GEMINI_MODEL"):
        configured_gemini_media_analyzer({"GEMINI_API_KEY": "fixture-secret"})
    with pytest.raises(ProviderConfigurationError, match="explicit enabled model"):
        GeminiMediaAnalyzer(api_key="fixture-secret", model="../other", client=FakeHttpClient(_response("{}")))


def test_video_input_is_supported_with_exact_mime_and_provenance():
    media = _media("video/mp4", b"small-safe-synthetic-video")
    client = FakeHttpClient(_response('{"description":"A short clip","timestamps":["00:00:01"]}'))
    analyzer = GeminiMediaAnalyzer(api_key="fixture-secret", model="gemini-fixture-v1", client=client)

    result, _ = analyzer.analyze_media(
        media=media,
        system_prompt="Describe video events and give timestamps.",
        input_payload={"expected_provenance": media.evidence_id},
        response_model=MediaSummary,
    )

    assert result.timestamps == ["00:00:01"]
    parts = client.calls[0][1]["json"]["contents"][0]["parts"]
    assert parts[1]["inlineData"]["mimeType"] == "video/mp4"
