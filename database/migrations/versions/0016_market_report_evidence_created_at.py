"""Repair missing created_at on market report evidence links.

The foundation migration calls current ORM metadata.create_all(), and the
historical 0013 migration only creates this table when absent. Databases that
already had the table before created_at entered ORM metadata therefore stayed
without the column even though newer code expects it.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_market_report_evidence_created_at"
down_revision = "0015_database_job_and_crawl_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "market_report_evidence" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("market_report_evidence")}
    if "created_at" in columns:
        return

    op.add_column(
        "market_report_evidence",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE market_report_evidence AS link "
        "SET created_at = COALESCE("
        "(SELECT report.created_at FROM market_reports AS report WHERE report.id = link.report_id), "
        "CURRENT_TIMESTAMP) "
        "WHERE link.created_at IS NULL"
    ))
    op.alter_column("market_report_evidence", "created_at", nullable=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "market_report_evidence" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("market_report_evidence")}
        if "created_at" in columns:
            op.drop_column("market_report_evidence", "created_at")
