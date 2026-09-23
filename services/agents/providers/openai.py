"""Legacy OpenAI model and independent embedding adapters for M3.

Credentials are read only in the server process. SDK retries are disabled so
the worker's job retry policy remains authoritative. Model IDs are explicit
runtime settings; this module never selects an implicit model.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from packages.contracts import GenerationMetadata

from .errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderContextLimitError,
    ProviderError,
    ProviderOutputError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


# Kept as a compatibility alias for callers migrating from this older adapter.
OpenAIProviderError = ProviderError


def _client(api_key: str, timeout_seconds: float, client: Any = None) -> Any:
    if client is not None:
        return client
    try:
        from openai import OpenAI
    except ImportError as error:  # pragma: no cover - installation issue
        raise ProviderConfigurationError("Install the openai package to use this adapter") from error
    return OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)


def _positive_float(value: str | None, name: str, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        result = float(value)
    except ValueError as error:
        raise ProviderConfigurationError(f"{name} must be a positive number") from error
    if not math.isfinite(result) or result <= 0:
        raise ProviderConfigurationError(f"{name} must be a positive number")
    return result


def _optional_price(value: str | None, name: str) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        result = float(value)
    except ValueError as error:
        raise ProviderConfigurationError(f"{name} must be a non-negative number") from error
    if not math.isfinite(result) or result < 0:
        raise ProviderConfigurationError(f"{name} must be a non-negative number")
    return result


def _positive_int(value: str | None, name: str, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        result = int(value)
    except ValueError as error:
        raise ProviderConfigurationError(f"{name} must be a positive integer") from error
    if result <= 0:
        raise ProviderConfigurationError(f"{name} must be a positive integer")
    return result


def _request_error(error: Exception) -> ProviderError:
    kind = type(error).__name__.casefold()
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    if isinstance(error, TimeoutError) or "timeout" in kind:
        return ProviderTimeoutError("The configured model request timed out")
    if isinstance(error, ValidationError) or "lengthfinishreason" in kind:
        return ProviderOutputError("The model did not return valid structured output")
    if status in (401, 403):
        return ProviderAuthenticationError("The configured provider credentials were rejected")
    if status == 429:
        return ProviderRateLimitError("The configured provider rate limit was reached")
    if status is not None:
        return ProviderRequestError(
            "The configured model request failed",
            retryable=status in (408, 500, 502, 503, 504),
        )
    return ProviderRequestError("The configured model request failed", retryable=True)


class OpenAIStructuredModel:
    """One-shot adapter implementing the provider-neutral ``StructuredModel``."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 45,
        input_usd_per_million_tokens: float | None = None,
        output_usd_per_million_tokens: float | None = None,
        max_input_chars: int = 24_000,
        client: Any = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderConfigurationError("OPENAI_API_KEY is not configured for the server")
        if not model.strip():
            raise ProviderConfigurationError("LLM_DEFAULT_MODEL must name an enabled model")
        self.model_name = model.strip()
        self.timeout_seconds = _positive_float(str(timeout_seconds), "AI_REQUEST_TIMEOUT_SECONDS", 45)
        self.input_usd_per_million_tokens = input_usd_per_million_tokens
        self.output_usd_per_million_tokens = output_usd_per_million_tokens
        for rate in (input_usd_per_million_tokens, output_usd_per_million_tokens):
            if rate is not None and (not math.isfinite(rate) or rate < 0):
                raise ProviderConfigurationError("OpenAI token rates must be non-negative numbers")
        if max_input_chars <= 0:
            raise ProviderConfigurationError("LLM_MAX_INPUT_CHARS must be positive")
        self.max_input_chars = max_input_chars
        if (input_usd_per_million_tokens is None) != (output_usd_per_million_tokens is None):
            raise ProviderConfigurationError(
                "Configure both OpenAI token rates, or leave both unset"
            )
        self.cost_estimate_available = (
            input_usd_per_million_tokens is not None and output_usd_per_million_tokens is not None
        )
        self.client = _client(api_key, self.timeout_seconds, client)

    def generate(
        self,
        *,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        response_model: type[ModelT],
    ) -> tuple[object, GenerationMetadata | None]:
        started = time.monotonic()
        serialized_payload = json.dumps(input_payload, ensure_ascii=False)
        if len(serialized_payload) > self.max_input_chars:
            raise ProviderContextLimitError("The serialized model input exceeds LLM_MAX_INPUT_CHARS")
        try:
            completion = self.client.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": serialized_payload},
                ],
                response_format=response_model,
                timeout=self.timeout_seconds,
            )
        except Exception as error:
            raise _request_error(error) from None

        try:
            choice = completion.choices[0]
            message = choice.message
            if getattr(message, "refusal", None):
                raise ProviderOutputError("The model refused to generate the structured result")
            parsed = getattr(message, "parsed", None)
            if parsed is None:
                raise ProviderOutputError("The model returned no structured result")
            result = response_model.model_validate(parsed)
        except ProviderOutputError:
            raise
        except Exception:
            raise ProviderOutputError("The model returned an invalid structured result") from None

        usage = getattr(completion, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = 0.0
        if self.cost_estimate_available:
            cost = (
                input_tokens * self.input_usd_per_million_tokens
                + output_tokens * self.output_usd_per_million_tokens
            ) / 1_000_000
        metadata = GenerationMetadata(
            model=self.model_name,
            provider=self.provider_name,
            prompt_version="set-by-agent",
            schema_version=response_model.__name__,
            input_snapshot_id="set-by-caller",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
        return result, metadata


class OpenAIEmbeddingProvider:
    """Batched embeddings matching the current PostgreSQL vector width."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int = 1536,
        timeout_seconds: float = 45,
        client: Any = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderConfigurationError("OPENAI_API_KEY is not configured for the server")
        if not model.strip():
            raise ProviderConfigurationError("EMBEDDING_MODEL must name an enabled model")
        if dimensions <= 0:
            raise ProviderConfigurationError("embedding dimensions must be positive")
        self.model_name = model.strip()
        self.dimensions = dimensions
        self.timeout_seconds = _positive_float(str(timeout_seconds), "AI_REQUEST_TIMEOUT_SECONDS", 45)
        self.client = _client(api_key, self.timeout_seconds, client)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=list(texts),
                dimensions=self.dimensions,
                timeout=self.timeout_seconds,
            )
        except Exception as error:
            raise _request_error(error) from None
        try:
            vectors = [list(row.embedding) for row in response.data]
            valid = len(vectors) == len(texts) and all(
                len(vector) == self.dimensions
                and all(math.isfinite(float(value)) for value in vector)
                for vector in vectors
            )
        except (AttributeError, TypeError, ValueError):
            valid = False
            vectors = []
        if not valid:
            raise ProviderOutputError("The embedding provider returned invalid vectors")
        return [[float(value) for value in vector] for vector in vectors]


def configured_openai_structured_model(
    environ: Mapping[str, str] | None = None,
) -> OpenAIStructuredModel:
    """Build from explicit server configuration; no model is silently selected."""

    env = os.environ if environ is None else environ
    key = env.get("OPENAI_API_KEY", "")
    model = env.get("LLM_DEFAULT_MODEL", "")
    if not key:
        raise ProviderConfigurationError("OPENAI_API_KEY is not configured for the server")
    if not model:
        raise ProviderConfigurationError("LLM_DEFAULT_MODEL must name an enabled model")
    return OpenAIStructuredModel(
        api_key=key,
        model=model,
        timeout_seconds=_positive_float(env.get("AI_REQUEST_TIMEOUT_SECONDS"), "AI_REQUEST_TIMEOUT_SECONDS", 45),
        input_usd_per_million_tokens=_optional_price(
            env.get("OPENAI_INPUT_USD_PER_MILLION_TOKENS"),
            "OPENAI_INPUT_USD_PER_MILLION_TOKENS",
        ),
        output_usd_per_million_tokens=_optional_price(
            env.get("OPENAI_OUTPUT_USD_PER_MILLION_TOKENS"),
            "OPENAI_OUTPUT_USD_PER_MILLION_TOKENS",
        ),
        max_input_chars=_positive_int(env.get("LLM_MAX_INPUT_CHARS"), "LLM_MAX_INPUT_CHARS", 24_000),
    )


def configured_openai_embedding_provider(
    environ: Mapping[str, str] | None = None,
) -> OpenAIEmbeddingProvider:
    env = os.environ if environ is None else environ
    key = env.get("OPENAI_API_KEY", "")
    model = env.get("EMBEDDING_MODEL", "")
    if not key:
        raise ProviderConfigurationError("OPENAI_API_KEY is not configured for the server")
    if not model:
        raise ProviderConfigurationError("EMBEDDING_MODEL must name an enabled model")
    return OpenAIEmbeddingProvider(
        api_key=key,
        model=model,
        dimensions=1536,
        timeout_seconds=_positive_float(env.get("AI_REQUEST_TIMEOUT_SECONDS"), "AI_REQUEST_TIMEOUT_SECONDS", 45),
    )
