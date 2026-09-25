"""Small provider-neutral structured model boundary.

Concrete OpenAI/Anthropic adapters belong to the integration layer.  Agent
handlers depend only on this protocol, making fixtures deterministic and
keeping credentials/tokens out of prompts and normalized documents.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from packages.contracts import GenerationMetadata

ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredModel(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        response_model: type[ModelT],
    ) -> tuple[object, GenerationMetadata | None]:
        """Return raw structured data and optional provider instrumentation."""


def context_payload(context: list[Mapping[str, str]]) -> list[dict[str, str]]:
    """Copy only safe source context fields into a model payload."""

    safe_fields = (
        "source_id",
        "document_id",
        "source_version",
        "source_hash",
        "locator",
        "source_kind",
        "trust_level",
        "text",
    )
    return [{field: item[field] for field in safe_fields if field in item} for item in context]
