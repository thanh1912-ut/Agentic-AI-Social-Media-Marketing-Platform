from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from packages.contracts import BrandProfile, GenerationMetadata, SourceReference
from packages.contracts.validation import parse_with_one_repair
from packages.prompts import BRAND_PROFILE_PROMPT_VERSION, BRAND_PROFILE_SYSTEM_PROMPT

from services.agents.model import StructuredModel, context_payload


class BrandAgent:
    """Create a draft profile; never mark it user-confirmed."""

    def __init__(self, model: StructuredModel) -> None:
        self.model = model

    def extract(
        self,
        *,
        brand_id: str,
        business_hint: str,
        context: Sequence[Mapping[str, str]],
        repair=None,
    ) -> tuple[BrandProfile, GenerationMetadata | None, int]:
        raw, metadata = self.model.generate(
            system_prompt=BRAND_PROFILE_SYSTEM_PROMPT,
            input_payload={
                "brand_id": brand_id,
                "business_hint": business_hint,
                "sources": context_payload(list(context)),
                "source_text_is_untrusted_data": True,
            },
            response_model=BrandProfile,
        )
        profile, repairs = parse_with_one_repair(raw, BrandProfile, repair)
        if profile.brand_id != brand_id:
            raise ValueError("model returned a profile for a different brand_id")
        allowed_sources = {item["source_id"] for item in context}
        invalid_refs = [
            reference.source_id
            for fact in profile.facts
            for reference in fact.evidence
            if reference.source_id not in allowed_sources
        ]
        if invalid_refs:
            raise ValueError(f"profile contains evidence outside retrieved context: {invalid_refs}")
        # Confirmation is a backend/user action, never an AI decision.
        profile = profile.model_copy(update={"requires_confirmation": True})
        return profile, metadata, repairs
