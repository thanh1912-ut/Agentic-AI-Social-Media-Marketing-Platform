"""Backend-facing callable result for one Brand Profile generation run."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from packages.contracts import BrandProfile, GenerationMetadata, SourceReference
from services.agents.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderContextLimitError,
    ProviderError,
    ProviderModelNotFoundError,
    ProviderOutputError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)

from .handler import BrandAgent, InvalidSourceReferenceError

FailureCode = Literal[
    "no_relevant_context",
    "provider_not_configured",
    "provider_authentication_failed",
    "provider_model_not_found",
    "provider_rate_limited",
    "provider_timeout",
    "context_limit_exceeded",
    "provider_request_failed",
    "invalid_structured_output",
    "invalid_source_reference",
]


@dataclass(frozen=True)
class BrandProfileFailure:
    code: FailureCode
    message: str
    retryable: bool


@dataclass(frozen=True)
class BrandProfileHandlerResult:
    status: Literal["succeeded", "insufficient_evidence", "failed"]
    company_id: str
    brand_id: str
    document_ids: tuple[str, ...]
    job_id: str
    run_id: str
    input_snapshot_id: str
    profile: BrandProfile | None
    source_references: tuple[SourceReference, ...]
    missing_information: tuple[str, ...]
    contradictions: tuple[str, ...]
    generation: GenerationMetadata | None
    repair_attempts: int
    estimated_cost_available: bool
    error: BrandProfileFailure | None = None

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-ready value for M2 persistence and job reporting."""

        generation = self.generation.model_dump(mode="json") if self.generation else None
        if generation is not None and not self.estimated_cost_available:
            # GenerationMetadata currently requires float. Do not serialize its
            # internal zero sentinel as a measured/estimated zero cost.
            generation["estimated_cost_usd"] = None
        return {
            "status": self.status,
            "company_id": self.company_id,
            "brand_id": self.brand_id,
            "document_ids": list(self.document_ids),
            "job_id": self.job_id,
            "run_id": self.run_id,
            "input_snapshot_id": self.input_snapshot_id,
            "profile": self.profile.model_dump(mode="json") if self.profile else None,
            "source_references": [item.model_dump(mode="json") for item in self.source_references],
            "missing_information": list(self.missing_information),
            "contradictions": list(self.contradictions),
            "generation": generation,
            "repair_attempts": self.repair_attempts,
            "estimated_cost_available": self.estimated_cost_available,
            "error": None
            if self.error is None
            else {
                "code": self.error.code,
                "message": self.error.message,
                "retryable": self.error.retryable,
            },
        }


def run_brand_profile_handler(
    *,
    agent: BrandAgent,
    company_id: str,
    brand_id: str,
    document_ids: Sequence[str],
    job_id: str,
    run_id: str,
    input_snapshot_id: str,
    business_hint: str,
    context: Sequence[Mapping[str, str]],
    repair=None,
) -> BrandProfileHandlerResult:
    """Generate a draft profile from M2-authorized, active-source context.

    M2 owns authorization and must perform tenant/brand/source filters before
    calling this function. The handler never allocates IDs or confirms a draft.
    """

    ids = (company_id, brand_id, job_id, run_id, input_snapshot_id)
    if any(not item.strip() for item in ids):
        raise ValueError("company, brand, job, run, and snapshot IDs are required")
    resolved_documents = tuple(dict.fromkeys(document_ids))
    required_source_fields = {
        "source_id",
        "document_id",
        "source_version",
        "source_hash",
        "locator",
        "text",
    }
    if context and any(
        any(not item.get(field) for field in required_source_fields)
        for item in context
    ):
        return BrandProfileHandlerResult(
            status="failed",
            company_id=company_id,
            brand_id=brand_id,
            document_ids=resolved_documents,
            job_id=job_id,
            run_id=run_id,
            input_snapshot_id=input_snapshot_id,
            profile=None,
            source_references=(),
            missing_information=(),
            contradictions=(),
            generation=None,
            repair_attempts=0,
            estimated_cost_available=False,
            error=BrandProfileFailure(
                "invalid_source_reference",
                "Retrieved source context is missing stable identity or locator fields.",
                False,
            ),
        )
    if any(
        (item.get("company_id") is not None and item["company_id"] != company_id)
        or (item.get("brand_id") is not None and item["brand_id"] != brand_id)
        for item in context
    ):
        return BrandProfileHandlerResult(
            status="failed",
            company_id=company_id,
            brand_id=brand_id,
            document_ids=resolved_documents,
            job_id=job_id,
            run_id=run_id,
            input_snapshot_id=input_snapshot_id,
            profile=None,
            source_references=(),
            missing_information=(),
            contradictions=(),
            generation=None,
            repair_attempts=0,
            estimated_cost_available=False,
            error=BrandProfileFailure(
                "invalid_source_reference",
                "Retrieved source context is outside the requested tenant or brand.",
                False,
            ),
        )
    if not context:
        return BrandProfileHandlerResult(
            status="insufficient_evidence",
            company_id=company_id,
            brand_id=brand_id,
            document_ids=resolved_documents,
            job_id=job_id,
            run_id=run_id,
            input_snapshot_id=input_snapshot_id,
            profile=None,
            source_references=(),
            missing_information=("Không tìm thấy ngữ cảnh liên quan trong nguồn đang hoạt động.",),
            contradictions=(),
            generation=None,
            repair_attempts=0,
            estimated_cost_available=False,
            error=BrandProfileFailure(
                "no_relevant_context",
                "No relevant active-source context was retrieved.",
                False,
            ),
        )

    repair_attempts = 0
    tracked_repair = repair
    if repair is not None:
        def tracked_repair(payload, validation_error):
            nonlocal repair_attempts
            repair_attempts += 1
            return repair(payload, validation_error)

    try:
        profile, metadata, repairs = agent.extract(
            brand_id=brand_id,
            business_hint=business_hint,
            context=context,
            repair=tracked_repair,
            input_snapshot_id=input_snapshot_id,
        )
    except ProviderConfigurationError:
        failure = BrandProfileFailure(
            "provider_not_configured", "The model provider is not configured.", False
        )
    except ProviderTimeoutError:
        failure = BrandProfileFailure(
            "provider_timeout", "The model request timed out.", True
        )
    except ProviderAuthenticationError:
        failure = BrandProfileFailure(
            "provider_authentication_failed", "The model provider rejected its credentials.", False
        )
    except ProviderModelNotFoundError:
        failure = BrandProfileFailure(
            "provider_model_not_found", "The configured model is unavailable to the provider account.", False
        )
    except ProviderRateLimitError:
        failure = BrandProfileFailure(
            "provider_rate_limited", "The model provider rate limit was reached.", True
        )
    except ProviderContextLimitError:
        failure = BrandProfileFailure(
            "context_limit_exceeded", "The retrieved model input exceeded its configured size limit.", False
        )
    except ProviderOutputError:
        failure = BrandProfileFailure(
            "invalid_structured_output", "The model returned invalid structured output.", False
        )
    except InvalidSourceReferenceError:
        failure = BrandProfileFailure(
            "invalid_source_reference", "The model cited evidence outside its retrieved context.", False
        )
    except ValidationError:
        failure = BrandProfileFailure(
            "invalid_structured_output", "The model returned invalid structured output.", False
        )
    except ProviderError as error:
        failure = BrandProfileFailure(
            "provider_request_failed", "The configured model request failed.", error.retryable
        )
    except ValueError:
        failure = BrandProfileFailure(
            "invalid_structured_output", "The model returned an invalid profile result.", False
        )
    except Exception:
        failure = BrandProfileFailure(
            "provider_request_failed", "The configured model request failed.", True
        )
    else:
        refs = tuple(
            reference
            for fact in profile.facts
            for reference in fact.evidence
        )
        return BrandProfileHandlerResult(
            status="succeeded",
            company_id=company_id,
            brand_id=brand_id,
            document_ids=resolved_documents,
            job_id=job_id,
            run_id=run_id,
            input_snapshot_id=input_snapshot_id,
            profile=profile,
            source_references=refs,
            missing_information=tuple(profile.unknowns),
            contradictions=tuple(profile.contradictions),
            generation=metadata,
            repair_attempts=repairs,
            estimated_cost_available=bool(
                getattr(agent.model, "cost_estimate_available", False)
            ),
        )

    repair_attempts = max(
        repair_attempts,
        int(getattr(agent.model, "last_repair_attempts", 0) or 0),
    )
    return BrandProfileHandlerResult(
        status="failed",
        company_id=company_id,
        brand_id=brand_id,
        document_ids=resolved_documents,
        job_id=job_id,
        run_id=run_id,
        input_snapshot_id=input_snapshot_id,
        profile=None,
        source_references=(),
        missing_information=(),
        contradictions=(),
        generation=None,
        repair_attempts=repair_attempts,
        estimated_cost_available=False,
        error=failure,
    )
