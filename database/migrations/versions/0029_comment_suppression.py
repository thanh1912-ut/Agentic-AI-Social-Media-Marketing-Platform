"""Keep a tenant-scoped comment deletion ledger and suppressed tombstones."""
from alembic import op
import sqlalchemy as sa

revision = "0029_comment_suppression"
down_revision = "0028_comment_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "research_comment_suppressions" not in inspector.get_table_names():
        op.create_table(
            "research_comment_suppressions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_id", sa.String(36), nullable=False),
            sa.Column("post_key_hash", sa.String(64), nullable=False),
            sa.Column("external_comment_id", sa.String(100), nullable=False),
            sa.Column("reason", sa.String(24), nullable=False),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("company_id", "source_id", "post_key_hash", "external_comment_id",
                                name="uq_comment_suppression_identity"),
            sa.ForeignKeyConstraint(
                ["company_id", "source_id"],
                ["research_sources.company_id", "research_sources.id"],
                name="fk_comment_suppression_source_tenant", ondelete="CASCADE",
            ),
            sa.CheckConstraint("reason IN ('subject_request','out_of_scope','privacy_risk')",
                               name="ck_comment_suppression_reason"),
        )
        op.create_index("ix_comment_suppression_post", "research_comment_suppressions",
                        ["company_id", "source_id", "post_key_hash"])
    # pg_dump/restore can retain legacy varchar-array casts that differ from
    # fresh metadata. Re-create the unchanged enums from one canonical SQL
    # definition, so fresh and upgrade constraints can be compared directly.
    enums = (
        ("research_comment_processing_decisions", "ck_comment_decision_status", "status IN ('pending','active','revoked')"),
        ("research_comment_processing_decisions", "ck_comment_decision_scope", "scope = 'local_comment_quarantine_v1'"),
        ("research_comment_checkpoints", "ck_comment_checkpoint_status",
         "status IN ('privacy_hold','queued','collecting','partial','completed','error','suppressed')"),
    )
    for table, name, definition in enums:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, definition)
    receipt_columns = {column["name"] for column in inspector.get_columns("research_comment_page_receipts")}
    if "suppressed_count" not in receipt_columns:
        op.add_column("research_comment_page_receipts", sa.Column("suppressed_count", sa.Integer(),
                                                               server_default="0", nullable=False))
    op.drop_constraint("ck_comment_page_receipt_counts", "research_comment_page_receipts", type_="check")
    op.create_check_constraint("ck_comment_page_receipt_counts", "research_comment_page_receipts",
                               "received_count >= 0 AND withheld_private_count >= 0 AND suppressed_count >= 0")
    op.drop_constraint("ck_comment_version_status", "research_comment_versions", type_="check")
    op.create_check_constraint("ck_comment_version_status", "research_comment_versions",
                               "status IN ('privacy_hold','expired','suppressed')")


def downgrade() -> None:
    # A rollback must not restore content or permit previously erased imports.
    raise RuntimeError("Comment suppression migration is forward-only; disable new UI instead of deleting the ledger")
