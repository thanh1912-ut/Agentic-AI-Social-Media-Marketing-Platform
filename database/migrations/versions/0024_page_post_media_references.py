"""Store sanitized Page post link and attachment metadata."""

from alembic import op
import sqlalchemy as sa


revision = "0024_page_post_media_references"
down_revision = "0023_research_privacy_policy_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("meta_page_posts")}
    if "link_url" not in columns:
        op.add_column("meta_page_posts", sa.Column("link_url", sa.String(2048), nullable=True))
    if "attachments_json" not in columns:
        op.add_column(
            "meta_page_posts",
            sa.Column("attachments_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
    if "attachment_metadata_status" not in columns:
        op.add_column(
            "meta_page_posts",
            sa.Column(
                "attachment_metadata_status", sa.String(32), nullable=False,
                server_default=sa.text("'not_returned'"),
            ),
        )


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("meta_page_posts")}
    if "attachment_metadata_status" in columns:
        op.drop_column("meta_page_posts", "attachment_metadata_status")
    if "attachments_json" in columns:
        op.drop_column("meta_page_posts", "attachments_json")
    if "link_url" in columns:
        op.drop_column("meta_page_posts", "link_url")
