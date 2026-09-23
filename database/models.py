"""SQLAlchemy models owned by the backend.

The models deliberately keep lifecycle state in PostgreSQL. Redis/Celery is
only a delivery mechanism for work that has already been committed here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Company(Base, IdMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(120))


class Membership(Base, IdMixin, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_membership_company_user"),
        Index("ix_membership_user_active", "user_id", "is_active"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Invitation(Base, IdMixin, TimestampMixin):
    __tablename__ = "invitations"
    __table_args__ = (Index("ix_invitation_email_pending", "company_id", "email", "accepted_at"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    invited_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshSession(Base, IdMixin, TimestampMixin):
    __tablename__ = "refresh_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(64))


class PasswordResetToken(Base, IdMixin, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Brand(Base, IdMixin, TimestampMixin):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("company_id", name="uq_brand_company"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class BrandProfileRevision(Base, IdMixin, TimestampMixin):
    __tablename__ = "brand_profile_revisions"
    __table_args__ = (
        UniqueConstraint("brand_id", "revision", name="uq_brand_profile_revision"),
        UniqueConstraint("job_id", name="uq_brand_profile_revision_job"),
        Index("ix_brand_profile_revision_current", "brand_id", "revision"),
    )

    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    internal_profile_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    input_snapshot_id: Mapped[str | None] = mapped_column(String(64))
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    run_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Document(Base, IdMixin, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("company_id", "source_hash", "parser_version", name="uq_document_content_parser"),
        Index("ix_document_company_status", "company_id", "status"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), default=new_id, nullable=False, index=True)
    source_version: Mapped[str] = mapped_column(String(40), default="1", nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    normalized_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    knowledge_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(30), default="not_available", nullable=False)
    profile_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaAsset(Base, IdMixin):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("company_id", "content_sha256", name="uq_media_asset_company_hash"),
        Index("ix_media_asset_company_created", "company_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    alt_text: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DocumentChunk(Base, IdMixin, TimestampMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_document_chunk_company_document", "company_id", "document_id"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class KnowledgeChunk(Base, TimestampMixin):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("company_id", "brand_id", "source_id", "source_hash", "chunk_id", name="uq_knowledge_chunk_identity"),
        Index("ix_knowledge_chunks_scope_active", "company_id", "brand_id", "is_active"),
        Index("ix_knowledge_chunks_source", "source_id", "source_hash"),
    )

    chunk_id: Mapped[str] = mapped_column(String(1200), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    source_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locator: Mapped[str] = mapped_column(String(700), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(40), default="none", nullable=False)
    embedding_model_version: Mapped[str] = mapped_column(String(160), default="lexical-v1", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536).with_variant(JSON(), "sqlite"))


class Job(Base, IdMixin, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_job_company_status", "company_id", "status"),
        Index("ix_job_due_lease", "status", "lease_until"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_job_company_idempotency"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    progress: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class JobStep(Base, IdMixin, TimestampMixin):
    __tablename__ = "job_steps"
    __table_args__ = (UniqueConstraint("job_id", "step_key", name="uq_job_step_key"),)

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    progress: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base, IdMixin):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_job_event_sequence"),)

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RequestDeduplication(Base, IdMixin):
    __tablename__ = "request_deduplications"
    __table_args__ = (UniqueConstraint("company_id", "operation", "idempotency_key", name="uq_request_dedup"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AuditEvent(Base, IdMixin):
    __tablename__ = "audit_events"

    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Campaign(Base, IdMixin, TimestampMixin):
    __tablename__ = "campaigns"
    __table_args__ = (Index("ix_campaign_company_status", "company_id", "status"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    brief_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}", nullable=False)
    pillars_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    channels_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class CampaignPost(Base, IdMixin, TimestampMixin):
    __tablename__ = "campaign_posts"
    __table_args__ = (
        Index("ix_campaign_post_company_campaign", "company_id", "campaign_id"),
        Index("ix_campaign_post_company_status", "company_id", "status"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    pillar: Mapped[str] = mapped_column(String(80), nullable=False)
    format: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pending_approval_version: Mapped[int | None] = mapped_column(Integer)
    requires_reapproval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_mode: Mapped[str | None] = mapped_column(String(20))


class PostVersion(Base, IdMixin):
    __tablename__ = "post_versions"
    __table_args__ = (
        UniqueConstraint("post_id", "version", name="uq_post_version_number"),
        Index("ix_post_version_company_post", "company_id", "post_id"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[str] = mapped_column(ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_by_name: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    generation_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PostApproval(Base, IdMixin):
    __tablename__ = "post_approvals"
    __table_args__ = (
        Index("ix_post_approval_company_post", "company_id", "post_id"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[str] = mapped_column(ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    decided_by_name: Mapped[str] = mapped_column(String(200), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContentGenerationRun(Base, IdMixin):
    __tablename__ = "content_generation_runs"
    __table_args__ = (UniqueConstraint("job_id", name="uq_content_generation_job"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    post_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExportArtifact(Base, IdMixin, TimestampMixin):
    __tablename__ = "export_artifacts"
    __table_args__ = (Index("ix_export_artifact_company_created", "company_id", "created_at"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    object_key: Mapped[str] = mapped_column(String(700), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    post_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    version_snapshot_json: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)


class PostMetricSnapshot(Base, IdMixin):
    __tablename__ = "post_metric_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "post_id", "source_id", "measured_at", name="uq_metric_post_source_measured"),
        Index("ix_metric_company_source_measured", "company_id", "source_id", "measured_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[str] = mapped_column(ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    post_age_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    reach: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int | None] = mapped_column(Integer)
    engagements: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    spend: Mapped[float | None] = mapped_column(Numeric(14, 2))
    attributed_revenue: Mapped[float | None] = mapped_column(Numeric(14, 2))
    attribution_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    imported_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class AnalyticsRecommendationRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "analytics_recommendations"
    __table_args__ = (
        UniqueConstraint("company_id", "source_id", "evidence_fingerprint", name="uq_recommendation_source_evidence"),
        Index("ix_recommendation_company_status", "company_id", "lifecycle_status"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    recommendation_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    feedback_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CampaignBriefRevisionDraft(Base, IdMixin):
    __tablename__ = "campaign_brief_revision_drafts"
    __table_args__ = (
        UniqueConstraint("recommendation_id", name="uq_brief_revision_recommendation"),
        Index("ix_brief_revision_company_campaign", "company_id", "campaign_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("analytics_recommendations.id", ondelete="CASCADE"), nullable=False)
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    changes_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    resulting_brief_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending_review", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RecommendationExperimentOutcome(Base, IdMixin):
    __tablename__ = "recommendation_experiment_outcomes"
    __table_args__ = (
        UniqueConstraint("draft_id", "request_fingerprint", name="uq_experiment_outcome_request"),
        Index("ix_experiment_outcome_company_draft", "company_id", "draft_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    draft_id: Mapped[str] = mapped_column(ForeignKey("campaign_brief_revision_drafts.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    min_post_age_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    max_post_age_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_window_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    baseline_window_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    followup_window_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    followup_window_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    baseline_value: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    followup_value: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    absolute_change: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    relative_change: Mapped[float | None] = mapped_column(Numeric(18, 8))
    baseline_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    followup_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_coverage: Mapped[float] = mapped_column(Numeric(8, 7), nullable=False)
    followup_coverage: Mapped[float] = mapped_column(Numeric(8, 7), nullable=False)
    baseline_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    followup_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    limitations_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
