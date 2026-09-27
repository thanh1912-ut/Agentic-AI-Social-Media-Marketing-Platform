"""HTTP contracts for the MailGuard pilot additions."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .campaign_schemas import CampaignBriefIn, ContentPillarValue


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CampaignPlanRequest(StrictModel):
    prompt: str = Field(min_length=8, max_length=4000)
    group_id: str | None = Field(default=None, max_length=36)


class CampaignPlanConcept(StrictModel):
    id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=180)
    angle: str = Field(min_length=1, max_length=1000)
    hook: str = Field(min_length=1, max_length=500)
    format: Literal["text", "image"]
    cta: str = Field(min_length=1, max_length=500)
    hashtags: list[str] = Field(default_factory=list, max_length=12)


class CampaignPlanProposal(StrictModel):
    campaign_name: str = Field(min_length=1, max_length=200)
    objective: Literal["awareness", "engagement", "traffic", "leads", "sales", "retention"]
    topic: str = Field(min_length=1, max_length=500)
    tone: str = Field(min_length=1, max_length=300)
    audience: list[str] = Field(min_length=1, max_length=12)
    key_message: str = Field(min_length=1, max_length=1000)
    must_include: list[str] = Field(default_factory=list, max_length=15)
    must_avoid: list[str] = Field(default_factory=list, max_length=15)
    start_date: date
    end_date: date
    pillars: list[ContentPillarValue] = Field(min_length=1, max_length=4)
    concepts: list[CampaignPlanConcept] = Field(min_length=3, max_length=3)
    assumptions: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def valid_dates_and_concepts(self) -> "CampaignPlanProposal":
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        if len({concept.id for concept in self.concepts}) != 3:
            raise ValueError("concept IDs must be unique")
        return self


class CampaignPlanJobResult(StrictModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    proposal: CampaignPlanProposal | None = None
    error: dict[str, Any] | None = None


class ContentReviewRequest(StrictModel):
    version: int = Field(ge=1)


class ContentSemanticFinding(StrictModel):
    category: Literal["unsupported_claim", "brand_voice", "unsafe_cta", "defamation", "other"]
    concern: str = Field(min_length=1, max_length=500)
    quoted_text: str = Field(default="", max_length=300)


class ContentSemanticReview(StrictModel):
    brand_voice: Literal["aligned", "needs_attention", "uncertain"]
    summary: str = Field(min_length=1, max_length=800)
    findings: list[ContentSemanticFinding] = Field(default_factory=list, max_length=12)


class ContentReviewCheck(StrictModel):
    key: str
    label: str
    status: Literal["pass", "warn", "blocking"]
    message: str
    evidence: list[str] = Field(default_factory=list)


class ContentReviewOut(StrictModel):
    id: str
    post_id: str
    post_version: int
    content_sha256: str
    rule_version: str
    status: Literal["ready", "blocked"]
    summary: str
    checks: list[ContentReviewCheck]
    semantic_status: Literal["not_run", "completed", "failed"]
    checked_at: datetime


class MetaPublishRequest(StrictModel):
    post_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)
    connection_id: str | None = Field(default=None, min_length=1, max_length=36)
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def scheduled_time_has_timezone(self) -> "MetaPublishRequest":
        if self.scheduled_at is not None and (self.scheduled_at.tzinfo is None or self.scheduled_at.utcoffset() is None):
            raise ValueError("scheduled_at must include a timezone")
        return self


class ScheduledMetaPublicationOut(StrictModel):
    id: str
    job_id: str
    post_id: str
    post_version: int
    page_id: str
    scheduled_at: datetime
    status: Literal["scheduled", "queued", "cancelled", "missed", "published", "failed", "outcome_unknown"]
    created_at: datetime


class MetaMetricsScheduleIn(StrictModel):
    enabled: bool


class MetaMetricsScheduleOut(StrictModel):
    connection_id: str
    page_id: str
    enabled: bool
    interval_hours: int
    next_sync_at: datetime | None


class CancelScheduledPublicationOut(StrictModel):
    id: str
    status: Literal["cancelled"]
    post_id: str
    post_version: int


class MailGuardIntegrationOut(StrictModel):
    id: str
    key_prefix: str
    status: Literal["active", "revoked"]
    created_at: datetime


class MailGuardIntegrationCreated(MailGuardIntegrationOut):
    integration_key: str


class MailGuardEventIn(StrictModel):
    event_id: str = Field(min_length=1, max_length=160)
    event_type: Literal["signup_completed", "first_analysis_completed"]
    occurred_at: datetime
    external_user_id: str = Field(min_length=1, max_length=200)
    tracking_id: str | None = Field(default=None, min_length=8, max_length=48)

    @model_validator(mode="after")
    def event_time_has_timezone(self) -> "MailGuardEventIn":
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return self


class MailGuardEventReceipt(StrictModel):
    accepted: bool
    duplicate: bool
    message: str


class MailGuardTrackingReferenceIn(StrictModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    post_id: str | None = Field(default=None, min_length=1, max_length=36)
    post_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def post_fields_together(self) -> "MailGuardTrackingReferenceIn":
        if (self.post_id is None) != (self.post_version is None):
            raise ValueError("post_id and post_version must be supplied together")
        return self


class MailGuardTrackingReferenceOut(StrictModel):
    tracking_id: str
    campaign_id: str
    post_id: str | None
    post_version: int | None
    created_at: datetime


class MailGuardConversionAnalyticsOut(StrictModel):
    state: Literal["not_connected", "no_data", "available"]
    signup_count: int | None
    first_analysis_count: int | None
    signup_cohort_count: int | None
    activated_within_window_count: int | None
    activation_rate: float | None
    activation_window_days: int
    window_start: datetime
    window_end: datetime
    attribution: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
