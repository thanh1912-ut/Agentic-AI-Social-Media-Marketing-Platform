"""Account for user-triggered provider calls outside the automatic AI cap."""

from __future__ import annotations

import asyncio
from typing import Any

from packages.contracts import GenerationMetadata
from services.agents.providers.errors import ProviderContextLimitError, ProviderError
from services.worker.ai_budget import (
    mark_interactive_request_unknown,
    release_interactive_request,
    reserve_interactive_request,
    settle_interactive_request,
)


class InteractiveProviderOutcomeUnknown(ProviderError):
    """A prior interactive call may have been accepted; never send it twice."""


class InteractiveReservationUnavailable(ProviderError):
    """No safe usage reservation exists, so the provider was not called."""


class InteractiveBudgetedModel:
    """Sync StructuredModel proxy that reserves and records each user call.

    Content agents are synchronous today, while budget/database operations are
    async. The model is invoked from a worker thread and schedules those DB
    operations back onto the durable job's live event loop.
    """

    def __init__(
        self,
        model: Any,
        *,
        loop: asyncio.AbstractEventLoop,
        company_id: str,
        request_key_prefix: str,
        operation: str,
    ) -> None:
        self._model = model
        self._loop = loop
        self._company_id = company_id
        self._request_key_prefix = request_key_prefix
        self._operation = operation
        self._calls = 0
        self.ledger_ids: list[str] = []
        self.provider_name = str(getattr(model, "provider_name", "deepseek"))
        self.model_name = str(getattr(model, "model_name", ""))

    def _await(self, coroutine):
        if not self._loop.is_running():
            coroutine.close()
            raise RuntimeError("interactive model accounting loop is not running")
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    def generate(self, *, system_prompt: str, input_payload: dict, response_model: type):
        index = self._calls
        self._calls += 1
        request_key = f"{self._request_key_prefix}:{index}"
        reservation = self._await(reserve_interactive_request(
            company_id=self._company_id,
            request_key=request_key,
            provider=self.provider_name,
            model=self.model_name,
            operation=self._operation,
        ))
        if reservation.status == "cached" and reservation.cached_result is not None:
            cached = reservation.cached_result
            self.ledger_ids.append(reservation.ledger_id or "")
            metadata = cached.get("metadata")
            return cached.get("output"), GenerationMetadata.model_validate(metadata) if metadata else None
        if reservation.status in {"uncertain", "cached_unknown"}:
            raise InteractiveProviderOutcomeUnknown(
                "A previous request may already have been sent; create a new request instead of resending it."
            )
        if reservation.status != "reserved":
            raise InteractiveReservationUnavailable(
                f"Interactive AI usage reservation was not created ({reservation.status})."
            )

        try:
            output, metadata = self._model.generate(
                system_prompt=system_prompt,
                input_payload=input_payload,
                response_model=response_model,
            )
        except ProviderContextLimitError:
            self._await(release_interactive_request(
                company_id=self._company_id, reservation=reservation,
            ))
            raise
        except Exception:
            self._await(mark_interactive_request_unknown(
                company_id=self._company_id,
                reservation=reservation,
                error_code="provider_call_outcome_unknown",
            ))
            raise

        output_payload = output.model_dump(mode="json") if hasattr(output, "model_dump") else output
        if not isinstance(output_payload, dict):
            self._await(mark_interactive_request_unknown(
                company_id=self._company_id,
                reservation=reservation,
                error_code="provider_output_unserializable",
            ))
            raise ProviderError("The provider response could not be safely recorded")
        metadata_payload = _metadata_payload(metadata)
        settlement = self._await(settle_interactive_request(
            company_id=self._company_id,
            reservation=reservation,
            provider=str(metadata_payload.get("provider") or self.provider_name),
            model=str(metadata_payload.get("model") or self.model_name),
            input_tokens=metadata_payload.get("input_tokens"),
            output_tokens=metadata_payload.get("output_tokens"),
            result_json={"output": output_payload, "metadata": metadata_payload},
        ))
        if settlement == "missing":
            raise ProviderError("The provider response could not be linked to its usage record")
        self.ledger_ids.append(reservation.ledger_id or "")
        return output, metadata


def _metadata_payload(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if hasattr(metadata, "model_dump"):
        value = metadata.model_dump(mode="json")
        return value if isinstance(value, dict) else {}
    return {
        key: getattr(metadata, key)
        for key in ("provider", "model", "input_tokens", "output_tokens", "latency_ms", "estimated_cost_usd")
        if getattr(metadata, key, None) is not None
    }
