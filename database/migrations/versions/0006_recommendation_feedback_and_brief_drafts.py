"""Persist recommendation feedback and reviewable campaign brief drafts."""

from alembic import op
import sqlalchemy as sa


revision = "0006_recommendation_feedback_and_brief_drafts"
down_revision = "0005_manual_metric_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "analytics_recommendations" not in tables:
        op.create_table(
            "analytics_recommendations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_id", sa.String(length=160), nullable=False),
            sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("recommendation_json", sa.JSON(), nullable=False),
            sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="new"),
            sa.Column("feedback_json", sa.JSON()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "source_id", "evidence_fingerprint", name="uq_recommendation_source_evidence"),
        )
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("analytics_recommendations")}
    if "ix_recommendation_company_status" not in indexes:
        op.create_index(
            "ix_recommendation_company_status",
            "analytics_recommendations",
            ["company_id", "lifecycle_status"],
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "campaign_brief_revision_drafts" not in tables:
        op.create_table(
            "campaign_brief_revision_drafts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("recommendation_id", sa.String(length=36), sa.ForeignKey("analytics_recommendations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("base_version", sa.Integer(), nullable=False),
            sa.Column("changes_json", sa.JSON(), nullable=False),
            sa.Column("resulting_brief_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending_review"),
            sa.Column("note", sa.Text()),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("recommendation_id", name="uq_brief_revision_recommendation"),
        )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("campaign_brief_revision_drafts")}
    if "ix_brief_revision_company_campaign" not in indexes:
        op.create_index(
            "ix_brief_revision_company_campaign",
            "campaign_brief_revision_drafts",
            ["company_id", "campaign_id", "created_at"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "campaign_brief_revision_drafts" in inspector.get_table_names():
        indexes = {item["name"] for item in inspector.get_indexes("campaign_brief_revision_drafts")}
        if "ix_brief_revision_company_campaign" in indexes:
            op.drop_index("ix_brief_revision_company_campaign", table_name="campaign_brief_revision_drafts")
        op.drop_table("campaign_brief_revision_drafts")
    inspector = sa.inspect(op.get_bind())
    if "analytics_recommendations" in inspector.get_table_names():
        indexes = {item["name"] for item in inspector.get_indexes("analytics_recommendations")}
        if "ix_recommendation_company_status" in indexes:
            op.drop_index("ix_recommendation_company_status", table_name="analytics_recommendations")
        op.drop_table("analytics_recommendations")
