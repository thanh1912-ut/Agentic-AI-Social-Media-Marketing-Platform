"""Record per-source privacy processing notes without enabling processing."""

from alembic import op
import sqlalchemy as sa


revision = "0023_research_privacy_policy_records"
down_revision = "0022_ai_usage_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "research_privacy_policy_revisions" in tables:
        return
    op.create_table(
        "research_privacy_policy_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("processing_basis_reference", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("requested_retention_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("configured_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "source_id", "revision_no", name="uq_research_privacy_policy_revision"),
        sa.ForeignKeyConstraint(
            ["company_id", "source_id"],
            ["research_sources.company_id", "research_sources.id"],
            name="fk_research_privacy_policy_source_tenant",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("requested_retention_days BETWEEN 1 AND 365", name="ck_research_privacy_retention_days"),
    )

def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "research_privacy_policy_revisions" in tables:
        op.drop_table("research_privacy_policy_revisions")
