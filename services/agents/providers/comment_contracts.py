"""Provider-neutral contracts for already-screened comment excerpts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScreenedComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ref: str = Field(min_length=8, max_length=128, pattern=r"^comment_[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=1500)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("screened comment text must not be blank")
        return value


class PrivacyApprovedCommentBatch(BaseModel):
    """A privacy decision is required; this contract does not establish legal basis."""

    model_config = ConfigDict(extra="forbid")

    privacy_status: Literal["approved_for_provider"]
    privacy_decision_id: str = Field(min_length=8, max_length=128)
    policy_version: str = Field(min_length=1, max_length=80)
    comments: list[ScreenedComment] = Field(min_length=1, max_length=500)

    @field_validator("comments")
    @classmethod
    def require_unique_evidence_refs(cls, comments: list[ScreenedComment]) -> list[ScreenedComment]:
        refs = [comment.evidence_ref for comment in comments]
        if len(refs) != len(set(refs)):
            raise ValueError("comment evidence references must be unique within a batch")
        return comments


class CommentTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["question", "need", "feedback", "other"]
    topic: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)


class CommentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topics: list[CommentTopic] = Field(max_length=30)
    limitations: list[str] = Field(max_length=20)
