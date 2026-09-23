"""HTTP schemas for manual metrics, analytics summaries, and recommendations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts import AnalyticsReport


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MetricPointIn(StrictModel):
    post_id: str = Field(min_length=1, max_length=36)
    post_age_hours: int = Field(ge=0, le=24 * 365)
    reach: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)
    engagements: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    spend: float | None = Field(default=None, ge=0)
    attributed_revenue: float | None = Field(default=None, ge=0)
    attribution_valid: bool = False

    @model_validator(mode="after")
    def contains_a_measurement(self) -> "MetricPointIn":
        if all(getattr(self, key) is None for key in ("reach", "views", "engagements", "clicks", "spend", "attributed_revenue")):
            raise ValueError("at least one metric value is required")
        if self.attribution_valid and (self.spend is None or self.attributed_revenue is None):
            raise ValueError("valid attribution requires both spend and attributed_revenue")
        return self


class MetricImportRequest(StrictModel):
    source_id: str = Field(min_length=1, max_length=160)
    measured_at: datetime
    points: list[MetricPointIn] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_snapshot(self) -> "MetricImportRequest":
        if self.measured_at.tzinfo is None or self.measured_at.utcoffset() is None:
            raise ValueError("measured_at must include a timezone")
        post_ids = [point.post_id for point in self.points]
        if len(post_ids) != len(set(post_ids)):
            raise ValueError("a snapshot may contain only one point per post")
        return self


class MetricImportResponse(StrictModel):
    source_id: str
    imported_count: int
    measured_at: datetime
    snapshot_fingerprint: str


class MetricGroupOut(StrictModel):
    dimension: Literal["pillar", "format"]
    name: str
    post_count: int
    average_reach: float | None = None
    average_views: float | None = None
    engagement_rate_by_reach: float | None = None
    click_rate_by_reach: float | None = None


class AnalyticsDashboardOut(StrictModel):
    report: AnalyticsReport
    groups: list[MetricGroupOut]
    source_id: str
    source_label: str
    freshness_at: datetime | None = None


class RecommendationOut(StrictModel):
    status: Literal["abstain", "proposed"]
    observation: str
    hypothesis: str | None = None
    action: str | None = None
    metric: str
    threshold: str | None = None
    confidence: float = Field(ge=0, le=1)
    sample_size: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
    created_at: datetime


class SaveRecommendationRequest(StrictModel):
    source_id: str = Field(min_length=1, max_length=160)


class RecommendationFeedbackRequest(StrictModel):
    value: Literal["useful", "not_useful", "already_done"]
    note: str | None = Field(default=None, max_length=1000)


class RecommendationFeedbackOut(StrictModel):
    value: Literal["useful", "not_useful", "already_done"]
    note: str | None = None
    at: datetime
    by: str


class AnalyticsRecommendationRecordOut(StrictModel):
    id: str
    source_id: str
    lifecycle_status: Literal["new", "acknowledged", "dismissed", "applied"]
    recommendation: RecommendationOut
    feedback: RecommendationFeedbackOut | None = None
    created_at: datetime


class ApplyRecommendationRequest(StrictModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    evidence_ids: list[str] | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=1000)


class CampaignBriefChangeOut(StrictModel):
    field: str
    label: str
    before: Any
    after: Any
    rationale: str


class CampaignBriefRevisionDraftOut(StrictModel):
    id: str
    campaign_id: str
    base_version: int
    changes: list[CampaignBriefChangeOut]
    source_recommendation_id: str
    status: Literal["pending_review", "accepted", "discarded"]
    created_at: datetime


class ApplyRecommendationResponse(StrictModel):
    recommendation: AnalyticsRecommendationRecordOut
    created_draft: CampaignBriefRevisionDraftOut
    notice: str


class RecommendationDraftDecisionRequest(StrictModel):
    decision: Literal["accepted", "discarded"]
