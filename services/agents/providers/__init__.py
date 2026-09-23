"""Concrete provider adapters for the M3 agent boundary."""

from .deepseek import (
    DEEPSEEK_BASE_URL,
    DeepSeekStructuredModel,
    configured_deepseek_structured_model,
)
from .errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderContextLimitError,
    ProviderError,
    ProviderModelNotFoundError,
    ProviderOutputError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
)
from .fastembed import FastEmbedLocalEmbeddingProvider
from .openai import (
    OpenAIEmbeddingProvider,
    OpenAIProviderError,
    OpenAIStructuredModel,
    configured_openai_embedding_provider,
    configured_openai_structured_model,
)

__all__ = [
    "DEEPSEEK_BASE_URL",
    "DeepSeekStructuredModel",
    "FastEmbedLocalEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "OpenAIProviderError",
    "OpenAIStructuredModel",
    "ProviderAuthenticationError",
    "ProviderContextLimitError",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderModelNotFoundError",
    "ProviderOutputError",
    "ProviderRateLimitError",
    "ProviderRequestError",
    "ProviderTimeoutError",
    "configured_deepseek_structured_model",
    "configured_openai_embedding_provider",
    "configured_openai_structured_model",
]
