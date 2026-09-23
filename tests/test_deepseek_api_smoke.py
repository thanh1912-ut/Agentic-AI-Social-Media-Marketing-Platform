"""Opt-in live DeepSeek API smoke test; never runs as part of fixture CI."""

from __future__ import annotations

import os
from typing import Literal

import pytest
from pydantic import BaseModel

from services.worker.model_provider import configured_structured_model


class DeepSeekSmokeResult(BaseModel):
    ok: bool
    provider: Literal["deepseek"]


@pytest.mark.api_smoke
def test_live_deepseek_structured_generation():
    if os.getenv("RUN_DEEPSEEK_API_SMOKE") != "1":
        pytest.skip("Set RUN_DEEPSEEK_API_SMOKE=1 in a secured server environment to run the live smoke test")
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY is unavailable in this secured environment")

    adapter = configured_structured_model()
    result, metadata = adapter.generate(
        system_prompt="Return a valid JSON object. Do not include any other text.",
        input_payload={"ok": True, "provider": "deepseek"},
        response_model=DeepSeekSmokeResult,
    )

    assert result.ok is True
    assert result.provider == "deepseek"
    assert metadata is not None and metadata.provider == "deepseek"
