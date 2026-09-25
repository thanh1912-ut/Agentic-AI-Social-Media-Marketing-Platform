"""Public HTTP shapes for the single-owner Meta Page connection."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MetaConnectionOut(StrictModel):
    status: Literal["unconfigured", "configured", "verified", "error"]
    page_id: str | None
    page_name: str | None
    can_publish: bool
    can_sync_metrics: bool
    message: str


class MetaPublishIn(StrictModel):
    post_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)
    connection_id: str | None = Field(default=None, min_length=1, max_length=36)


class MetaErrorOut(StrictModel):
    code: str
    message: str
    hint: str | None = None


class MetaPublicationOut(StrictModel):
    id: str
    post_id: str
    post_version: int
    page_id: str
    connection_id: str | None = None
    status: Literal["queued", "sending", "published", "failed", "needs_reconnect", "outcome_unknown", "not_published"]
    external_post_id: str | None
    permalink: str | None
    error: MetaErrorOut | None
    created_at: datetime
    updated_at: datetime


class MetaReconcileIn(StrictModel):
    outcome: Literal["published", "not_published"]
    external_post_id: str | None = Field(default=None, max_length=160)
    permalink: str | None = Field(default=None, max_length=2048)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_external_id(self) -> "MetaReconcileIn":
        if self.outcome == "published" and not self.external_post_id:
            raise ValueError("external_post_id is required for published outcome")
        return self


class MetaPagePostOut(StrictModel):
    id: str
    external_post_id: str
    page_id: str
    message: str | None
    permalink: str | None
    published_at: datetime | None
    reactions: int | None
    comments: int | None
    shares: int | None
    engagements: int | None
    last_synced_at: datetime
    linked_post_id: str | None


class MetaPagePostsOut(StrictModel):
    items: list[MetaPagePostOut]
    total: int
    has_more: bool
    next_offset: int | None
    sync_has_more: bool
    last_sync_at: datetime | None


class MetaMetricSnapshotOut(StrictModel):
    id: str
    observed_at: datetime
    source: str
    metric_definition: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    followers: int | None = None
    views: int | None = None
    reactions: int | None = None
    comments: int | None = None
    shares: int | None = None
    missing_metrics: list[str]


class MetaMetricHistoryOut(StrictModel):
    entity_type: Literal["page", "post"]
    entity_id: str
    page_id: str | None = None
    snapshots: list[MetaMetricSnapshotOut]
    total: int
    has_more: bool
    next_offset: int | None
