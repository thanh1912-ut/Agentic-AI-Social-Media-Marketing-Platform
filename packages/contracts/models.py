"""Strict Pydantic contracts owned by the AI/agent boundary.

IDs, lifecycle status and permissions are intentionally nullable/opaque here:
the backend owns their allocation and authorization.  AI code can only return
content and evidence; it cannot grant approval or publish a post.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


NonEmpty = Annotated[str, Field(min_length=1)]
EvidenceId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class SourceReference(StrictModel):
    source_id: NonEmpty
    document_id: NonEmpty
    source_version: NonEmpty
    locator: NonEmpty
    excerpt: Optional[str] = None


class TextBlock(StrictModel):
    block_id: NonEmpty
    heading: Optional[str] = None
    text: NonEmpty
    locator: NonEmpty
    extraction_warnings: list[str] = Field(default_factory=list)


class TableBlock(StrictModel):
    block_id: NonEmpty
    headers: list[NonEmpty] = Field(min_length=1)
    rows: list[list[str]] = Field(default_factory=list)
    locator: NonEmpty
    extraction_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def rows_match_headers(self) -> "TableBlock":
        width = len(self.headers)
        if any(len(row) != width for row in self.rows):
            raise ValueError("every table row must have the same width as headers")
        return self


class NormalizedDocument(StrictModel):
    """M2 -> M3 normalized-document handoff.

    The source hash is the idempotency key for indexing.  ``active`` is a
    retrieval filter and does not grant access; tenant authorization remains
    an M2/database responsibility.
    """

    company_id: NonEmpty
    brand_id: NonEmpty
    document_id: NonEmpty
    source_id: NonEmpty
    source_version: NonEmpty
    source_hash: NonEmpty
    text_blocks: list[TextBlock] = Field(default_factory=list)
    table_blocks: list[TableBlock] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)
    active: bool = True

    @model_validator(mode="after")
    def has_content(self) -> "NormalizedDocument":
        if not self.text_blocks and not self.table_blocks:
            raise ValueError("normalized document must contain text_blocks or table_blocks")
        return self


class BrandFact(StrictModel):
    key: NonEmpty
    value: NonEmpty
    status: Literal["confirmed", "unconfirmed", "inference"] = "unconfirmed"
    evidence: list[SourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def confirmed_fact_needs_evidence(self) -> "BrandFact":
        if self.status == "confirmed" and not self.evidence:
            raise ValueError("confirmed brand facts must include source evidence")
        return self


class BrandProfile(StrictModel):
    brand_id: NonEmpty
    business: NonEmpty
    products: list[NonEmpty] = Field(default_factory=list)
    audience: list[NonEmpty] = Field(default_factory=list)
    voice: list[NonEmpty] = Field(default_factory=list)
    constraints: list[NonEmpty] = Field(default_factory=list)
    facts: list[BrandFact] = Field(default_factory=list)
    unknowns: list[NonEmpty] = Field(default_factory=list)
    contradictions: list[NonEmpty] = Field(default_factory=list)
    requires_confirmation: bool = True
    profile_version: NonEmpty = "draft"


class CampaignBrief(StrictModel):
    objective: NonEmpty
    audience: NonEmpty
    channel: NonEmpty
    campaign_name: Optional[NonEmpty] = None
    offer: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    user_requirements: list[NonEmpty] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_window(self) -> "CampaignBrief":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        return self


class CampaignStrategy(StrictModel):
    objective: NonEmpty
    pillars: list[NonEmpty] = Field(min_length=1)
    angles: list[NonEmpty] = Field(min_length=1)
    formats: list[NonEmpty] = Field(min_length=1)
    ctas: list[NonEmpty] = Field(min_length=1)
    hypothesis: NonEmpty
    suggested_schedule: list[NonEmpty] = Field(default_factory=list)
    assumptions: list[NonEmpty] = Field(default_factory=list)
    supporting_evidence: list[SourceReference] = Field(default_factory=list)


class GenerationMetadata(StrictModel):
    model: NonEmpty
    provider: NonEmpty
    prompt_version: NonEmpty
    schema_version: NonEmpty
    input_snapshot_id: NonEmpty
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)


class GeneratedPost(StrictModel):
    base_version: NonEmpty
    version: int = Field(ge=1)
    channel: NonEmpty
    caption: NonEmpty
    hook: Optional[NonEmpty] = None
    cta: Optional[NonEmpty] = None
    hashtags: list[NonEmpty] = Field(default_factory=list)
    image_brief: Optional[str] = None
    citations: list[SourceReference] = Field(default_factory=list)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    metadata: Optional[GenerationMetadata] = None

    @model_validator(mode="after")
    def evidence_must_be_cited(self) -> "GeneratedPost":
        citation_ids = {reference.source_id for reference in self.citations}
        missing = [evidence_id for evidence_id in self.evidence_ids if evidence_id not in citation_ids]
        if missing:
            raise ValueError(f"evidence_ids must resolve to citations: {missing}")
        return self


class ContentIssue(StrictModel):
    code: NonEmpty
    severity: Literal["warning", "blocking"]
    message: NonEmpty
    evidence: list[SourceReference] = Field(default_factory=list)
    field: Optional[str] = None


class ContentReview(StrictModel):
    post_version: NonEmpty
    score: float = Field(ge=0, le=5)
    issues: list[ContentIssue] = Field(default_factory=list)
    checked_requirements: list[NonEmpty] = Field(default_factory=list)
    human_approval_required: bool = True


class MetricObservation(StrictModel):
    metric: NonEmpty
    value: Optional[float] = None
    numerator: Optional[float] = None
    denominator: Optional[float] = None
    sample_size: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    measured_from: datetime
    measured_to: datetime
    unavailable_reason: Optional[str] = None

    @model_validator(mode="after")
    def unavailable_is_explicit(self) -> "MetricObservation":
        if self.value is None and not self.unavailable_reason:
            raise ValueError("missing metric values must include unavailable_reason")
        if self.value is not None and self.unavailable_reason:
            raise ValueError("available metric values cannot include unavailable_reason")
        if self.measured_to < self.measured_from:
            raise ValueError("measured_to cannot be earlier than measured_from")
        return self


class AnalyticsEvidence(StrictModel):
    evidence_id: EvidenceId
    description: NonEmpty
    post_ids: list[NonEmpty] = Field(default_factory=list)
    metric_names: list[NonEmpty] = Field(default_factory=list)


class AnalyticsReport(StrictModel):
    report_id: NonEmpty
    page_id: NonEmpty
    period_start: datetime
    period_end: datetime
    observations: list[MetricObservation] = Field(default_factory=list)
    evidence: list[AnalyticsEvidence] = Field(default_factory=list)
    notes: list[NonEmpty] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_period(self) -> "AnalyticsReport":
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot be earlier than period_start")
        return self


class AnalyticsInsight(StrictModel):
    observation: NonEmpty
    interpretation: NonEmpty
    limitations: list[NonEmpty] = Field(min_length=1)
    evidence_ids: list[EvidenceId] = Field(min_length=1)
    insufficient_data: bool = False


class Experiment(StrictModel):
    name: NonEmpty
    hypothesis: NonEmpty
    action: NonEmpty
    metric: NonEmpty
    threshold: NonEmpty
    duration_days: int = Field(gt=0)


class Recommendation(StrictModel):
    observation: NonEmpty
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    hypothesis: NonEmpty
    action: NonEmpty
    expected_impact: NonEmpty
    experiment: Experiment
    metric: NonEmpty
    threshold: NonEmpty
    confidence: float = Field(ge=0, le=1)
    status: Literal["proposed", "accepted", "rejected", "applied"] = "proposed"
    created_at: datetime

    @model_validator(mode="after")
    def evidence_required_unless_abstaining(self) -> "Recommendation":
        if self.confidence > 0 and not self.evidence_ids:
            raise ValueError("a non-abstaining recommendation must reference evidence_ids")
        return self


__all__ = [name for name in globals() if not name.startswith("_")]
