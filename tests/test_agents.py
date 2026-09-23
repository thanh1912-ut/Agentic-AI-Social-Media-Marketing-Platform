from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from packages.contracts import BrandFact, BrandProfile, CampaignBrief, GeneratedPost, SourceReference
from services.agents.brand_agent import BrandAgent
from services.agents.content_agent import ContentAgent


@dataclass
class FakeStructuredModel:
    response: object

    def generate(self, *, system_prompt, input_payload, response_model):
        assert "source_text_is_untrusted_data" in input_payload
        assert "source" in system_prompt.lower() or "structured" in system_prompt.lower()
        if "profile" in input_payload:
            assert input_payload["profile"]["brand_id"] == "confirmed-brand"
        return self.response, None


def source_ref() -> SourceReference:
    return SourceReference(
        source_id="source-menu",
        document_id="doc-1",
        source_version="v1",
        locator="page=1",
    )


def test_brand_agent_never_confirms_profile() -> None:
    model = FakeStructuredModel(
        BrandProfile(
            brand_id="brand-1",
            business="Bếp Mộc",
            facts=[BrandFact(key="business", value="Bếp Mộc", status="confirmed", evidence=[source_ref()])],
            requires_confirmation=False,
        )
    )
    profile, metadata, repairs = BrandAgent(model).extract(
        brand_id="brand-1",
        business_hint="Bếp Mộc",
        context=[{"source_id": "source-menu", "locator": "page=1", "text": "Bếp Mộc"}],
    )
    assert profile.requires_confirmation is True
    assert metadata is None
    assert repairs == 0


def test_brand_agent_does_not_send_database_brand_id_to_provider() -> None:
    class CapturingModel:
        payload = None

        def generate(self, *, system_prompt, input_payload, response_model):
            self.payload = input_payload
            return BrandProfile(brand_id=input_payload["brand_id"], business="Bếp Mộc"), None

    model = CapturingModel()
    profile, _, _ = BrandAgent(model).extract(
        brand_id="internal-database-brand-id",
        business_hint="Bếp Mộc",
        context=[],
    )
    assert model.payload["brand_id"] == "brand-profile"
    assert profile.brand_id == "internal-database-brand-id"


def test_brand_agent_rejects_citation_outside_context() -> None:
    model = FakeStructuredModel(
        BrandProfile(
            brand_id="brand-1",
            business="Bếp Mộc",
            facts=[
                BrandFact(
                    key="business",
                    value="Bếp Mộc",
                    status="confirmed",
                    evidence=[source_ref().model_copy(update={"source_id": "not-retrieved"})],
                )
            ],
        )
    )
    with pytest.raises(ValueError, match="outside retrieved context"):
        BrandAgent(model).extract(
            brand_id="brand-1",
            business_hint="Bếp Mộc",
            context=[{"source_id": "source-menu", "locator": "page=1", "text": "Bếp Mộc"}],
        )


def test_content_agent_requires_confirmation() -> None:
    profile = BrandProfile(brand_id="brand-1", business="Bếp Mộc")
    brief = CampaignBrief(objective="Tăng nhận biết", audience="Gia đình", channel="facebook")
    with pytest.raises(ValueError, match="confirmed"):
        ContentAgent(FakeStructuredModel(object())).generate(
            profile=profile,
            brief=brief,
            base_version="post-v1",
            next_version=2,
            context=[],
        )


def test_content_agent_returns_new_backend_version() -> None:
    profile = BrandProfile(
        brand_id="brand-1",
        business="Bếp Mộc",
        requires_confirmation=False,
    )
    brief = CampaignBrief(objective="Tăng nhận biết", audience="Gia đình", channel="facebook")
    raw = GeneratedPost(
        base_version="model-must-not-win",
        version=1,
        channel="facebook",
        caption="Bữa cơm Việt gần gũi.",
    )
    post, _, _ = ContentAgent(FakeStructuredModel(raw)).generate(
        profile=profile,
        brief=brief,
        base_version="post-v1",
        next_version=2,
        context=[],
    )
    assert post.base_version == "post-v1"
    assert post.version == 2


def test_content_agent_rejects_citation_metadata_not_from_exact_source() -> None:
    profile = BrandProfile(brand_id="db-brand-id", business="Bếp Mộc", requires_confirmation=False)
    brief = CampaignBrief(objective="Nhận biết", audience="Gia đình", channel="facebook_page")
    raw = GeneratedPost(
        base_version="ignored", version=1, channel="ignored", caption="Cơm gà Bếp Mộc.",
        citations=[SourceReference(
            source_id="source-1", document_id="another-document", source_version="1",
            locator="page=1", excerpt="Cơm gà",
        )],
    )
    with pytest.raises(ValueError, match="exact retrieved source"):
        ContentAgent(FakeStructuredModel(raw)).generate(
            profile=profile,
            brief=brief,
            base_version="base-v1",
            next_version=1,
            context=[{
                "source_id": "source-1", "document_id": "doc-1", "source_version": "1",
                "source_hash": "a" * 64, "locator": "page=1", "text": "Cơm gà Bếp Mộc.",
            }],
        )
