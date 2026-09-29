"""Alibaba Model Studio Qwen JSON-mode adapter for bounded text tasks."""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit
from typing import Any

from .deepseek import DeepSeekStructuredModel, _positive_float, _positive_int
from .errors import ProviderConfigurationError


class QwenStructuredModel(DeepSeekStructuredModel):
    """Use Model Studio's OpenAI-compatible JSON-object chat endpoint.

    This adapter accepts text only. It does not fetch or upload media, comments,
    or arbitrary URLs; callers must complete privacy screening before use.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 60,
        max_tokens: int = 8192,
        max_input_chars: int = 24_000,
        client: Any = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderConfigurationError("QWEN_API_KEY is not configured for the server")
        if not model.strip():
            raise ProviderConfigurationError("QWEN_MODEL must name an enabled model")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment
        ):
            raise ProviderConfigurationError("QWEN_BASE_URL must be an HTTPS Model Studio endpoint")
        hostname = parsed.hostname.casefold()
        if hostname not in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"} and not hostname.endswith(
            ".maas.aliyuncs.com"
        ):
            raise ProviderConfigurationError("QWEN_BASE_URL host is not an official Alibaba Model Studio endpoint")
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            max_input_chars=max_input_chars,
            provider_label="Qwen",
            client=client,
        )


def configured_qwen_structured_model(
    environ: Mapping[str, str] | None = None,
) -> QwenStructuredModel:
    """Require an explicit model and regional endpoint; never infer a region."""

    env = os.environ if environ is None else environ
    api_key = env.get("QWEN_API_KEY", "")
    model = env.get("QWEN_MODEL", "").strip()
    base_url = env.get("QWEN_BASE_URL", "").strip()
    if not api_key:
        raise ProviderConfigurationError("QWEN_API_KEY is not configured for the server")
    if not model:
        raise ProviderConfigurationError("QWEN_MODEL must name an enabled model")
    if not base_url:
        raise ProviderConfigurationError("QWEN_BASE_URL must name the account's Model Studio region endpoint")
    return QwenStructuredModel(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_seconds=_positive_float(env.get("AI_REQUEST_TIMEOUT_SECONDS"), "AI_REQUEST_TIMEOUT_SECONDS", 60),
        max_tokens=_positive_int(env.get("QWEN_MAX_TOKENS"), "QWEN_MAX_TOKENS", 8192),
        max_input_chars=_positive_int(env.get("LLM_MAX_INPUT_CHARS"), "LLM_MAX_INPUT_CHARS", 24_000),
    )
