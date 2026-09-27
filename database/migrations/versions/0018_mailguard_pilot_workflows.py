"""Persist post safety reviews, scheduled publishing, and MailGuard events."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_mailguard_pilot_workflows"
down_revision = "0017_web_entity_snapshot_immutability"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    connection_columns = _columns("meta_page_connections")
    if connection_columns:
        if "metrics_schedule_enabled" not in connection_columns:
            op.add_column("meta_page_connections", sa.Column("metrics_schedule_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
        if "metrics_sync_interval_hours" not in connection_columns:
            op.add_column("meta_page_connections", sa.Column("metrics_sync_interval_hours", sa.Integer(), server_default="6", nullable=False))
        if "next_metrics_sync_at" not in connection_columns:
            op.add_column("meta_page_connections", sa.Column("next_metrics_sync_at", sa.DateTime(timezone=True), nullable=True))

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "post_content_reviews" not in tables:
        op.create_table(
            "post_content_reviews",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("post_id", sa.String(36), sa.ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("post_version", sa.Integer(), nullable=False),
            sa.Column("content_sha256", sa.String(64), nullable=False),
            sa.Column("rule_version", sa.String(40), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("checks_json", sa.JSON(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("semantic_status", sa.String(24), server_default="not_run", nullable=False),
            sa.Column("checked_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["company_id", "post_id", "post_version"], ["post_versions.company_id", "post_versions.post_id", "post_versions.version"], name="fk_post_content_review_version_tenant", ondelete="CASCADE"),
            sa.CheckConstraint("status IN ('ready', 'blocked')", name="ck_post_content_review_status"),
        )
        op.create_index("ix_post_content_review_version", "post_content_reviews", ["company_id", "post_id", "post_version", "checked_at"])

    if "scheduled_meta_publications" not in tables:
        op.create_table(
            "scheduled_meta_publications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("post_id", sa.String(36), sa.ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("post_version", sa.Integer(), nullable=False),
            sa.Column("page_id", sa.String(100), nullable=False),
            sa.Column("connection_id", sa.String(36), nullable=True),
            sa.Column("approved_content_sha256", sa.String(64), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(20), server_default="scheduled", nullable=False),
            sa.Column("active_key", sa.String(255), nullable=True),
            sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("publication_id", sa.String(36), sa.ForeignKey("meta_publications.id", ondelete="SET NULL"), nullable=True),
            sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["company_id", "post_id", "post_version"], ["post_versions.company_id", "post_versions.post_id", "post_versions.version"], name="fk_scheduled_meta_post_version_tenant", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["company_id", "connection_id", "page_id"], ["meta_page_connections.company_id", "meta_page_connections.id", "meta_page_connections.page_id"], name="fk_scheduled_meta_connection_tenant_page", ondelete="RESTRICT"),
            sa.CheckConstraint("status IN ('scheduled', 'queued', 'cancelled', 'missed', 'published', 'failed', 'outcome_unknown')", name="ck_scheduled_meta_status"),
            sa.UniqueConstraint("company_id", "active_key", name="uq_scheduled_meta_active"),
            sa.UniqueConstraint("job_id", name="uq_scheduled_meta_job"),
        )
        op.create_index("ix_scheduled_meta_due", "scheduled_meta_publications", ["status", "scheduled_at"])

    if "mailguard_integrations" not in tables:
        op.create_table(
            "mailguard_integrations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("key_hash", sa.String(64), nullable=False),
            sa.Column("key_prefix", sa.String(24), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", name="uq_mailguard_integration_company"),
            sa.UniqueConstraint("key_hash", name="uq_mailguard_integration_key_hash"),
            sa.UniqueConstraint("company_id", "id", name="uq_mailguard_integration_tenant_id"),
        )

    if "mailguard_tracking_references" not in tables:
        op.create_table(
            "mailguard_tracking_references",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tracking_id", sa.String(48), nullable=False),
            sa.Column("campaign_id", sa.String(36), nullable=True),
            sa.Column("post_id", sa.String(36), nullable=True),
            sa.Column("post_version", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("(post_id IS NULL) = (post_version IS NULL)", name="ck_mailguard_tracking_post_pair"),
            sa.ForeignKeyConstraint(["company_id", "campaign_id"], ["campaigns.company_id", "campaigns.id"], name="fk_mailguard_tracking_campaign_tenant", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["company_id", "post_id", "post_version"], ["post_versions.company_id", "post_versions.post_id", "post_versions.version"], name="fk_mailguard_tracking_post_version_tenant", ondelete="CASCADE"),
            sa.UniqueConstraint("company_id", "tracking_id", name="uq_mailguard_tracking_tenant_id"),
        )

    if "mailguard_conversion_events" not in tables:
        op.create_table(
            "mailguard_conversion_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("integration_id", sa.String(36), nullable=False),
            sa.Column("event_id", sa.String(160), nullable=False),
            sa.Column("event_type", sa.String(40), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("actor_hash", sa.String(64), nullable=False),
            sa.Column("tracking_id", sa.String(48), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("event_type IN ('signup_completed', 'first_analysis_completed')", name="ck_mailguard_event_type"),
            sa.ForeignKeyConstraint(["company_id", "integration_id"], ["mailguard_integrations.company_id", "mailguard_integrations.id"], name="fk_mailguard_event_integration_tenant", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["company_id", "tracking_id"], ["mailguard_tracking_references.company_id", "mailguard_tracking_references.tracking_id"], name="fk_mailguard_event_tracking_tenant"),
            sa.UniqueConstraint("integration_id", "event_id", name="uq_mailguard_event_id"),
            sa.UniqueConstraint("integration_id", "event_type", "actor_hash", name="uq_mailguard_event_actor_type"),
        )
        op.create_index("ix_mailguard_event_company_type_time", "mailguard_conversion_events", ["company_id", "event_type", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_mailguard_event_company_type_time", table_name="mailguard_conversion_events")
    op.drop_table("mailguard_conversion_events")
    op.drop_table("mailguard_tracking_references")
    op.drop_table("mailguard_integrations")
    op.drop_index("ix_scheduled_meta_due", table_name="scheduled_meta_publications")
    op.drop_table("scheduled_meta_publications")
    op.drop_index("ix_post_content_review_version", table_name="post_content_reviews")
    op.drop_table("post_content_reviews")
    op.drop_column("meta_page_connections", "next_metrics_sync_at")
    op.drop_column("meta_page_connections", "metrics_sync_interval_hours")
    op.drop_column("meta_page_connections", "metrics_schedule_enabled")
