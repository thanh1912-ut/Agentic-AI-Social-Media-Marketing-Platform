"""Bind a workspace to one verified Facebook Page identity."""

from alembic import op
import sqlalchemy as sa


revision = "0021_page_workspace_identity"
down_revision = "0020_facebook_cli_public_collector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("companies")}
    if "page_id" not in columns:
        op.add_column("companies", sa.Column("page_id", sa.String(100), nullable=True))
    if "page_avatar_url" not in columns:
        op.add_column("companies", sa.Column("page_avatar_url", sa.String(2048), nullable=True))
    if "page_connection_state" not in columns:
        op.add_column(
            "companies",
            sa.Column(
                "page_connection_state", sa.String(32), nullable=False,
                server_default=sa.text("'connection_required'"),
            ),
        )

    # A single, non-conflicting legacy Page can be mapped, but its old token
    # must be verified again before agentic features are enabled. Multi-Page
    # and cross-workspace duplicates stay unbound for explicit Owner review.
    op.execute(sa.text(
        "UPDATE companies AS c SET page_id = p.page_id, page_connection_state = 'needs_reconnect' "
        "FROM meta_page_connections AS p "
        "WHERE p.company_id = c.id AND p.active = TRUE AND p.status = 'verified' "
        "AND (SELECT COUNT(*) FROM meta_page_connections p2 WHERE p2.company_id = c.id AND p2.active = TRUE) = 1 "
        "AND (SELECT COUNT(DISTINCT p3.company_id) FROM meta_page_connections p3 "
        "WHERE p3.page_id = p.page_id AND p3.active = TRUE) = 1"
    ))
    indexes = {item["name"] for item in inspector.get_indexes("companies")}
    if "ix_companies_page_id" not in indexes:
        op.create_index("ix_companies_page_id", "companies", ["page_id"], unique=True)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("companies")}
    if "ix_companies_page_id" in indexes:
        op.drop_index("ix_companies_page_id", table_name="companies")
    columns = {item["name"] for item in inspector.get_columns("companies")}
    for name in ("page_connection_state", "page_avatar_url", "page_id"):
        if name in columns:
            op.drop_column("companies", name)
