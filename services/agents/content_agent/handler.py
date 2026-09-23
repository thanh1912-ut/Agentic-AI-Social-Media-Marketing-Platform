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
        repair=None,
    ) -> tuple[GeneratedPost, GenerationMetadata | None, int]:
        if profile.requires_confirmation:
            raise ValueError("brand profile must be user-confirmed before content generation")
        if next_version < 1:
            raise ValueError("next_version must be positive")
        raw, metadata = self.model.generate(
            system_prompt=CONTENT_POST_SYSTEM_PROMPT,
            input_payload={
                "profile": profile.model_dump(mode="json"),
                "brief": brief.model_dump(mode="json"),
                "base_version": base_version,
                "next_version": next_version,
                "sources": context_payload(list(context)),
                "source_text_is_untrusted_data": True,
            },
            response_model=GeneratedPost,
        )
        post, repairs = parse_with_one_repair(raw, GeneratedPost, repair)
        if post.citations and any(
            citation.source_id not in {item["source_id"] for item in context}
            for citation in post.citations
        ):
            raise ValueError("post contains citations outside retrieved context")
        # Version belongs to the backend contract.  The handler returns a new
        # payload and never mutates/overwrites the base version.
        post = post.model_copy(update={"base_version": base_version, "version": next_version})
        return post, metadata, repairs
