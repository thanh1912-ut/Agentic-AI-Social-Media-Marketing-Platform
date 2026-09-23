"""Strict HTTP DTOs for campaign, content, approval and export workflows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CampaignBriefIn(StrictModel):
    objective: Literal["awareness", "engagement", "traffic", "leads", "sales", "retention"]
    objective_note: str | None = Field(default=None, max_length=1000)
    audience: list[str] = Field(min_length=1, max_length=20)
    product_ids: list[str] = Field(default_factory=list, max_length=100)
    key_message: str = Field(min_length=1, max_length=2000)
    must_include: list[str] = Field(default_factory=list, max_length=30)
    must_avoid: list[str] = Field(default_factory=list, max_length=30)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def date_range_is_valid(self) -> "CampaignBriefIn":
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        return self


ContentPillarValue = Literal[
    "education", "entertainment", "inspiration", "promotion", "community",
    "behind_the_scenes", "product", "testimonial",
]


class CampaignCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    brief: CampaignBriefIn
    pillars: list[ContentPillarValue] = Field(default_factory=lambda: ["product", "education"], max_length=8)
    channels: list[Literal["facebook_page"]] = Field(default_factory=lambda: ["facebook_page"], min_length=1)


class CampaignUpdateRequest(CampaignCreateRequest):
    version: int = Field(ge=1)


class CampaignOut(StrictModel):
    id: str
    workspace_id: str
    name: str
    status: Literal["draft", "active", "completed", "archived"]
    brief: dict[str, Any]
    pillars: list[ContentPillarValue]
    channels: list[str]
    version: int
    post_count: int
    approved_count: int
    published_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class PaginatedCampaigns(StrictModel):
    items: list[CampaignOut]
    total: int
    page: int
    page_size: int


class GenerateContentRequest(StrictModel):
    campaign_id: str
    count: int = Field(ge=1, le=10)
    pillars: list[ContentPillarValue] = Field(default_factory=list, max_length=8)
    formats: list[Literal["text", "image", "carousel", "video", "reel", "story"]] = Field(default_factory=lambda: ["text"], min_length=1, max_length=6)
    start_date: date | None = None
    end_date: date | None = None
    instruction: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def date_range_is_valid(self) -> "GenerateContentRequest":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        return self


class GenerateContentResponse(StrictModel):
    job_id: str
    max_count: int = 10


class CreateManualPostRequest(StrictModel):
    pillar: Literal[
        "education", "entertainment", "inspiration", "promotion", "community",
        "behind_the_scenes", "product", "testimonial",
    ]
    format: Literal["text", "image", "carousel", "video", "reel", "story"] = "text"
    caption: str = Field(min_length=1, max_length=10000)
    hashtags: list[str] = Field(default_factory=list, max_length=50)


class UpdatePostRequest(StrictModel):
    version: int = Field(ge=1)
    caption: str | None = Field(default=None, min_length=1, max_length=10000)
    hashtags: list[str] | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def update_has_changes(self) -> "UpdatePostRequest":
        if self.caption is None and self.hashtags is None:
            raise ValueError("caption or hashtags must be provided")
        return self


class ReviseWithAiRequest(StrictModel):
    version: int = Field(ge=1)
    instruction: str = Field(min_length=1, max_length=2000)
    scope: Literal["caption", "hashtags", "media", "all"] = "all"


class PostOut(StrictModel):
    id: str
    campaign_id: str
    workspace_id: str
    channel: str
    pillar: str
    format: str
    status: Literal["draft", "needs_review", "approved", "rejected", "scheduled", "published", "failed"]
    version: int
    current: dict[str, Any]
    scheduled_at: datetime | None = None
    publish_mode: Literal["now", "scheduled", "manual"] | None = None
    requires_reapproval: bool
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class PaginatedPosts(StrictModel):
    items: list[PostOut]
    total: int
    page: int
    page_size: int


class PostVersionOut(StrictModel):
    version: int
    caption: str
    hashtags: list[str]
    media: list[dict[str, Any]]
    source: Literal["human", "ai_generated", "ai_revised", "imported"]
    created_by: str
    created_by_name: str
    created_at: datetime
    note: str | None = None
    review: dict[str, Any] | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None


class PostVersionListOut(StrictModel):
    post_id: str
    versions: list[PostVersionOut]
    current_version: int
    pending_approval_version: int | None = None


class ApprovalRequest(StrictModel):
    version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalRecordOut(StrictModel):
    id: str
    post_id: str
    version: int
    decision: Literal["approved", "rejected"]
    reason: str | None = None
    decided_by: str
    decided_by_name: str
    decided_at: datetime


class SubmitApprovalRequest(StrictModel):
    version: int = Field(ge=1)


class CreateExportRequest(StrictModel):
    campaign_id: str
    format: Literal["csv", "xlsx"]
    post_ids: list[str] | None = Field(default=None, max_length=1000)
    columns: list[str] | None = Field(default=None, max_length=30)


class ExportOut(StrictModel):
    id: str
    campaign_id: str
    format: Literal["csv", "xlsx"]
    status: Literal["ready"]
    download_url: str
    filename: str
    size: int
    created_at: datetime
