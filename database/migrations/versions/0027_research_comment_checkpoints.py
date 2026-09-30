"""Add a tenant/version-bound comment frontier without storing personal content."""

from alembic import op
import sqlalchemy as sa


revision = "0027_comment_frontier"
down_revision = "0026_research_source_erasure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    constraints = {item["name"] for item in inspector.get_unique_constraints("market_evidence")}
    if "uq_market_evidence_tenant_source_id" not in constraints:
        op.create_unique_constraint(
            "uq_market_evidence_tenant_source_id", "market_evidence", ["company_id", "source_id", "id"],
        )
    # Initial metadata-based migration can already contain this table on a
    # fresh database. Do not rewrite or duplicate a released migration.
    if "research_comment_checkpoints" in inspector.get_table_names():
        return
    op.create_table(
        "research_comment_checkpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("evidence_version_id", sa.String(36), nullable=False),
        sa.Column("external_post_id", sa.String(100), nullable=False),
        sa.Column("parent_key", sa.String(100), server_default="root", nullable=False),
        sa.Column("cursor_after", sa.String(2048)),
        sa.Column("status", sa.String(24), server_default="privacy_hold", nullable=False),
        sa.Column("received_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_reported_count", sa.Integer()),
        sa.Column("count_definition", sa.String(48), server_default="post_comments_summary", nullable=False),
        sa.Column("pagination_exhausted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("stop_reason", sa.String(80), server_default="privacy_hold"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "observation_id", "parent_key", name="uq_comment_checkpoint_observation_parent"),
        sa.UniqueConstraint("company_id", "id", name="uq_comment_checkpoint_tenant_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "source_id", "evidence_id"],
            ["market_evidence.company_id", "market_evidence.source_id", "market_evidence.id"],
            name="fk_comment_checkpoint_source_evidence_tenant", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "evidence_id", "observation_id", "evidence_version_id"],
            ["market_observations.company_id", "market_observations.evidence_id",
             "market_observations.id", "market_observations.evidence_version_id"],
            name="fk_comment_checkpoint_observation_version_tenant", ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('privacy_hold','queued','collecting','partial','completed','error','suppressed')",
            name="ck_comment_checkpoint_status",
        ),
        sa.CheckConstraint(
            "received_count >= 0 AND pages_processed >= 0 AND "
            "(provider_reported_count IS NULL OR provider_reported_count >= 0)",
            name="ck_comment_checkpoint_counts",
        ),
    )
    op.create_index(
        "ix_comment_checkpoint_source_status", "research_comment_checkpoints",
        ["company_id", "source_id", "status", "created_at"],
    )


def downgrade() -> None:
    # Downgrade is only for disposable tests; do not discard user checkpoints
    # during operational rollback. Keep the Page gate and schema in place.
    op.drop_index("ix_comment_checkpoint_source_status", table_name="research_comment_checkpoints")
    op.drop_table("research_comment_checkpoints")
    op.drop_constraint("uq_market_evidence_tenant_source_id", "market_evidence", type_="unique")
