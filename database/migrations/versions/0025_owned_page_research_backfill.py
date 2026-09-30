"""Persist the owned Page research backfill cursor and observation time."""

from alembic import op
import sqlalchemy as sa


revision = "0025_owned_page_research_backfill"
down_revision = "0024_page_post_media_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    source_columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("research_sources")}
    source_additions = (
        ("owned_page_backfill_cursor", sa.Text(), None),
        ("owned_page_backfill_page_id", sa.String(100), None),
        ("owned_page_backfill_window_start", sa.DateTime(timezone=True), None),
        ("owned_page_backfill_complete", sa.Boolean(), sa.text("false")),
        ("owned_page_backfill_window_complete", sa.Boolean(), sa.text("false")),
        ("owned_page_backfill_pages_processed", sa.Integer(), sa.text("0")),
    )
    for name, column_type, default in source_additions:
        if name not in source_columns:
            kwargs = {"nullable": False} if default is not None else {"nullable": True}
            if default is not None:
                kwargs["server_default"] = default
            op.add_column("research_sources", sa.Column(name, column_type, **kwargs))

    cycle_columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("research_cycles")}
    if "collection_observed_at" not in cycle_columns:
        op.add_column("research_cycles", sa.Column("collection_observed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    cycle_columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("research_cycles")}
    if "collection_observed_at" in cycle_columns:
        op.drop_column("research_cycles", "collection_observed_at")
    source_columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("research_sources")}
    for name in (
        "owned_page_backfill_pages_processed", "owned_page_backfill_window_complete",
        "owned_page_backfill_complete",
        "owned_page_backfill_window_start", "owned_page_backfill_page_id",
        "owned_page_backfill_cursor",
    ):
        if name in source_columns:
            op.drop_column("research_sources", name)
