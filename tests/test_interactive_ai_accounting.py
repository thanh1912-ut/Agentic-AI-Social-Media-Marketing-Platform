from __future__ import annotations

import asyncio

import pytest

from packages.contracts import GenerationMetadata
from services.agents.providers.errors import ProviderContextLimitError
from services.worker import interactive_ai
from services.worker.ai_budget import Reservation


def _metadata() -> GenerationMetadata:
    return GenerationMetadata(
        model="deepseek-flash",
        provider="deepseek",
        prompt_version="test",
        schema_version="TestOutput",
        input_snapshot_id="test-input",
        input_tokens=10,
        output_tokens=5,
        estimated_cost_usd=0,
        latency_ms=8,
    )


class _Model:
    provider_name = "deepseek"
    model_name = "deepseek-flash"

    def __init__(self, output: object | None = None, error: Exception | None = None) -> None:
        self.output = output or {"answer": "ok"}
        self.error = error
        self.calls = 0

    def generate(self, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.output, _metadata()


def _proxy(model: _Model, loop: asyncio.AbstractEventLoop) -> interactive_ai.InteractiveBudgetedModel:
    return interactive_ai.InteractiveBudgetedModel(
        model,
        loop=loop,
        company_id="workspace-test",
        request_key_prefix="interactive:content:job-test",
        operation="content_generation",
    )


def test_interactive_model_reserves_settles_and_returns_provider_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []
    reservation = Reservation("reserved", "request-key", ledger_id="ledger-test", reserved_micro_usd=100)

    async def reserve(**kwargs):
        calls.append(("reserve", kwargs))
        return reservation

    async def settle(**kwargs):
        calls.append(("settle", kwargs))
        return "succeeded"

    monkeypatch.setattr(interactive_ai, "reserve_interactive_request", reserve)
    monkeypatch.setattr(interactive_ai, "settle_interactive_request", settle)
    model = _Model()

    async def run():
        loop = asyncio.get_running_loop()
        proxy = _proxy(model, loop)
        result = await asyncio.to_thread(
            proxy.generate,
            system_prompt="test",
            input_payload={"prompt": "hello"},
            response_model=dict,
        )
        return result, proxy

    (output, metadata), proxy = asyncio.run(run())

    assert output == {"answer": "ok"}
    assert metadata.model == "deepseek-flash"
    assert model.calls == 1
    assert proxy.ledger_ids == ["ledger-test"]
    assert [name for name, _ in calls] == ["reserve", "settle"]
    assert calls[0][1]["request_key"] == "interactive:content:job-test:0"
    assert calls[1][1]["input_tokens"] == 10


def test_interactive_model_replays_completed_result_without_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    reservation = Reservation(
        "cached",
        "request-key",
        ledger_id="ledger-test",
        cached_result={"output": {"answer": "persisted"}, "metadata": _metadata().model_dump(mode="json")},
    )

    async def reserve(**_kwargs):
        return reservation

    monkeypatch.setattr(interactive_ai, "reserve_interactive_request", reserve)
    model = _Model()

    async def run():
        loop = asyncio.get_running_loop()
        proxy = _proxy(model, loop)
        result = await asyncio.to_thread(
            proxy.generate,
            system_prompt="test",
            input_payload={"prompt": "hello"},
            response_model=dict,
        )
        return result, proxy

    (output, metadata), proxy = asyncio.run(run())

    assert output == {"answer": "persisted"}
    assert metadata.model == "deepseek-flash"
    assert model.calls == 0
    assert proxy.ledger_ids == ["ledger-test"]


def test_interactive_model_does_not_resend_uncertain_request(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reserve(**_kwargs):
        return Reservation("uncertain", "request-key", ledger_id="ledger-test")

    monkeypatch.setattr(interactive_ai, "reserve_interactive_request", reserve)
    model = _Model()

    async def run():
        loop = asyncio.get_running_loop()
        proxy = _proxy(model, loop)
        await asyncio.to_thread(
            proxy.generate,
            system_prompt="test",
            input_payload={"prompt": "hello"},
            response_model=dict,
        )

    with pytest.raises(interactive_ai.InteractiveProviderOutcomeUnknown):
        asyncio.run(run())
    assert model.calls == 0


def test_interactive_model_distinguishes_missing_reservation_from_unknown_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reserve(**_kwargs):
        return Reservation("workspace_missing", "request-key")

    monkeypatch.setattr(interactive_ai, "reserve_interactive_request", reserve)
    model = _Model()

    async def run():
        loop = asyncio.get_running_loop()
        proxy = _proxy(model, loop)
        await asyncio.to_thread(
            proxy.generate,
            system_prompt="test",
            input_payload={"prompt": "hello"},
            response_model=dict,
        )

    with pytest.raises(interactive_ai.InteractiveReservationUnavailable):
        asyncio.run(run())
    assert model.calls == 0


def test_interactive_model_releases_reservation_for_local_context_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def reserve(**_kwargs):
        return Reservation("reserved", "request-key", ledger_id="ledger-test")

    async def release(**_kwargs):
        calls.append("release")

    monkeypatch.setattr(interactive_ai, "reserve_interactive_request", reserve)
    monkeypatch.setattr(interactive_ai, "release_interactive_request", release)
    model = _Model(error=ProviderContextLimitError("input too long"))

    async def run():
        loop = asyncio.get_running_loop()
        proxy = _proxy(model, loop)
        await asyncio.to_thread(
            proxy.generate,
            system_prompt="test",
            input_payload={"prompt": "hello"},
            response_model=dict,
        )

    with pytest.raises(ProviderContextLimitError):
        asyncio.run(run())
    assert calls == ["release"]
    assert model.calls == 1
