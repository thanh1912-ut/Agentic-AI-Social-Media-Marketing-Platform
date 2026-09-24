"""Persist campaigns, immutable post versions, approvals and export artifacts."""

from alembic import op
import sqlalchemy as sa


revision = "0004_campaign_content_workflows"
down_revision = "0003_deepseek_knowledge_versions"
branch_labels = None
depends_on = None


def _create_table_if_missing(name: str, *elements, **kwargs) -> None:
    # Earlier migrations used the current ORM metadata for bootstrap creation.
    # A fresh install can therefore already contain tables introduced later.
    if name not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(name, *elements, **kwargs)


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _create_table_if_missing(
        "campaigns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("brief_json", sa.JSON(), nullable=False),
        sa.Column("pillars_json", sa.JSON(), nullable=False),
        sa.Column("channels_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index_if_missing("ix_campaign_company_status", "campaigns", ["company_id", "status"])

    _create_table_if_missing(
        "campaign_posts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("pillar", sa.String(length=80), nullable=False),
        sa.Column("format", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_json", sa.JSON(), nullable=False),
        sa.Column("pending_approval_version", sa.Integer()),
        sa.Column("requires_reapproval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("publish_mode", sa.String(length=20)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index_if_missing("ix_campaign_post_company_campaign", "campaign_posts", ["company_id", "campaign_id"])
    _create_index_if_missing("ix_campaign_post_company_status", "campaign_posts", ["company_id", "status"])

    _create_table_if_missing(
        "post_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_id", sa.String(length=36), sa.ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_name", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("generation_job_id", sa.String(length=36), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("post_id", "version", name="uq_post_version_number"),
    )
    _create_index_if_missing("ix_post_version_company_post", "post_versions", ["company_id", "post_id"])

    _create_table_if_missing(
        "post_approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_id", sa.String(length=36), sa.ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("decided_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decided_by_name", sa.String(length=200), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index_if_missing("ix_post_approval_company_post", "post_approvals", ["company_id", "post_id"])

    _create_table_if_missing(
        "content_generation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_ids_json", sa.JSON(), nullable=False),
        sa.Column("input_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("run_metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", name="uq_content_generation_job"),
    )

    _create_table_if_missing(
        "export_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=700), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("post_ids_json", sa.JSON(), nullable=False),
        sa.Column("version_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index_if_missing("ix_export_artifact_company_created", "export_artifacts", ["company_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_export_artifact_company_created", table_name="export_artifacts")
    op.drop_table("export_artifacts")
    op.drop_table("content_generation_runs")
    op.drop_index("ix_post_approval_company_post", table_name="post_approvals")
    op.drop_table("post_approvals")
    op.drop_index("ix_post_version_company_post", table_name="post_versions")
    op.drop_table("post_versions")
    op.drop_index("ix_campaign_post_company_status", table_name="campaign_posts")
    op.drop_index("ix_campaign_post_company_campaign", table_name="campaign_posts")
    op.drop_table("campaign_posts")
    op.drop_index("ix_campaign_company_status", table_name="campaigns")
    op.drop_table("campaigns")
