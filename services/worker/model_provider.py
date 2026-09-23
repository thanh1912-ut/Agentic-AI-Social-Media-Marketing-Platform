"""Provider adapter for M3's structured-model interface."""

from __future__ import annotations

import time
import json
from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel

from packages.contracts import GenerationMetadata
from services.api.config import settings

ModelT = TypeVar("ModelT", bound=BaseModel)


class AIConfigurationError(RuntimeError):
    """The worker cannot reach a configured structured model provider."""


class OpenAIStructuredModel:
    """OpenAI adapter; the API key is kept in process settings, never payloads."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None, client=None) -> None:
        resolved_key = api_key if api_key is not None else settings.openai_api_key
        if client is None and not resolved_key:
            raise AIConfigurationError("OPENAI_API_KEY is not configured for the worker")
        self.model_name = model or settings.llm_default_model
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=resolved_key, timeout=settings.ai_request_timeout_seconds)
        self.client = client

    def generate(
        self,
        *,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        response_model: type[ModelT],
    ) -> tuple[object, GenerationMetadata | None]:
        started = time.monotonic()
        completion = self.client.chat.completions.parse(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
            ],
            response_format=response_model,
        )
        choice = completion.choices[0]
        if choice.message.refusal:
            raise RuntimeError("The model refused to generate a Brand Profile")
        if choice.message.parsed is None:
            raise RuntimeError("The model returned no structured Brand Profile")
        usage = completion.usage
        metadata = GenerationMetadata(
            model=self.model_name,
            provider="openai",
            prompt_version="provider-neutral-v1",
            schema_version=response_model.__name__,
            input_snapshot_id="pending-persistence",
            input_tokens=int(usage.prompt_tokens) if usage else 0,
            output_tokens=int(usage.completion_tokens) if usage else 0,
            # Provider pricing changes independently of code; a missing cost
            # estimate is represented as 0 and flagged in persisted run metadata.
            estimated_cost_usd=0.0,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
        return choice.message.parsed, metadata


class OpenAIEmbeddingProvider:
    """Optional batch embedder used by the pgvector adapter when configured."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None, client=None) -> None:
        resolved_key = api_key if api_key is not None else settings.openai_api_key
        resolved_model = model or settings.embedding_model
        if not resolved_model:
            raise AIConfigurationError("EMBEDDING_MODEL is not configured")
        if client is None and not resolved_key:
            raise AIConfigurationError("OPENAI_API_KEY is not configured for embeddings")
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=resolved_key, timeout=settings.ai_request_timeout_seconds)
        self.client = client
        self.model_name = resolved_model

    def embed(self, texts):
        response = self.client.embeddings.create(model=self.model_name, input=list(texts), dimensions=1536)
        return [item.embedding for item in response.data]


def configured_embedding_provider() -> OpenAIEmbeddingProvider | None:
    if settings.openai_api_key and settings.embedding_model:
        return OpenAIEmbeddingProvider()
    return None
