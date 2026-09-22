from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.contracts import (
    AnalyticsInsight,
    BrandFact,
    BrandProfile,
    GeneratedPost,
    NormalizedDocument,
    Recommendation,
    SourceReference,
)
from packages.contracts.validation import parse_with_one_repair


def source() -> SourceReference:
    return SourceReference(
        source_id="source-menu",
        document_id="doc-1",
        source_version="v1",
        locator="page=1",
        excerpt="Cơm gà 65.000đ",
    )


def test_normalized_document_rejects_unknown_fields(normalized_document: NormalizedDocument) -> None:
    payload = normalized_document.model_dump()
    payload["unexpected"] = "must not cross contract"
    with pytest.raises(ValidationError):
        NormalizedDocument.model_validate(payload)


def test_confirmed_fact_requires_source() -> None:
    with pytest.raises(ValidationError):
        BrandFact(key="price", value="65.000đ", status="confirmed")


def test_generated_post_evidence_must_resolve_to_citation() -> None:
    with pytest.raises(ValidationError):
        GeneratedPost(
            base_version="draft-1",
            version=1,
            channel="facebook",
            caption="Món Việt cho bữa tối.",
            evidence_ids=["source-menu"],
        )


def test_structured_output_repair_is_bounded() -> None:
    calls = 0

    def repair(payload: object, _error: ValidationError) -> object:
        nonlocal calls
        calls += 1
        return {"business": payload, "brand_id": "brand-1"}

    profile, repairs = parse_with_one_repair(
        "Bếp Mộc",
        BrandProfile,
        repair,
    )
    assert profile.business == "Bếp Mộc"
    assert repairs == 1
    assert calls == 1


def test_recommendation_requires_evidence_when_confident() -> None:
    with pytest.raises(ValidationError):
        Recommendation(
            observation="Reach của nhóm A cao hơn.",
            hypothesis="Hook ngắn phù hợp hơn.",
            action="Thử 3 bài hook ngắn.",
            expected_impact="Tăng reach.",
            experiment={
                "name": "Hook test",
                "hypothesis": "Hook ngắn tăng reach",
                "action": "Đăng 3 bài",
                "metric": "reach",
                "threshold": ">=10%",
                "duration_days": 14,
            },
            metric="reach",
            threshold=">=10%",
            confidence=0.8,
            created_at=datetime.now(timezone.utc),
        )
