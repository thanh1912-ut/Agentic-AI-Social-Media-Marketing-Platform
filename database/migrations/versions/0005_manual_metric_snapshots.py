"""Persist tenant-scoped manual post metric snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "0005_manual_metric_snapshots"
down_revision = "0004_campaign_content_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "post_metric_snapshots" not in inspector.get_table_names():
        op.create_table(
            "post_metric_snapshots",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("post_id", sa.String(length=36), sa.ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_id", sa.String(length=160), nullable=False),
            sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("post_age_hours", sa.Integer(), nullable=False),
            sa.Column("reach", sa.Integer()),
            sa.Column("views", sa.Integer()),
            sa.Column("engagements", sa.Integer()),
            sa.Column("clicks", sa.Integer()),
            sa.Column("spend", sa.Numeric(14, 2)),
            sa.Column("attributed_revenue", sa.Numeric(14, 2)),
            sa.Column("attribution_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("imported_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.UniqueConstraint("company_id", "post_id", "source_id", "measured_at", name="uq_metric_post_source_measured"),
        )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("post_metric_snapshots")}
    if "ix_metric_company_source_measured" not in indexes:
        op.create_index(
            "ix_metric_company_source_measured",
            "post_metric_snapshots",
            ["company_id", "source_id", "measured_at"],
        )


def downgrade() -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("post_metric_snapshots")}
    if "ix_metric_company_source_measured" in indexes:
        op.drop_index("ix_metric_company_source_measured", table_name="post_metric_snapshots")
    if "post_metric_snapshots" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("post_metric_snapshots")
