from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from services.worker.ai_budget import (
    PricingUnavailable,
    Reservation,
    cost_micro_usd,
    price_for,
    reserve_upper_bound_micro_usd,
    reserve_token_bound_micro_usd,
)


def test_deepseek_cost_uses_micro_usd_and_rounds_up() -> None:
    flash = price_for("deepseek", "deepseek-flash")
    assert cost_micro_usd(flash, input_tokens=1, output_tokens=0) == 1
    assert cost_micro_usd(flash, input_tokens=1_000_000, output_tokens=1_000_000) == 1_500_000
    pro = price_for("deepseek", "deepseek-v4-pro")
    assert cost_micro_usd(pro, input_tokens=1_000_000, output_tokens=1_000_000) == 5_280_000


def test_reservation_bounds_initial_and_repair_requests() -> None:
    price = price_for("deepseek", "deepseek-flash")
    reservation = reserve_upper_bound_micro_usd(
        price, max_input_chars=24_000, max_output_tokens=8_192,
    )
    assert reservation > cost_micro_usd(price, 24_000, 8_192)
    assert reservation == 151_061


def test_gemini_and_qwen_prices_are_pinned_to_exact_model_and_region() -> None:
    gemini = price_for("gemini", "gemini-3.8-flash", on_date=date(2026, 9, 30))
    assert cost_micro_usd(gemini, input_tokens=1_000_000, output_tokens=1_000_000) == 4_500_000
    assert reserve_token_bound_micro_usd(
        gemini, max_input_tokens=10_000, max_output_tokens=1_000,
    ) == 11_250

    qwen = price_for("qwen", "qwen3.8-27b", region="singapore")
    assert qwen.basis == "singapore_international_list_price"
    assert cost_micro_usd(qwen, input_tokens=1_000_000, output_tokens=1_000_000) == 3_500_000
    with pytest.raises(PricingUnavailable, match="region_unverified"):
        price_for("qwen", "qwen3.8-27b", region="beijing")
    with pytest.raises(PricingUnavailable, match="region_unverified"):
        price_for("qwen", "qwen3.8-27b")
    with pytest.raises(PricingUnavailable, match="expired"):
        price_for("gemini", "gemini-3.8-flash", on_date=date(2027, 1, 1))


def test_non_deepseek_reservation_requires_explicit_token_bounds() -> None:
    from services.worker.ai_budget import reserve_automatic_request

    async def reserve_without_bounds():
        return await reserve_automatic_request(
            company_id="workspace-test", request_key="media-run-1", provider="gemini",
            model="gemini-3.8-flash", operation="media_analysis",
        )

    with pytest.raises(PricingUnavailable, match="reservation_bounds_unavailable"):
        asyncio.run(reserve_without_bounds())


@pytest.mark.parametrize("provider,model", [
    ("gemini", "some-model"),
    ("qwen", "some-model"),
    ("deepseek", "latest"),
    ("deepseek", "unreviewed-model"),
])
def test_unknown_provider_or_price_fails_closed(provider: str, model: str) -> None:
    with pytest.raises(PricingUnavailable):
        price_for(provider, model)


def test_cost_rejects_negative_usage() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        cost_micro_usd(price_for("deepseek", "deepseek-flash"), -1, 0)


@pytest.mark.parametrize("reservation_status", ["deferred_budget", "uncertain"])
def test_research_report_does_not_call_provider_without_a_fresh_reservation(
    monkeypatch: pytest.MonkeyPatch, reservation_status: str,
) -> None:
    from services.worker import research_tasks

    class Model:
        model_name = "deepseek-flash"

        def generate(self, **_kwargs):
            pytest.fail("provider must not be called for a deferred/uncertain reservation")

    async def fake_reserve(**_kwargs):
        return Reservation(reservation_status, "cycle-key")

    monkeypatch.setattr(research_tasks, "configured_structured_model", lambda: Model())
    monkeypatch.setattr(research_tasks, "reserve_automatic_request", fake_reserve)
    async def no_owner_profile(_company_id):
        return None, {"status": "not_configured"}

    monkeypatch.setattr(research_tasks, "_active_owner_brand_context", no_owner_profile)
    group = SimpleNamespace(industry="", region="", locale="vi-VN", keywords_json=[])
    evidence = [{"id": "evidence-1", "title": "fixture", "url": "https://example.invalid/"}]
    report, model_name, status = asyncio.run(research_tasks._make_report(
        "workspace-test", "cycle-test", group, evidence, [], [],
    ))

    assert model_name == "deepseek-flash"
    assert status == report["analysis_status"]
    assert status == ("deferred_budget" if reservation_status == "deferred_budget" else "provider_outcome_unknown")


def test_research_report_uses_only_applied_owner_profile_and_explicit_market_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.worker import research_tasks

    class Model:
        model_name = "deepseek-flash"
        payload = None

        def generate(self, *, system_prompt, input_payload, response_model):
            self.payload = input_payload
            assert "chân dung khách hàng" in system_prompt
            return response_model(
                headline="Nghiên cứu có hồ sơ",
                summary="Tóm tắt dựa trên nguồn đã cung cấp.",
                trends=[],
                suggestions=[],
            ), SimpleNamespace(model="deepseek-flash", input_tokens=20, output_tokens=10)

    model = Model()
    profile = {
        "source": "owner_authored",
        "brand_id": "brand-1",
        "revision_id": "revision-3",
        "revision": 3,
        "profile_text": "Chúng tôi bán trà rang nhẹ cho người pha tại nhà.",
    }
    provenance = {"status": "applied", "brand_id": "brand-1", "revision_id": "revision-3", "revision": 3}

    async def active_profile(_company_id):
        return profile, provenance

    async def reserve(**_kwargs):
        return Reservation("reserved", "cycle-key")

    async def settle(**_kwargs):
        return "settled"

    monkeypatch.setattr(research_tasks, "configured_structured_model", lambda: model)
    monkeypatch.setattr(research_tasks, "_active_owner_brand_context", active_profile)
    monkeypatch.setattr(research_tasks, "reserve_automatic_request", reserve)
    monkeypatch.setattr(research_tasks, "settle_automatic_request", settle)

    group = SimpleNamespace(
        industry="Chưa xác định", region="unknown", locale="vi-VN",
        keywords_json=["  trà  ", ""],
    )
    evidence = [{"id": "evidence-1", "title": "fixture", "url": "https://example.invalid/"}]
    report, model_name, status = asyncio.run(research_tasks._make_report(
        "workspace-test", "cycle-test", group, evidence, [], [],
    ))

    assert model_name == "deepseek-flash"
    assert status == "completed"
    assert model.payload["owner_authored_brand_profile"] == profile
    assert model.payload["market_scope"] == {"locale": "vi-VN", "keywords": ["trà"]}
    assert report["business_profile_context"] == provenance
