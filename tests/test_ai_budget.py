from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from services.worker.ai_budget import (
    PricingUnavailable,
    Reservation,
    cost_micro_usd,
    price_for,
    reserve_upper_bound_micro_usd,
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
    group = SimpleNamespace(industry="", region="", locale="vi-VN", keywords_json=[])
    evidence = [{"id": "evidence-1", "title": "fixture", "url": "https://example.invalid/"}]
    report, model_name, status = asyncio.run(research_tasks._make_report(
        "workspace-test", "cycle-test", group, evidence, [], [],
    ))

    assert model_name == "deepseek-flash"
    assert status == report["analysis_status"]
    assert status == ("deferred_budget" if reservation_status == "deferred_budget" else "provider_outcome_unknown")
