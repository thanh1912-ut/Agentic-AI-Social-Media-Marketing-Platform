"""Add scoped comment decisions, encrypted candidates and cursor receipts."""

from alembic import op
import sqlalchemy as sa


revision = "0028_comment_quarantine"
down_revision = "0027_comment_frontier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    unique = {row["name"] for row in inspector.get_unique_constraints("research_privacy_policy_revisions")}
    if "uq_research_privacy_policy_tenant_id" not in unique:
        op.create_unique_constraint("uq_research_privacy_policy_tenant_id", "research_privacy_policy_revisions",
                                    ["company_id", "source_id", "id"])
    existing = set(inspector.get_table_names())
    # 0001 creates current metadata on fresh installs. Each table is checked
    # independently; upgrade from the previously released head creates all three.
    if "research_comment_processing_decisions" not in existing:
        op.create_table(
            "research_comment_processing_decisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), nullable=False),
            sa.Column("source_id", sa.String(36), nullable=False),
            sa.Column("policy_revision_id", sa.String(36), nullable=False),
            sa.Column("assessment_reference", sa.Text(), nullable=False),
            sa.Column("scope", sa.String(40), server_default="local_comment_quarantine_v1", nullable=False),
            sa.Column("status", sa.String(16), server_default="pending", nullable=False),
            sa.Column("assessed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "source_id", "id", name="uq_comment_decision_tenant_source_id"),
            sa.ForeignKeyConstraint(
                ["company_id", "source_id", "policy_revision_id"],
                ["research_privacy_policy_revisions.company_id", "research_privacy_policy_revisions.source_id",
                 "research_privacy_policy_revisions.id"],
                name="fk_comment_decision_policy_tenant", ondelete="CASCADE",
            ),
            sa.CheckConstraint("status IN ('pending','active','revoked')", name="ck_comment_decision_status"),
            sa.CheckConstraint("scope = 'local_comment_quarantine_v1'", name="ck_comment_decision_scope"),
            sa.CheckConstraint("valid_until > created_at", name="ck_comment_decision_validity"),
        )
        op.create_index("ix_comment_decision_source_status", "research_comment_processing_decisions",
                        ["company_id", "source_id", "status", "valid_until"])
    if "research_comment_versions" not in existing:
        op.create_table(
            "research_comment_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), nullable=False),
            sa.Column("source_id", sa.String(36), nullable=False),
            sa.Column("evidence_id", sa.String(36), nullable=False),
            sa.Column("observation_id", sa.String(36), nullable=False),
            sa.Column("evidence_version_id", sa.String(36), nullable=False),
            sa.Column("decision_id", sa.String(36), nullable=False),
            sa.Column("parent_key", sa.String(100), nullable=False),
            sa.Column("external_comment_id", sa.String(100), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("candidate_ciphertext", sa.Text()),
            sa.Column("redactor_version", sa.String(80), nullable=False),
            sa.Column("redaction_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(24), server_default="privacy_hold", nullable=False),
            sa.Column("content_truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("likes", sa.Integer()),
            sa.Column("reply_count", sa.Integer()),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "observation_id", "external_comment_id", "content_hash",
                                name="uq_comment_version_observation_content"),
            sa.ForeignKeyConstraint(
                ["company_id", "source_id", "evidence_id"],
                ["market_evidence.company_id", "market_evidence.source_id", "market_evidence.id"],
                name="fk_comment_version_source_evidence_tenant", ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["company_id", "evidence_id", "observation_id", "evidence_version_id"],
                ["market_observations.company_id", "market_observations.evidence_id",
                 "market_observations.id", "market_observations.evidence_version_id"],
                name="fk_comment_version_observation_tenant", ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["company_id", "observation_id", "parent_key"],
                ["research_comment_checkpoints.company_id", "research_comment_checkpoints.observation_id",
                 "research_comment_checkpoints.parent_key"],
                name="fk_comment_version_parent_checkpoint", ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["company_id", "source_id", "decision_id"],
                ["research_comment_processing_decisions.company_id",
                 "research_comment_processing_decisions.source_id", "research_comment_processing_decisions.id"],
                name="fk_comment_version_decision_tenant", ondelete="CASCADE",
            ),
            sa.CheckConstraint("status IN ('privacy_hold','expired')", name="ck_comment_version_status"),
            sa.CheckConstraint("expires_at > captured_at", name="ck_comment_version_expiry"),
            sa.CheckConstraint("(likes IS NULL OR likes >= 0) AND (reply_count IS NULL OR reply_count >= 0)",
                               name="ck_comment_version_counts"),
        )
        if op.get_bind().dialect.name == "postgresql":
            op.create_check_constraint("ck_comment_version_quarantine_max_age", "research_comment_versions",
                                       "expires_at <= captured_at + INTERVAL '24 hours'")
        op.create_index("ix_comment_version_quarantine_expiry", "research_comment_versions", ["status", "expires_at"])
        op.create_index("ix_comment_version_observation_identity", "research_comment_versions",
                        ["company_id", "observation_id", "external_comment_id"])
    if "research_comment_page_receipts" not in existing:
        op.create_table(
            "research_comment_page_receipts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), nullable=False),
            sa.Column("checkpoint_id", sa.String(36), nullable=False),
            sa.Column("request_cursor_hash", sa.String(64), nullable=False),
            sa.Column("received_count", sa.Integer(), nullable=False),
            sa.Column("withheld_private_count", sa.Integer(), nullable=False),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "checkpoint_id", "request_cursor_hash", name="uq_comment_page_cursor_receipt"),
            sa.ForeignKeyConstraint(
                ["company_id", "checkpoint_id"],
                ["research_comment_checkpoints.company_id", "research_comment_checkpoints.id"],
                name="fk_comment_page_checkpoint_tenant", ondelete="CASCADE",
            ),
            sa.CheckConstraint("received_count >= 0 AND withheld_private_count >= 0", name="ck_comment_page_receipt_counts"),
        )


def downgrade() -> None:
    # Operational rollback keeps this schema and disables collection. Never
    # downgrade a live database just to roll back a worker release.
    op.drop_table("research_comment_page_receipts")
    op.drop_table("research_comment_versions")
    op.drop_table("research_comment_processing_decisions")
    op.drop_constraint("uq_research_privacy_policy_tenant_id", "research_privacy_policy_revisions", type_="unique")
