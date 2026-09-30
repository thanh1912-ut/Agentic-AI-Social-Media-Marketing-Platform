"""PostgreSQL-backed, idempotent budget reservations for automated AI calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_CEILING
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from services.api.config import settings


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PRICE_TABLE_VERSION = "provider-public-pricing-2026-09-30-v2"
MAX_AUTO_DAILY_BUDGET_MICRO_USD = 2_000_000


@dataclass(frozen=True)
class ProviderPrice:
    input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal
    basis: str
    valid_through: date | None = None


@dataclass(frozen=True)
class Reservation:
    status: str
    request_key: str
    ledger_id: str | None = None
    reserved_micro_usd: int = 0
    cached_result: dict | None = None


class PricingUnavailable(ValueError):
    pass


def price_for(
    provider: str, model: str, *, region: str | None = None, on_date: date | None = None,
) -> ProviderPrice:
    """Return only reviewed public rates; unknown IDs/regions fail closed.

    Gemini's published Gemini 3.8 Flash price is promotional through the end
    of 2026, so it must stop being used automatically after that date until the
    rate table is reviewed again. Qwen's price is tied to the Singapore
    International deployment; other Model Studio regions have different rates.
    """

    prices: dict[tuple[str, str], ProviderPrice] = {
        ("deepseek", "deepseek-flash"): ProviderPrice(
            Decimal("0.30"), Decimal("1.20"), "peak_cache_miss"
        ),
        ("deepseek", "deepseek-v4-pro"): ProviderPrice(
            Decimal("1.32"), Decimal("3.96"), "peak_cache_miss"
        ),
        ("gemini", "gemini-3.8-flash"): ProviderPrice(
            Decimal("0.75"), Decimal("3.75"), "standard_intro_price_through_2026_12_31",
            valid_through=date(2026, 12, 31),
        ),
        ("qwen", "qwen3.8-27b"): ProviderPrice(
            Decimal("0.5"), Decimal("3"), "singapore_international_list_price",
        ),
    }
    try:
        price = prices[(provider, model)]
    except KeyError as error:
        raise PricingUnavailable("pricing_unavailable") from error
    if provider == "qwen" and (region or "").strip().casefold() != "singapore":
        raise PricingUnavailable("pricing_region_unverified")
    if price.valid_through is not None and (on_date or datetime.now(VN_TZ).date()) > price.valid_through:
        raise PricingUnavailable("pricing_expired")
    return price


def cost_micro_usd(price: ProviderPrice, input_tokens: int, output_tokens: int) -> int:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    value = (
        Decimal(input_tokens) * price.input_usd_per_million_tokens
        + Decimal(output_tokens) * price.output_usd_per_million_tokens
    )
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def reserve_upper_bound_micro_usd(price: ProviderPrice, *, max_input_chars: int, max_output_tokens: int) -> int:
    """Bound both initial + one repair call using UTF-8 bytes as token upper bound.

    The adapter permits at most 2*max_input_chars in its first structured
    request and one repair that adds at most 12k characters plus bounded
    instructions. A Unicode code point occupies at most four UTF-8 bytes.
    """

    total_chars = (4 * max_input_chars) + 13_000
    input_tokens = (4 * total_chars) + 2_000  # message framing allowance
    output_tokens = 2 * max_output_tokens
    return cost_micro_usd(price, input_tokens, output_tokens)


def reserve_token_bound_micro_usd(
    price: ProviderPrice, *, max_input_tokens: int, max_output_tokens: int, max_attempts: int = 1,
) -> int:
    """Reserve an explicit provider-token upper bound before an automated call.

    Callers handling media must get a conservative input-token bound for the
    exact bytes before invoking a provider; character count is not a safe proxy
    for image/video token billing.
    """

    if max_input_tokens < 1 or max_output_tokens < 1 or max_attempts < 1:
        raise ValueError("token bounds and attempt count must be positive")
    return cost_micro_usd(
        price,
        input_tokens=max_input_tokens * max_attempts,
        output_tokens=max_output_tokens * max_attempts,
    )


def _budget_date(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(VN_TZ).date()


async def reserve_automatic_request(
    *, company_id: str, request_key: str, provider: str, model: str, operation: str,
    region: str | None = None, max_input_tokens: int | None = None,
    max_output_tokens: int | None = None, max_attempts: int = 1,
) -> Reservation:
    price = price_for(provider, model, region=region)
    if max_input_tokens is not None or max_output_tokens is not None:
        if max_input_tokens is None or max_output_tokens is None:
            raise PricingUnavailable("pricing_reservation_bounds_unavailable")
        amount = reserve_token_bound_micro_usd(
            price, max_input_tokens=max_input_tokens, max_output_tokens=max_output_tokens,
            max_attempts=max_attempts,
        )
    elif provider == "deepseek":
        amount = reserve_upper_bound_micro_usd(
            price, max_input_chars=settings.llm_max_input_chars, max_output_tokens=settings.llm_max_tokens,
        )
    else:
        # In particular, media tokens cannot be safely bounded from the
        # existing text-only limits. No provider call occurs without bounds.
        raise PricingUnavailable("pricing_reservation_bounds_unavailable")
    from database.models import AIUsageBudgetDay, AIUsageLedger, Company, new_id
    from services.api.db import SessionLocal

    budget_date = _budget_date()
    daily_limit = min(settings.auto_ai_daily_budget_micro_usd, MAX_AUTO_DAILY_BUDGET_MICRO_USD)
    async with SessionLocal() as db:
        company = await db.scalar(select(Company.id).where(Company.id == company_id).with_for_update())
        if company is None:
            return Reservation("workspace_missing", request_key)

        existing = await db.scalar(select(AIUsageLedger).where(
            AIUsageLedger.company_id == company_id,
            AIUsageLedger.request_key == request_key,
        ).with_for_update())
        if existing is not None:
            if existing.status in {"succeeded", "overrun"} and existing.result_json is not None:
                return Reservation("cached", request_key, existing.id, existing.reserved_micro_usd, existing.result_json)
            if existing.status == "unknown" and existing.result_json is not None:
                return Reservation("cached_unknown", request_key, existing.id, existing.reserved_micro_usd, existing.result_json)
            if existing.status != "released":
                return Reservation("uncertain", request_key, existing.id, existing.reserved_micro_usd)

        await db.execute(pg_insert(AIUsageBudgetDay).values(
            company_id=company_id,
            budget_date=budget_date,
            limit_micro_usd=daily_limit,
            reserved_micro_usd=0,
            spent_micro_usd=0,
            updated_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing(index_elements=["company_id", "budget_date"]))
        day = await db.scalar(select(AIUsageBudgetDay).where(
            AIUsageBudgetDay.company_id == company_id,
            AIUsageBudgetDay.budget_date == budget_date,
        ).with_for_update())
        assert day is not None
        # A runtime lowering applies immediately; raising a limit does not
        # retroactively increase today's allowance.
        day.limit_micro_usd = min(day.limit_micro_usd, daily_limit)
        if day.spent_micro_usd + day.reserved_micro_usd + amount > day.limit_micro_usd:
            await db.commit()
            return Reservation("deferred_budget", request_key)

        if existing is None:
            existing = AIUsageLedger(
                id=new_id(), company_id=company_id, request_key=request_key,
                provider=provider, model=model, operation=operation,
                budget_class="automatic", budget_date=budget_date,
                pricing_version=PRICE_TABLE_VERSION, cost_basis=price.basis,
                reserved_micro_usd=amount, status="reserved",
            )
            db.add(existing)
        else:
            existing.provider = provider
            existing.model = model
            existing.operation = operation
            existing.budget_date = budget_date
            existing.pricing_version = PRICE_TABLE_VERSION
            existing.cost_basis = price.basis
            existing.reserved_micro_usd = amount
            existing.actual_micro_usd = None
            existing.input_tokens = None
            existing.output_tokens = None
            existing.result_json = None
            existing.unknown_at = None
            existing.error_code = None
            existing.status = "reserved"
        day.reserved_micro_usd += amount
        day.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return Reservation("reserved", request_key, existing.id, amount)


async def reserve_interactive_request(
    *, company_id: str, request_key: str, provider: str, model: str, operation: str,
    region: str | None = None, max_input_tokens: int | None = None,
    max_output_tokens: int | None = None, max_attempts: int = 1,
) -> Reservation:
    """Record a user-triggered call separately; it does not consume auto budget.

    The row is committed before the provider request. A retry of the same job
    can replay a completed result, but never resends a request whose outcome is
    still uncertain.
    """

    price = price_for(provider, model, region=region)
    if max_input_tokens is not None or max_output_tokens is not None:
        if max_input_tokens is None or max_output_tokens is None:
            raise PricingUnavailable("pricing_reservation_bounds_unavailable")
        amount = reserve_token_bound_micro_usd(
            price, max_input_tokens=max_input_tokens, max_output_tokens=max_output_tokens,
            max_attempts=max_attempts,
        )
    elif provider == "deepseek":
        amount = reserve_upper_bound_micro_usd(
            price, max_input_chars=settings.llm_max_input_chars,
            max_output_tokens=settings.llm_max_tokens,
        )
    else:
        raise PricingUnavailable("pricing_reservation_bounds_unavailable")

    from database.models import AIUsageLedger, Company, new_id
    from services.api.db import SessionLocal

    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        company = await db.scalar(select(Company.id).where(Company.id == company_id).with_for_update())
        if company is None:
            return Reservation("workspace_missing", request_key)
        existing = await db.scalar(select(AIUsageLedger).where(
            AIUsageLedger.company_id == company_id,
            AIUsageLedger.request_key == request_key,
        ).with_for_update())
        if existing is not None:
            if existing.status in {"succeeded", "overrun", "usage_unavailable"} and existing.result_json is not None:
                return Reservation("cached", request_key, existing.id, existing.reserved_micro_usd, existing.result_json)
            if existing.status == "unknown" and existing.result_json is not None:
                return Reservation("cached_unknown", request_key, existing.id, existing.reserved_micro_usd, existing.result_json)
            if existing.status != "released":
                return Reservation("uncertain", request_key, existing.id, existing.reserved_micro_usd)

        if existing is None:
            existing = AIUsageLedger(
                id=new_id(), company_id=company_id, request_key=request_key,
                provider=provider, model=model, operation=operation,
                budget_class="interactive", budget_date=_budget_date(now),
                pricing_version=PRICE_TABLE_VERSION, cost_basis=price.basis,
                reserved_micro_usd=amount, status="reserved",
            )
            db.add(existing)
        else:
            existing.provider = provider
            existing.model = model
            existing.operation = operation
            existing.budget_class = "interactive"
            existing.budget_date = _budget_date(now)
            existing.pricing_version = PRICE_TABLE_VERSION
            existing.cost_basis = price.basis
            existing.reserved_micro_usd = amount
            existing.actual_micro_usd = None
            existing.input_tokens = None
            existing.output_tokens = None
            existing.result_json = None
            existing.unknown_at = None
            existing.error_code = None
            existing.status = "reserved"
        await db.commit()
        return Reservation("reserved", request_key, existing.id, amount)


async def settle_automatic_request(
    *, company_id: str, reservation: Reservation, provider: str, model: str,
    input_tokens: int | None, output_tokens: int | None, result_json: dict,
    region: str | None = None,
) -> str:
    """Settle verified usage and preserve the structured result for replay."""

    from database.models import AIUsageBudgetDay, AIUsageLedger
    from services.api.db import SessionLocal

    if not reservation.ledger_id:
        return "missing"
    try:
        price = price_for(provider, model, region=region)
    except PricingUnavailable:
        await mark_automatic_request_unknown(
            company_id=company_id, reservation=reservation, error_code="pricing_unavailable_for_actual_model",
            result_json=result_json,
        )
        return "unknown"
    if input_tokens is None or output_tokens is None or input_tokens <= 0 or output_tokens < 0:
        await mark_automatic_request_unknown(
            company_id=company_id, reservation=reservation, error_code="provider_usage_missing",
            result_json=result_json,
        )
        return "unknown"
    actual = cost_micro_usd(price, input_tokens, output_tokens)
    async with SessionLocal() as db:
        row = await db.scalar(select(AIUsageLedger).where(
            AIUsageLedger.id == reservation.ledger_id,
            AIUsageLedger.company_id == company_id,
        ).with_for_update())
        if row is None or row.status != "reserved":
            return "missing"
        day = await db.scalar(select(AIUsageBudgetDay).where(
            AIUsageBudgetDay.company_id == company_id,
            AIUsageBudgetDay.budget_date == row.budget_date,
        ).with_for_update())
        if day is None:
            row.status = "unknown"
            row.error_code = "budget_day_missing"
            row.unknown_at = datetime.now(timezone.utc)
            await db.commit()
            return "unknown"
        day.reserved_micro_usd = max(0, day.reserved_micro_usd - row.reserved_micro_usd)
        day.spent_micro_usd += actual
        day.updated_at = datetime.now(timezone.utc)
        row.actual_micro_usd = actual
        row.input_tokens = input_tokens
        row.output_tokens = output_tokens
        row.result_json = result_json
        row.status = "succeeded" if actual <= row.reserved_micro_usd else "overrun"
        row.error_code = "reservation_underestimated" if actual > row.reserved_micro_usd else None
        await db.commit()
        return row.status


async def settle_interactive_request(
    *, company_id: str, reservation: Reservation, provider: str, model: str,
    input_tokens: int | None, output_tokens: int | None, result_json: dict,
    region: str | None = None,
) -> str:
    """Store successful interactive-call usage without altering auto budget counters."""

    from database.models import AIUsageLedger
    from services.api.db import SessionLocal

    if not reservation.ledger_id:
        return "missing"
    try:
        price = price_for(provider, model, region=region)
    except PricingUnavailable:
        price = None
    usage_valid = (
        input_tokens is not None and output_tokens is not None
        and input_tokens > 0 and output_tokens >= 0
    )
    actual = cost_micro_usd(price, input_tokens, output_tokens) if price and usage_valid else None
    async with SessionLocal() as db:
        row = await db.scalar(select(AIUsageLedger).where(
            AIUsageLedger.id == reservation.ledger_id,
            AIUsageLedger.company_id == company_id,
            AIUsageLedger.budget_class == "interactive",
        ).with_for_update())
        if row is None or row.status != "reserved":
            return "missing"
        row.actual_micro_usd = actual
        row.input_tokens = input_tokens if input_tokens is not None and input_tokens >= 0 else None
        row.output_tokens = output_tokens if output_tokens is not None and output_tokens >= 0 else None
        row.result_json = result_json
        if actual is None:
            row.status = "usage_unavailable"
            row.error_code = "provider_usage_or_pricing_unavailable"
        else:
            row.status = "succeeded" if actual <= row.reserved_micro_usd else "overrun"
            row.error_code = "reservation_underestimated" if actual > row.reserved_micro_usd else None
        await db.commit()
        return row.status


async def release_interactive_request(*, company_id: str, reservation: Reservation) -> None:
    """Release a user-call reservation only when no provider request was sent."""

    from database.models import AIUsageLedger
    from services.api.db import SessionLocal

    if not reservation.ledger_id:
        return
    async with SessionLocal() as db:
        row = await db.scalar(select(AIUsageLedger).where(
            AIUsageLedger.id == reservation.ledger_id,
            AIUsageLedger.company_id == company_id,
            AIUsageLedger.budget_class == "interactive",
        ).with_for_update())
        if row is not None and row.status == "reserved":
            row.status = "released"
            row.reserved_micro_usd = 0
            row.error_code = None
            await db.commit()


async def mark_automatic_request_unknown(
    *, company_id: str, reservation: Reservation, error_code: str,
    result_json: dict | None = None,
) -> None:
    """Keep the reservation when provider acceptance/charge is uncertain."""

    await _mark_request_unknown(
        company_id=company_id, reservation=reservation,
        error_code=error_code, result_json=result_json,
    )


async def mark_interactive_request_unknown(
    *, company_id: str, reservation: Reservation, error_code: str,
    result_json: dict | None = None,
) -> None:
    """Keep a user-triggered reservation when provider acceptance is uncertain."""

    await _mark_request_unknown(
        company_id=company_id, reservation=reservation,
        error_code=error_code, result_json=result_json,
    )


async def _mark_request_unknown(
    *, company_id: str, reservation: Reservation, error_code: str,
    result_json: dict | None = None,
) -> None:
    """Shared fail-closed state transition for both ledger classes."""

    from database.models import AIUsageLedger
    from services.api.db import SessionLocal

    if not reservation.ledger_id:
        return
    async with SessionLocal() as db:
        row = await db.scalar(select(AIUsageLedger).where(
            AIUsageLedger.id == reservation.ledger_id,
            AIUsageLedger.company_id == company_id,
        ).with_for_update())
        if row is not None and row.status == "reserved":
            row.status = "unknown"
            row.unknown_at = datetime.now(timezone.utc)
            row.error_code = error_code[:80]
            if result_json is not None:
                row.result_json = result_json
            await db.commit()


async def release_unsubmitted_request(*, company_id: str, reservation: Reservation) -> None:
    """Release only when the adapter proves no provider request was sent."""

    from database.models import AIUsageBudgetDay, AIUsageLedger
    from services.api.db import SessionLocal

    if not reservation.ledger_id:
        return
    async with SessionLocal() as db:
        row = await db.scalar(select(AIUsageLedger).where(
            AIUsageLedger.id == reservation.ledger_id,
            AIUsageLedger.company_id == company_id,
        ).with_for_update())
        if row is None or row.status != "reserved":
            return
        day = await db.scalar(select(AIUsageBudgetDay).where(
            AIUsageBudgetDay.company_id == company_id,
            AIUsageBudgetDay.budget_date == row.budget_date,
        ).with_for_update())
        if day is not None:
            day.reserved_micro_usd = max(0, day.reserved_micro_usd - row.reserved_micro_usd)
            day.updated_at = datetime.now(timezone.utc)
        row.status = "released"
        row.reserved_micro_usd = 0
        row.error_code = None
        await db.commit()
