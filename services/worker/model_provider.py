"""M2-owned provider selection and factories; adapter implementation is M3-owned."""

from __future__ import annotations

from services.api.config import settings


class AIConfigurationError(RuntimeError):
    """The selected provider is missing required server-side configuration."""


def configured_structured_model():
    """Return M3's configured adapter; M2 does not implement an LLM client."""

    if settings.llm_provider != "deepseek":
        raise AIConfigurationError("LLM_PROVIDER must be deepseek; no provider fallback is configured")
    if not settings.deepseek_api_key:
        raise AIConfigurationError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
    if not settings.llm_default_model:
        raise AIConfigurationError("LLM_DEFAULT_MODEL must name an available DeepSeek model")
    try:
        from services.agents.providers.deepseek import DeepSeekStructuredModel
    except ImportError as error:
        raise AIConfigurationError("The M3 DeepSeek adapter is unavailable in this deployment") from error
    return DeepSeekStructuredModel(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.llm_default_model,
        timeout_seconds=settings.ai_request_timeout_seconds,
    )


def configured_embedding_provider():
    """Embeddings are independent of the LLM and default to explicit lexical mode."""

    if settings.embedding_provider == "none":
        return None
    if settings.embedding_provider != "openai":
        raise AIConfigurationError(f"Unsupported EMBEDDING_PROVIDER: {settings.embedding_provider}")
    if not settings.embedding_api_key or not settings.embedding_model:
        raise AIConfigurationError(
            "EMBEDDING_API_KEY and EMBEDDING_MODEL are required when EMBEDDING_PROVIDER=openai"
        )
    try:
        from services.agents.providers.openai import OpenAIEmbeddingProvider
    except ImportError as error:
        raise AIConfigurationError("The configured embedding adapter is unavailable") from error
    return OpenAIEmbeddingProvider(
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.ai_request_timeout_seconds,
    )
