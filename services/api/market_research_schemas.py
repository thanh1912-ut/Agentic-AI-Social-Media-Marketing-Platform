"""HTTP contracts for Page groups and market research sources."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.agents.providers.comment_contracts import CommentAnalysis


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GroupCreate(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    industry: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=1, max_length=160)
    locale: str = Field(default="vi-VN", min_length=2, max_length=24)
    keywords: list[str] = Field(default_factory=list, max_length=30)


class GroupUpdate(GroupCreate):
    active: bool = True


class GroupOut(StrictModel):
    id: str
    name: str
    industry: str
    region: str
    locale: str
    keywords: list[str]
    active: bool
    page_count: int
    source_count: int
    next_due_at: datetime | None
    last_cycle_at: datetime | None


class PageConnectIn(StrictModel):
    page_id: str = Field(pattern=r"^[0-9]{1,32}$")
    page_access_token: str = Field(min_length=20, max_length=4096)

    @field_validator("page_access_token")
    @classmethod
    def token_has_no_control_chars(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("invalid Page token")
        return value


class PageConnectionOut(StrictModel):
    id: str
    group_id: str
    page_id: str
    page_name: str | None
    status: Literal["configured", "verified", "error", "needs_reconnect"]
    verified_at: datetime | None
    last_error_code: str | None
    active: bool


class ResearchSourceCreate(StrictModel):
    group_id: str | None = None
    source_type: Literal["website", "owned_facebook_page", "competitor_facebook_page", "facebook_group"]
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=2048)
    competitor_name: str | None = Field(default=None, max_length=200)
    connection_id: str | None = None


class ResearchSourceOut(StrictModel):
    id: str
    group_id: str
    source_type: str
    name: str
    url: str
    competitor_name: str | None
    status: str
    active: bool
    next_due_at: datetime | None
    last_crawled_at: datetime | None
    error: dict[str, Any] | None
    connection_id: str | None
    crawl_mode: Literal["legacy", "site_catalog"] = "legacy"
    crawl_page_limit: int = 1000
    render_mode: Literal["http_only", "javascript"] = "http_only"
    resource_hosts: list[str] = Field(default_factory=list)
    schedule_enabled: bool = True
    collection_mode: Literal["legacy", "public_web", "meta_api", "manual"] = "legacy"
    collection_post_limit: int = 50
    collection_status: str = "not_started"
    collection_last_method: str | None = None
    last_collection_attempt_at: datetime | None = None
    last_collection_success_at: datetime | None = None


class CollectionSettingsIn(StrictModel):
    collector: Literal["public_web", "meta_api", "manual"]
    schedule_enabled: bool = True
    post_limit: int = Field(default=50, ge=1, le=100)


class ResearchPrivacyPolicyUpdate(StrictModel):
    purpose: str = Field(min_length=10, max_length=4000)
    processing_basis_reference: str = Field(min_length=5, max_length=4000)
    policy_version: str = Field(min_length=1, max_length=100)
    requested_retention_days: int = Field(default=90, ge=1, le=365)


class ResearchPrivacyPolicyOut(StrictModel):
    source_id: str
    configured: bool
    collection_ready: bool = False
    legal_basis_verified: Literal[False] = False
    revision_no: int | None = None
    purpose: str | None = None
    processing_basis_reference: str | None = None
    policy_version: str | None = None
    requested_retention_days: int | None = None
    configured_by: str | None = None
    configured_at: datetime | None = None
    retention_enforcement_status: Literal["not_enforced"] = "not_enforced"
    comments_content_status: Literal["privacy_hold"] = "privacy_hold"


class CommentProcessingIn(StrictModel):
    expected_decision_id: str | None = Field(max_length=36)
    policy_revision_no: int = Field(ge=1)
    assessment_reference: str = Field(min_length=5, max_length=1000)
    status: Literal["pending", "active"] = "pending"
    valid_until: datetime

    @field_validator("valid_until")
    @classmethod
    def expiry_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("valid_until must include a timezone")
        return value

    @field_validator("assessment_reference")
    @classmethod
    def reference_has_no_control_chars(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("assessment_reference must be a reference, not raw personal data")
        return value


class CommentProcessingRevokeIn(StrictModel):
    expected_decision_id: str = Field(min_length=1, max_length=36)


class CommentProcessingOut(StrictModel):
    source_id: str
    supported: bool
    decision_id: str | None = None
    status: Literal["pending", "active", "revoked"] | None = None
    effective_status: Literal["not_configured", "pending", "active", "revoked", "expired",
                              "policy_changed", "assessor_unavailable", "page_unavailable", "source_unavailable",
                              "engine_unavailable", "unsupported"]
    collection_allowed: bool = False
    policy_revision_no: int | None = None
    assessment_reference: str | None = None
    assessed_by: str | None = None
    created_at: datetime | None = None
    valid_until: datetime | None = None
    scope: Literal["local_comment_quarantine_v1"] = "local_comment_quarantine_v1"
    provider_transmission_allowed: Literal[False] = False
    legal_basis_verified_by_platform: Literal[False] = False
    candidate_content_status: Literal["privacy_hold"] = "privacy_hold"
    quarantine_max_hours: Literal[24] = 24
    candidate_versions_count: int = 0
    quarantined_candidate_versions_count: int = 0
    pending_edges: int = 0
    job_id: str | None = None


class CollectionRunOut(StrictModel):
    id: str
    source_id: str
    job_id: str
    collector: str
    engine: str | None = None
    engine_version: str | None = None
    access_tier: int | None = None
    privacy_policy_revision_id: str | None = None
    privacy_policy_revision_no: int | None = None
    privacy_policy_version: str | None = None
    privacy_policy_ready_for_collection: bool | None = None
    privacy_policy_legal_basis_verified: Literal[False] | None = None
    privacy_policy_requested_retention_days: int | None = None
    retention_enforcement_status: Literal["not_enforced"] = "not_enforced"
    comments_content_status: Literal["privacy_hold"] = "privacy_hold"
    status: str
    post_limit: int
    counters: dict[str, Any]
    coverage: dict[str, Any]
    blocked_reason: str | None = None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ResearchPostAttachmentOut(StrictModel):
    kind: Literal["image", "video", "link", "other", "unknown"]
    provider_type: str | None = None
    title: str | None = None
    description: str | None = None
    target_url: str | None = None
    content_status: Literal["metadata_only_privacy_hold"] = "metadata_only_privacy_hold"


class CompetitorPostOut(StrictModel):
    id: str
    source_id: str
    external_id: str | None
    url: str
    title: str
    text: str
    published_at: datetime | None
    observed_at: datetime | None
    metrics: dict[str, int | float | None]
    link_url: str | None = None
    attachments: list[ResearchPostAttachmentOut] = Field(default_factory=list, max_length=100)
    attachment_metadata_status: Literal["returned", "none_returned", "not_returned", "truncated"] = "not_returned"
    metric_provenance: dict[str, Any] = Field(default_factory=dict)
    content_truncated: bool = False
    reaction_breakdown: dict[str, int] = Field(default_factory=dict)
    comment_coverage: dict[str, Any] = Field(default_factory=dict)


class CompetitorPostsPage(StrictModel):
    posts: list[CompetitorPostOut]
    next_cursor: str | None
    followers: int | None = None
    followers_observed_at: datetime | None = None
    followers_missing_reason: str | None = None


class WebCrawlSettingsIn(StrictModel):
    crawl_mode: Literal["legacy", "site_catalog"] = "site_catalog"
    crawl_page_limit: int = Field(default=1000, ge=1, le=1000)
    render_mode: Literal["http_only", "javascript"] = "http_only"
    resource_hosts: list[str] = Field(default_factory=list, max_length=20)
    schedule_enabled: bool = True


class WebCrawlRunOut(StrictModel):
    id: str
    source_id: str
    status: str
    page_limit: int
    counters: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class WebOfferOut(StrictModel):
    id: str
    offer_key: str
    price_kind: str
    price: str | None
    original_price: str | None = None
    low_price: str | None
    high_price: str | None
    currency: str | None
    availability: str | None
    billing_unit: str | None
    seller: str | None
    offer_url: str
    provenance: dict[str, Any]


class WebItemOut(StrictModel):
    id: str
    source_id: str
    kind: str
    title: str
    url: str
    observed_at: datetime | None
    data: dict[str, Any] | None
    offers: list[WebOfferOut] = Field(default_factory=list)


class WebItemsPage(StrictModel):
    items: list[WebItemOut]
    next_cursor: str | None


class ManualObservationIn(StrictModel):
    url: str = Field(min_length=8, max_length=2048)
    title: str = Field(default="", max_length=1000)
    text: str = Field(min_length=1, max_length=12000)
    observed_at: datetime | None = None
    published_at: datetime | None = None
    metrics: dict[str, int | float | None] = Field(default_factory=dict, max_length=20)
    comments: list[str] = Field(default_factory=list, max_length=100)


class ManualImportIn(StrictModel):
    rows: list[ManualObservationIn] = Field(min_length=1, max_length=500)


class ResearchReportOut(StrictModel):
    id: str
    group_id: str
    window_start: datetime
    window_end: datetime
    report: dict[str, Any]
    evidence_ids: list[str]
    coverage: dict[str, Any]
    model_name: str | None
    created_at: datetime
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_audience: list[dict[str, Any]] = Field(default_factory=list)


class ResearchAIBudgetOut(StrictModel):
    budget_date: date
    resets_at: datetime
    currency: Literal["USD"] = "USD"
    limit_micro_usd: int = Field(ge=0)
    reserved_micro_usd: int = Field(ge=0)
    spent_micro_usd: int = Field(ge=0)
    available_micro_usd: int = Field(ge=0)
    unsettled_requests: int = Field(ge=0)
    pending_reports: int = Field(ge=0)


class DraftFromReportIn(StrictModel):
    suggestion_index: int = Field(ge=0, le=19)


class CommentCandidateOut(StrictModel):
    id: str
    is_reply: bool = False
    parent_version_id: str | None = None
    author_alias: str | None
    author_identity_known: bool = False
    text: str
    published_at: datetime | None
    observed_at: datetime
    expires_at: datetime
    likes: int | None
    reactions: int | None
    reactions_raw: str | None = None
    reactions_precision: Literal["exact", "approximate", "lower_bound", "unknown"] = "unknown"
    reaction_breakdown: dict[str, int] = Field(default_factory=dict)
    reply_count: int | None
    content_truncated: bool
    content_status: Literal["privacy_hold"] = "privacy_hold"
    alias_scope: Literal["post_read_only"] = "post_read_only"


class CommentSuppressionIn(StrictModel):
    reason: Literal["subject_request", "out_of_scope", "privacy_risk"]


class CommentSuppressionOut(StrictModel):
    suppression_id: str
    identities_suppressed: int = Field(ge=1)
    versions_erased: int = Field(ge=0)
    reply_edges_stopped: int = Field(ge=0)
    provider_transmission_allowed: Literal[False] = False


class CommentCandidatesPage(StrictModel):
    source_id: str
    evidence_id: str
    observation_id: str | None
    status: Literal["privacy_hold", "no_candidates", "processing_required"]
    comments: list[CommentCandidateOut] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    next_cursor: str | None = None
    suppressed_comments_count: int = Field(default=0, ge=0)
    provider_transmission_allowed: Literal[False] = False


class ScreenedCommentIn(StrictModel):
    version_id: str = Field(min_length=36, max_length=36)
    text: str = Field(min_length=1, max_length=1500)

    @field_validator("text")
    @classmethod
    def nonblank_excerpt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Bản kiểm tra không được để trống")
        return value


class CommentAnalysisIn(StrictModel):
    request_key: str = Field(min_length=36, max_length=36)
    decision_id: str = Field(min_length=36, max_length=36)
    policy_revision_no: int = Field(ge=1)
    provider_assessment_reference: str = Field(min_length=5, max_length=1000)
    comments: list[ScreenedCommentIn] = Field(min_length=1, max_length=50)

    @field_validator("comments")
    @classmethod
    def unique_versions(cls, value: list[ScreenedCommentIn]) -> list[ScreenedCommentIn]:
        if len({item.version_id for item in value}) != len(value):
            raise ValueError("Không chọn trùng phiên bình luận")
        if sum(len(item.text) for item in value) > 12000:
            raise ValueError("Tổng bản kiểm tra tối đa 12.000 ký tự mỗi lô")
        return value

    @field_validator("request_key", "decision_id")
    @classmethod
    def uuid_identity(cls, value: str) -> str:
        from uuid import UUID
        if str(UUID(value)) != value:
            raise ValueError("Identity must be a canonical UUID")
        return value

    @field_validator("provider_assessment_reference")
    @classmethod
    def reference_only(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Chỉ nhập tham chiếu đánh giá, không nhập nội dung cá nhân")
        return value


class ScreenedCommentCitationOut(StrictModel):
    evidence_ref: str
    version_id: str
    evidence_id: str
    observation_id: str
    evidence_version_id: str
    text: str
    content_edited: bool
    source_content_truncated: bool


class CommentAnalysisOut(StrictModel):
    id: str
    source_id: str
    job_id: str | None = None
    report_job_id: str | None = None
    report_id: str | None = None
    status: str
    provider: str
    model: str
    created_at: datetime
    expires_at: datetime
    result: CommentAnalysis | None = None
    coverage: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    selected_version_ids: list[str] = Field(default_factory=list)
    citations: list[ScreenedCommentCitationOut] = Field(default_factory=list)
    legal_basis_verified_by_platform: Literal[False] = False


class CommentAnalysesPage(StrictModel):
    items: list[CommentAnalysisOut]
    next_cursor: str | None = None
