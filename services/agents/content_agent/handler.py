from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from packages.contracts import BrandProfile, CampaignBrief, GeneratedPost, GenerationMetadata
from packages.contracts.validation import parse_with_one_repair
from packages.prompts import CONTENT_POST_PROMPT_VERSION, CONTENT_POST_SYSTEM_PROMPT

from services.agents.model import StructuredModel, context_payload


class ContentAgent:
    """Generate an immutable new post version from a confirmed profile."""

    def __init__(self, model: StructuredModel) -> None:
        self.model = model

    def generate(
        self,
        *,
        profile: BrandProfile,
        brief: CampaignBrief,
        base_version: str,
        next_version: int,
        context: Sequence[Mapping[str, str]],
        content_requirements: Mapping[str, Any] | None = None,
        channel: str | None = None,
        repair=None,
    ) -> tuple[GeneratedPost, GenerationMetadata | None, int]:
        if profile.requires_confirmation:
            raise ValueError("brand profile must be user-confirmed before content generation")
        if next_version < 1:
            raise ValueError("next_version must be positive")
        raw, metadata = self.model.generate(
            system_prompt=CONTENT_POST_SYSTEM_PROMPT,
            input_payload={
                # The provider needs profile content, not the database brand ID.
                "profile": profile.model_dump(mode="json") | {"brand_id": "confirmed-brand"},
                "brief": brief.model_dump(mode="json"),
                "base_version": base_version,
                "next_version": next_version,
                "sources": context_payload(list(context)),
                "content_requirements": dict(content_requirements or {}),
                "source_text_is_untrusted_data": True,
            },
            response_model=GeneratedPost,
        )
        post, repairs = parse_with_one_repair(raw, GeneratedPost, repair)
        sources_by_id = {item["source_id"]: item for item in context}
        for citation in post.citations:
            source = sources_by_id.get(citation.source_id)
            if (
                source is None
                or citation.document_id != source.get("document_id")
                or citation.source_version != source.get("source_version")
                or citation.locator != source.get("locator")
                or (citation.excerpt is not None and citation.excerpt not in source.get("text", ""))
            ):
                raise ValueError("post contains a citation outside its exact retrieved source context")
        # Version belongs to the backend contract.  The handler returns a new
        # payload and never mutates/overwrites the base version.
        post = post.model_copy(update={
            "base_version": base_version,
            "version": next_version,
            "metadata": None,
            **({"channel": channel} if channel else {}),
        })
        return post, metadata, repairs
