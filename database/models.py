"""SQLAlchemy models owned by the backend.

The models deliberately keep lifecycle state in PostgreSQL. Redis/Celery is
only a delivery mechanism for work that has already been committed here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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
    # The PostgreSQL vector column is intentionally dimension-flexible. Its
    # provider/model/version fields isolate vectors with different dimensions.
    embedding: Mapped[list[float] | None] = mapped_column(Vector().with_variant(JSON(), "sqlite"))


class Job(Base, IdMixin, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_job_company_status", "company_id", "status"),
        Index("ix_job_due_lease", "status", "lease_until"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_job_company_idempotency"),
        UniqueConstraint("company_id", "id", name="uq_job_tenant_id"),
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
    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_campaign_tenant_id"),
        ForeignKeyConstraint(["company_id", "group_id"], ["meta_page_groups.company_id", "meta_page_groups.id"],
                             name="fk_campaign_group_tenant"),
        Index("ix_campaign_company_status", "company_id", "status"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("meta_page_groups.id", ondelete="SET NULL"), index=True)
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
        UniqueConstraint("company_id", "id", name="uq_campaign_post_tenant_id"),
        UniqueConstraint("company_id", "campaign_id", "id", name="uq_campaign_post_tenant_campaign"),
        ForeignKeyConstraint(["company_id", "campaign_id"], ["campaigns.company_id", "campaigns.id"],
                             name="fk_campaign_post_campaign_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "target_connection_id"],
                             ["meta_page_connections.company_id", "meta_page_connections.id"],
                             name="fk_campaign_post_target_tenant"),
        Index("ix_campaign_post_company_campaign", "company_id", "campaign_id"),
        Index("ix_campaign_post_company_status", "company_id", "status"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    target_connection_id: Mapped[str | None] = mapped_column(ForeignKey("meta_page_connections.id", ondelete="SET NULL"))
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
        UniqueConstraint("company_id", "post_id", "version", name="uq_post_version_tenant_number"),
        ForeignKeyConstraint(["company_id", "campaign_id", "post_id"],
                             ["campaign_posts.company_id", "campaign_posts.campaign_id", "campaign_posts.id"],
                             name="fk_post_version_post_tenant", ondelete="CASCADE"),
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
        ForeignKeyConstraint(
            ["company_id", "post_id", "version"],
            ["post_versions.company_id", "post_versions.post_id", "post_versions.version"],
            name="fk_post_approval_version_tenant",
        ),
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


class MetaPublication(Base, IdMixin, TimestampMixin):
    """One guarded attempt to publish an approved, immutable post version."""

    __tablename__ = "meta_publications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "post_id", "post_version"],
            ["post_versions.company_id", "post_versions.post_id", "post_versions.version"],
            name="fk_meta_publication_version_tenant",
        ),
        UniqueConstraint("company_id", "active_key", name="uq_meta_publication_active"),
        Index("ix_meta_publication_company_created", "company_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[str] = mapped_column(ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False)
    post_version: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_id: Mapped[str] = mapped_column(String(100), nullable=False)
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("meta_page_connections.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False)
    active_key: Mapped[str | None] = mapped_column(String(255))
    external_post_id: Mapped[str | None] = mapped_column(String(160))
    permalink: Mapped[str | None] = mapped_column(String(2048))
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MetaPagePost(Base, IdMixin, TimestampMixin):
    """Page-authored posts, including historical posts outside this product."""

    __tablename__ = "meta_page_posts"
    __table_args__ = (
        UniqueConstraint("company_id", "page_id", "external_post_id", name="uq_meta_page_post_external"),
        UniqueConstraint("company_id", "id", name="uq_meta_page_post_tenant_id"),
        Index("ix_meta_page_post_company_published", "company_id", "published_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_post_id: Mapped[str] = mapped_column(String(160), nullable=False)
    linked_post_id: Mapped[str | None] = mapped_column(ForeignKey("campaign_posts.id", ondelete="SET NULL"))
    message: Mapped[str | None] = mapped_column(Text)
    permalink: Mapped[str | None] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reactions: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MetaSyncState(Base, IdMixin, TimestampMixin):
    __tablename__ = "meta_sync_states"
    __table_args__ = (UniqueConstraint("company_id", "page_id", name="uq_meta_sync_company_page"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[str] = mapped_column(String(100), nullable=False)
    page_name: Mapped[str | None] = mapped_column(String(200))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_cursor: Mapped[str | None] = mapped_column(Text)
    has_more: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    running_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))


class MetaPageGroup(Base, IdMixin, TimestampMixin):
    """A user-defined set of owned Pages sharing one market profile."""

    __tablename__ = "meta_page_groups"
    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_meta_page_group_tenant_id"),
        UniqueConstraint("company_id", "name", name="uq_meta_page_group_name"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    industry: Mapped[str] = mapped_column(String(160), nullable=False)
    region: Mapped[str] = mapped_column(String(160), nullable=False)
    locale: Mapped[str] = mapped_column(String(24), default="vi-VN", nullable=False)
    keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MetaPageConnection(Base, IdMixin, TimestampMixin):
    """One encrypted Page token; the plaintext is only materialized in workers."""

    __tablename__ = "meta_page_connections"
    __table_args__ = (
        UniqueConstraint("company_id", "page_id", name="uq_meta_connection_company_page"),
        UniqueConstraint("company_id", "id", name="uq_meta_connection_tenant_id"),
        UniqueConstraint("company_id", "id", "page_id", name="uq_meta_connection_tenant_page"),
        ForeignKeyConstraint(["company_id", "group_id"], ["meta_page_groups.company_id", "meta_page_groups.id"],
                             name="fk_meta_connection_group_tenant", ondelete="CASCADE"),
        Index("ix_meta_connection_group_active", "company_id", "group_id", "active"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[str] = mapped_column(String(100), nullable=False)
    page_name: Mapped[str | None] = mapped_column(String(200))
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="configured", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ResearchSource(Base, IdMixin, TimestampMixin):
    """User-submitted web/Page/group URL; external text is never a brand document."""

    __tablename__ = "research_sources"
    __table_args__ = (
        UniqueConstraint("company_id", "group_id", "normalized_url", name="uq_research_source_url"),
        UniqueConstraint("company_id", "id", name="uq_research_source_tenant_id"),
        UniqueConstraint("company_id", "group_id", "id", name="uq_research_source_tenant_group_id"),
        ForeignKeyConstraint(["company_id", "group_id"], ["meta_page_groups.company_id", "meta_page_groups.id"],
                             name="fk_research_source_group_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "connection_id"],
                             ["meta_page_connections.company_id", "meta_page_connections.id"],
                             name="fk_research_source_connection_tenant"),
        Index("ix_research_source_due", "company_id", "group_id", "active", "next_due_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("meta_page_connections.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    competitor_name: Mapped[str | None] = mapped_column(String(200))
    crawl_mode: Mapped[str] = mapped_column(String(24), default="legacy", nullable=False)
    crawl_page_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    render_mode: Mapped[str] = mapped_column(String(24), default="http_only", nullable=False)
    resource_hosts_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class ResearchCycle(Base, IdMixin, TimestampMixin):
    __tablename__ = "research_cycles"
    __table_args__ = (
        UniqueConstraint("company_id", "group_id", "cycle_key", name="uq_research_cycle_window"),
        UniqueConstraint("company_id", "id", name="uq_research_cycle_tenant_id"),
        UniqueConstraint("company_id", "group_id", "id", name="uq_research_cycle_tenant_group_id"),
        ForeignKeyConstraint(["company_id", "group_id"], ["meta_page_groups.company_id", "meta_page_groups.id"],
                             name="fk_research_cycle_group_tenant", ondelete="CASCADE"),
        Index("ix_research_cycle_group_created", "company_id", "group_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[str] = mapped_column(ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    cycle_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    source_results_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketEvidence(Base, IdMixin, TimestampMixin):
    __tablename__ = "market_evidence"
    __table_args__ = (
        UniqueConstraint("company_id", "source_id", "canonical_url", name="uq_market_evidence_source_url"),
        UniqueConstraint("company_id", "id", name="uq_market_evidence_tenant_id"),
        UniqueConstraint("company_id", "group_id", "id", name="uq_market_evidence_tenant_group_id"),
        ForeignKeyConstraint(["company_id", "group_id"], ["meta_page_groups.company_id", "meta_page_groups.id"],
                             name="fk_market_evidence_group_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "source_id"], ["research_sources.company_id", "research_sources.id"],
                             name="fk_market_evidence_source_tenant", ondelete="CASCADE"),
        Index("ix_market_evidence_group_published", "company_id", "group_id", "published_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[str] = mapped_column(ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trust_level: Mapped[str] = mapped_column(String(32), default="external_unverified", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketObservation(Base, IdMixin):
    __tablename__ = "market_observations"
    __table_args__ = (
        Index("ix_market_observation_evidence_at", "evidence_id", "observed_at"),
        UniqueConstraint("evidence_id", "observed_at", name="uq_market_observation_at"),
        UniqueConstraint("company_id", "evidence_id", "id", name="uq_market_observation_tenant_evidence"),
        UniqueConstraint("company_id", "evidence_id", "id", "evidence_version_id",
                         name="uq_market_observation_tenant_version"),
        ForeignKeyConstraint(["company_id", "evidence_id"],
                             ["market_evidence.company_id", "market_evidence.id"],
                             name="fk_market_observation_evidence_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "evidence_id", "evidence_version_id"],
                             ["market_evidence_versions.company_id", "market_evidence_versions.evidence_id",
                              "market_evidence_versions.id"],
                             name="fk_market_observation_version_tenant"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("market_evidence.id", ondelete="CASCADE"), nullable=False)
    evidence_version_id: Mapped[str | None] = mapped_column(String(36))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    comments_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    raw_object_key: Mapped[str | None] = mapped_column(String(1024))
    raw_sha256: Mapped[str | None] = mapped_column(String(64))
    raw_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class MarketReport(Base, IdMixin, TimestampMixin):
    __tablename__ = "market_reports"
    __table_args__ = (
        UniqueConstraint("company_id", "id", name="uq_market_report_tenant_id"),
        UniqueConstraint("company_id", "group_id", "id", name="uq_market_report_tenant_group_id"),
        UniqueConstraint("cycle_id", name="uq_market_report_cycle"),
        ForeignKeyConstraint(["company_id", "group_id"], ["meta_page_groups.company_id", "meta_page_groups.id"],
                             name="fk_market_report_group_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "group_id", "cycle_id"],
                             ["research_cycles.company_id", "research_cycles.group_id", "research_cycles.id"],
                             name="fk_market_report_cycle_tenant"),
        Index("ix_market_report_group_created", "company_id", "group_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[str] = mapped_column(ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False)
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("research_cycles.id", ondelete="SET NULL"))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(160))


class MarketEvidenceVersion(Base, IdMixin):
    """Immutable extracted content used as exact provenance for a report."""

    __tablename__ = "market_evidence_versions"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "evidence_id", "content_hash", "parser_version",
            name="uq_market_evidence_version_fingerprint",
        ),
        UniqueConstraint("company_id", "evidence_id", "id", name="uq_market_evidence_version_tenant_id"),
        ForeignKeyConstraint(["company_id", "evidence_id"],
                             ["market_evidence.company_id", "market_evidence.id"],
                             name="fk_market_evidence_version_evidence_tenant", ondelete="CASCADE"),
        Index("ix_market_evidence_version_evidence_captured", "company_id", "evidence_id", "captured_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MarketReportEvidence(Base, IdMixin):
    """Links a report to the precise observation and extracted text version."""

    __tablename__ = "market_report_evidence"
    __table_args__ = (
        UniqueConstraint("report_id", "observation_id", name="uq_market_report_evidence_observation"),
        ForeignKeyConstraint(["company_id", "group_id", "report_id"],
                             ["market_reports.company_id", "market_reports.group_id", "market_reports.id"],
                             name="fk_market_report_evidence_report_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "group_id", "evidence_id"],
                             ["market_evidence.company_id", "market_evidence.group_id", "market_evidence.id"],
                             name="fk_market_report_evidence_group_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "evidence_id", "observation_id", "evidence_version_id"],
                             ["market_observations.company_id", "market_observations.evidence_id",
                              "market_observations.id", "market_observations.evidence_version_id"],
                             name="fk_market_report_evidence_observation_version", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "evidence_id", "evidence_version_id"],
                             ["market_evidence_versions.company_id", "market_evidence_versions.evidence_id",
                              "market_evidence_versions.id"],
                             name="fk_market_report_evidence_version_tenant", ondelete="CASCADE"),
        Index("ix_market_report_evidence_report", "company_id", "report_id"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    group_id: Mapped[str] = mapped_column(String(36), nullable=False)
    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    observation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evidence_version_id: Mapped[str] = mapped_column(String(36), nullable=False)


class MarketReportWebSnapshot(Base, IdMixin):
    """Pins normalized website entity snapshots cited by one report."""

    __tablename__ = "market_report_web_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "report_id", "snapshot_id", name="uq_market_report_web_snapshot"),
        ForeignKeyConstraint(["company_id", "report_id"],
                             ["market_reports.company_id", "market_reports.id"],
                             name="fk_market_report_web_snapshot_report_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "snapshot_id"],
                             ["web_entity_snapshots.company_id", "web_entity_snapshots.id"],
                             name="fk_market_report_web_snapshot_entity_tenant"),
        Index("ix_market_report_web_snapshot_report", "company_id", "report_id"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MetaPostMetricSnapshot(Base, IdMixin):
    """Historical metrics for both system-published and externally-created Page posts."""

    __tablename__ = "meta_post_metric_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "meta_page_post_id", "snapshot_key", name="uq_meta_post_metric_snapshot_key"),
        ForeignKeyConstraint(["company_id", "meta_page_post_id"],
                             ["meta_page_posts.company_id", "meta_page_posts.id"],
                             name="fk_meta_post_metric_post_tenant", ondelete="CASCADE"),
        Index("ix_meta_post_metric_history", "company_id", "meta_page_post_id", "observed_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    meta_page_post_id: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_key: Mapped[str] = mapped_column(String(200), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="meta_graph")
    metric_definition: Mapped[str] = mapped_column(String(100), nullable=False, default="meta_post_v1")
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    views: Mapped[int | None] = mapped_column(Integer)
    reactions: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    missing_metrics_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class MetaPageMetricSnapshot(Base, IdMixin):
    """Page-level audience snapshots; never repeated on every post observation."""

    __tablename__ = "meta_page_metric_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "connection_id", "snapshot_key", name="uq_meta_page_metric_snapshot_key"),
        ForeignKeyConstraint(["company_id", "connection_id", "page_id"],
                             ["meta_page_connections.company_id", "meta_page_connections.id",
                              "meta_page_connections.page_id"],
                             name="fk_meta_page_metric_connection_tenant", ondelete="CASCADE"),
        Index("ix_meta_page_metric_history", "company_id", "page_id", "observed_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False)
    page_id: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_key: Mapped[str] = mapped_column(String(200), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="meta_graph")
    metric_definition: Mapped[str] = mapped_column(String(100), nullable=False, default="page_followers_v1")
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    followers: Mapped[int | None] = mapped_column(Integer)
    missing_metrics_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class ResearchSourceMetricSnapshot(Base, IdMixin):
    """Page/group audience figures supplied by a permitted API or human import."""

    __tablename__ = "research_source_metric_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "source_id", "snapshot_key", name="uq_research_source_metric_snapshot_key"),
        ForeignKeyConstraint(["company_id", "source_id"],
                             ["research_sources.company_id", "research_sources.id"],
                             name="fk_research_source_metric_source_tenant", ondelete="CASCADE"),
        Index("ix_research_source_metric_history", "company_id", "source_id", "observed_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_key: Mapped[str] = mapped_column(String(200), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_definition: Mapped[str] = mapped_column(String(100), nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    followers: Mapped[int | None] = mapped_column(Integer)
    members: Mapped[int | None] = mapped_column(Integer)
    missing_metrics_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


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


class WebCrawlRun(Base, IdMixin, TimestampMixin):
    """A durable website scan checkpoint tied to one research cycle."""

    __tablename__ = "web_crawl_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "source_id", "cycle_id", name="uq_web_crawl_run_cycle_source"),
        UniqueConstraint("company_id", "id", name="uq_web_crawl_run_tenant_id"),
        ForeignKeyConstraint(["company_id", "source_id"], ["research_sources.company_id", "research_sources.id"],
                             name="fk_web_crawl_run_source_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "group_id", "source_id"],
                             ["research_sources.company_id", "research_sources.group_id", "research_sources.id"],
                             name="fk_web_crawl_run_source_group_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "group_id"], ["meta_page_groups.company_id", "meta_page_groups.id"],
                             name="fk_web_crawl_run_group_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "cycle_id"], ["research_cycles.company_id", "research_cycles.id"],
                             name="fk_web_crawl_run_cycle_tenant", ondelete="CASCADE"),
        Index("ix_web_crawl_run_status_updated", "status", "updated_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    group_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    cycle_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    page_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    counters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebCrawlPage(Base, IdMixin, TimestampMixin):
    """URL frontier/checkpoint row; status transitions are persisted in PostgreSQL."""

    __tablename__ = "web_crawl_pages"
    __table_args__ = (
        UniqueConstraint("company_id", "run_id", "url", name="uq_web_crawl_page_url"),
        ForeignKeyConstraint(["company_id", "run_id"], ["web_crawl_runs.company_id", "web_crawl_runs.id"],
                             name="fk_web_crawl_page_run_tenant", ondelete="CASCADE"),
        Index("ix_web_crawl_page_frontier", "company_id", "run_id", "status", "depth"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(500))
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence_id: Mapped[str | None] = mapped_column(String(36))
    observation_id: Mapped[str | None] = mapped_column(String(36))
    evidence_version_id: Mapped[str | None] = mapped_column(String(36))


class WebEntity(Base, IdMixin, TimestampMixin):
    """Source-scoped stable identity for a public product, article, or business fact."""

    __tablename__ = "web_entities"
    __table_args__ = (
        UniqueConstraint("company_id", "source_id", "kind", "identity_key", name="uq_web_entity_identity"),
        UniqueConstraint("company_id", "id", name="uq_web_entity_tenant_id"),
        ForeignKeyConstraint(["company_id", "source_id"], ["research_sources.company_id", "research_sources.id"],
                             name="fk_web_entity_source_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "group_id", "source_id"],
                             ["research_sources.company_id", "research_sources.group_id", "research_sources.id"],
                             name="fk_web_entity_source_group_tenant", ondelete="CASCADE"),
        Index("ix_web_entity_group_kind", "company_id", "group_id", "kind", "title"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    group_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_key: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    latest_snapshot_id: Mapped[str | None] = mapped_column(String(36))


class WebEntitySnapshot(Base, IdMixin):
    """Immutable normalized entity observation pinned to source evidence."""

    __tablename__ = "web_entity_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "run_id", "entity_id", "content_hash", name="uq_web_entity_snapshot_run_hash"),
        UniqueConstraint("company_id", "id", name="uq_web_entity_snapshot_tenant_id"),
        ForeignKeyConstraint(["company_id", "entity_id"], ["web_entities.company_id", "web_entities.id"],
                             name="fk_web_entity_snapshot_entity_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "run_id"], ["web_crawl_runs.company_id", "web_crawl_runs.id"],
                             name="fk_web_entity_snapshot_run_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["company_id", "evidence_id", "evidence_version_id"],
                             ["market_evidence_versions.company_id", "market_evidence_versions.evidence_id", "market_evidence_versions.id"],
                             name="fk_web_entity_snapshot_evidence_version"),
        ForeignKeyConstraint(["company_id", "evidence_id", "observation_id", "evidence_version_id"],
                             ["market_observations.company_id", "market_observations.evidence_id", "market_observations.id", "market_observations.evidence_version_id"],
                             name="fk_web_entity_snapshot_observation_version"),
        Index("ix_web_entity_snapshot_history", "company_id", "entity_id", "observed_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    observation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evidence_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class WebOfferSnapshot(Base, IdMixin):
    """One offer/variant price attached to one immutable product snapshot."""

    __tablename__ = "web_offer_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "entity_snapshot_id", "offer_key", name="uq_web_offer_snapshot_identity"),
        ForeignKeyConstraint(["company_id", "entity_snapshot_id"],
                             ["web_entity_snapshots.company_id", "web_entity_snapshots.id"],
                             name="fk_web_offer_snapshot_entity_tenant", ondelete="CASCADE"),
        Index("ix_web_offer_price", "company_id", "currency", "price"),
    )

    company_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entity_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    offer_key: Mapped[str] = mapped_column(String(500), nullable=False)
    price_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    currency: Mapped[str | None] = mapped_column(String(8))
    availability: Mapped[str | None] = mapped_column(String(120))
    billing_unit: Mapped[str | None] = mapped_column(String(80))
    seller: Mapped[str | None] = mapped_column(String(300))
    offer_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
