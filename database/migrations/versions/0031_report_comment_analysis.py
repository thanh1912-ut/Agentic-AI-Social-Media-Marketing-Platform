"""Pin screened comment analysis to reports without changing old reports."""
from alembic import op
import sqlalchemy as sa

revision = "0031_report_comment_analysis"
down_revision = "0030_screened_comment_analysis"
branch_labels = None
depends_on = None


def upgrade():
    if "market_report_comment_analyses" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table("market_report_comment_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("group_id", sa.String(36), nullable=False),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "report_id", "batch_id", name="uq_report_comment_analysis"),
        sa.ForeignKeyConstraint(["company_id", "group_id", "report_id"],
            ["market_reports.company_id", "market_reports.group_id", "market_reports.id"],
            name="fk_report_comment_report_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "source_id", "batch_id"],
            ["research_comment_analysis_batches.company_id", "research_comment_analysis_batches.source_id",
             "research_comment_analysis_batches.id"], name="fk_report_comment_batch_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "group_id", "source_id"],
            ["research_sources.company_id", "research_sources.group_id", "research_sources.id"],
            name="fk_report_comment_source_group", ondelete="CASCADE"))
    op.create_index("ix_report_comment_batch", "market_report_comment_analyses", ["company_id", "source_id", "batch_id"])


def downgrade():
    raise RuntimeError("Forward-only provenance: disable new report jobs without deleting pinned history")
