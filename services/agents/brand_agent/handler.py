from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import unicodedata

from packages.contracts import BrandProfile, GenerationMetadata, SourceReference
from packages.contracts.validation import parse_with_one_repair
from packages.prompts import BRAND_PROFILE_PROMPT_VERSION, BRAND_PROFILE_SYSTEM_PROMPT

from services.agents.model import StructuredModel, context_payload


class InvalidSourceReferenceError(ValueError):
    """A model cited an ID, version, locator, or excerpt outside its context."""


def _fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _ground_top_level_claims(profile: BrandProfile, context: Sequence[Mapping[str, str]]) -> BrandProfile:
    """Keep summary fields only when a matching evidence-backed fact supports them."""

    aliases = {
        "business": {"business", "company", "brand", "description"},
        "products": {"product", "products", "service", "services", "offer", "price"},
        "audience": {"audience", "target_audience", "customer", "customers"},
        "voice": {"voice", "tone", "brand_voice"},
        "constraints": {"constraint", "constraints", "restriction", "restrictions"},
    }
    context_by_identity = {
        (item.get("source_id"), item.get("locator")): item
        for item in context
    }
    facts_by_key: dict[str, list[tuple[str, set[tuple[str, str]]]]] = {}
    cited_locations: set[tuple[str, str]] = set()
    for fact in profile.facts:
        if fact.status == "inference" or not fact.evidence:
            continue
        locations = {(reference.source_id, reference.locator) for reference in fact.evidence}
        cited_locations.update(locations)
        facts_by_key.setdefault(_fold(fact.key).replace(" ", "_"), []).append(
            (fact.value, locations)
        )

    def supports(field: str, claim: str) -> bool:
        allowed_keys = aliases[field]
        folded_claim = _fold(claim)
        for fact_key, fact_values in facts_by_key.items():
            if fact_key not in allowed_keys:
                continue
            for fact_value, locations in fact_values:
                material = [fact_value]
                material.extend(
                    context_by_identity[location].get("text", "")
                    for location in locations
                    if location in context_by_identity
                )
                if any(folded_claim and folded_claim in _fold(text) for text in material):
                    return True
        return False

    updates: dict[str, Any] = {}
    unknowns = list(profile.unknowns)
    if not supports("business", profile.business):
        updates["business"] = "Chưa xác định từ nguồn hiện có."
        unknowns.append("Chưa có bằng chứng nguồn đủ để xác định doanh nghiệp/thương hiệu.")
    for field in ("products", "audience", "voice", "constraints"):
        values = getattr(profile, field)
        grounded = [value for value in values if supports(field, value)]
        if grounded != values:
            updates[field] = grounded
            for value in values:
                if value not in grounded:
                    unknowns.append(f"Chưa có bằng chứng nguồn cho {field}: {value}.")
    # A contradiction is actionable only when at least two distinct source
    # locations were cited by the grounded facts returned for this profile.
    if profile.contradictions and len(cited_locations) < 2:
        raise InvalidSourceReferenceError(
            "profile reports a contradiction without references to both source locations"
        )
    if updates:
        updates["unknowns"] = list(dict.fromkeys(unknowns))
        profile = profile.model_copy(update=updates)
    return profile


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
        input_snapshot_id: str | None = None,
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
        repairs += int(getattr(self.model, "last_repair_attempts", 0) or 0)
        if profile.brand_id != brand_id:
            raise ValueError("model returned a profile for a different brand_id")
        contexts = {
            (item["source_id"], item["locator"]): item
            for item in context
            if item.get("source_id") and item.get("locator")
        }
        for fact in profile.facts:
            for reference in fact.evidence:
                source = contexts.get((reference.source_id, reference.locator))
                if source is None:
                    raise InvalidSourceReferenceError(
                        "profile contains evidence outside retrieved context: "
                        f"{reference.source_id}@{reference.locator}"
                    )
                for field in ("document_id", "source_version"):
                    expected = source.get(field)
                    actual = getattr(reference, field)
                    if expected is not None and expected != actual:
                        raise InvalidSourceReferenceError(
                            f"profile evidence {field} does not match retrieved context"
                        )
                if reference.excerpt and reference.excerpt not in source.get("text", ""):
                    raise InvalidSourceReferenceError(
                        "profile evidence excerpt is not present in retrieved context"
                    )
        profile = _ground_top_level_claims(profile, context)
        # Confirmation is a backend/user action, never an AI decision.
        profile = profile.model_copy(update={"requires_confirmation": True})
        if metadata is not None:
            metadata = metadata.model_copy(
                update={
                    "prompt_version": BRAND_PROFILE_PROMPT_VERSION,
                    "schema_version": BrandProfile.__name__,
                    "input_snapshot_id": input_snapshot_id or "not-provided",
                }
            )
        return profile, metadata, repairs
