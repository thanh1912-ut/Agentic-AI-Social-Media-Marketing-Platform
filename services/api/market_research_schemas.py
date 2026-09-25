"""HTTP contracts for Page groups and market research sources."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    group_id: str
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


class DraftFromReportIn(StrictModel):
    suggestion_index: int = Field(ge=0, le=19)
